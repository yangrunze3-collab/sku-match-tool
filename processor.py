# -*- coding: utf-8 -*-
"""全站同品检测工具 - 核心业务处理层"""

import time
import logging
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    JSF_BATCH_SIZE, MAX_CONCURRENT_WORKERS,
    OUTPUT_DATE_FORMAT, OUTPUT_FILE_PREFIX,
)
import api_client

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    pass


class SameProductProcessor:
    """全站同品检测处理器"""

    def __init__(self, progress_callback=None, log_callback=None):
        self.progress_callback = progress_callback or (lambda *a: None)
        self.log_callback = log_callback or (lambda m: None)
        self._stop_requested = False

        self.seed_skus = []
        self.sku_info_map = {}
        self.search_results = []
        self.sku_features = {}
        self.match_results = {}
        self.error_records = []

    def log(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_callback(f"[{timestamp}] {msg}")

    def update_progress(self, step, current, total, message=''):
        self.progress_callback(step, current, total, message)

    def request_stop(self):
        self._stop_requested = True
        self.log("⚠ 收到停止请求，正在安全终止...")

    @property
    def should_stop(self):
        return self._stop_requested

    # ==================== Step 1 ====================

    def step1_load_seed_skus(self, file_path):
        self.log("📖 步骤1: 读取种子SKU文件...")
        try:
            df = pd.read_excel(file_path, dtype=str)
        except Exception as e:
            raise ProcessingError(f"读取Excel失败: {e}")

        sku_col = None
        for col in df.columns:
            col_lower = col.strip().lower().replace('_', '').replace(' ', '').replace('-', '')
            if col_lower in ('skuid', 'skuids'):
                sku_col = col
                break

        if sku_col is None:
            sku_col = df.columns[0]
            self.log(f"未找到sku_id列，使用第一列: {sku_col}")

        self.seed_skus = df[sku_col].dropna().astype(str).str.strip().tolist()
        self.seed_skus = list(dict.fromkeys(self.seed_skus))

        self.log(f"✅ 读取到 {len(self.seed_skus)} 个种子SKU")
        self.update_progress(1, 1, 1, f"已读取 {len(self.seed_skus)} 个种子SKU")
        return len(self.seed_skus)

    # ==================== Step 2 ====================

    def step2_search_and_recall(self):
        total = len(self.seed_skus)
        self.log(f"🔍 步骤2: 查询SKU信息并搜索召回 ({total}个)...")
        self.error_records = []

        # 2.1 批量获取种子SKU信息
        self.log("  → 正在批量查询种子SKU信息...")
        batch_size = JSF_BATCH_SIZE
        batches = [self.seed_skus[i:i + batch_size] for i in range(0, total, batch_size)]

        completed = 0
        for batch in batches:
            if self.should_stop:
                return

            try:
                sku_ids_dict = {sid: "0" for sid in batch}
                result = api_client.query_product(sku_ids_dict)
                with api_client._cache_lock:
                    for sid in batch:
                        if sid in result:
                            self.sku_info_map[sid] = result[sid]
            except Exception as e:
                self.log(f"  ⚠ 批量查询失败: {e}")

            completed += len(batch)
            self.update_progress(2, completed, total * 2, f"查询SKU信息 {completed}/{total}")

        # 2.2 逐SKU搜索召回
        self.log("  → 正在搜索召回相似SKU...")
        completed = 0
        for sku_id in self.seed_skus:
            if self.should_stop:
                return

            sku_info = self.sku_info_map.get(sku_id, {})
            brand_name = sku_info.get('barndname_cn', '') or sku_info.get('brand_name', '')
            model = sku_info.get('item_type', '') or sku_info.get('model', '')
            colour = sku_info.get('jd_colour', '') or sku_info.get('colour', '')
            size = sku_info.get('size', '') or sku_info.get('jd_size', '')
            sku_name = sku_info.get('product_name', '') or sku_info.get('sku_name', '')

            key = brand_name or ''
            for v in [model, colour, size]:
                if v and v not in key:
                    key = key + ' ' + v

            search_data = []
            try:
                search_data = api_client.search_sku_info(key)
                if not search_data and brand_name and model:
                    key2 = brand_name + ' ' + model
                    key = key + ' | ' + key2
                    search_data = api_client.search_sku_info(key2)
                if not search_data and sku_name:
                    key = key + ' | sku_name'
                    search_data = api_client.search_sku_info(sku_name)
            except Exception as e:
                self.log(f"  ⚠ 搜索失败 sku={sku_id}: {e}")

            if not search_data:
                self.error_records.append(f"搜索结果为空: {sku_id}, key={key}")
                self.search_results.append({
                    'seed_sku_id': sku_id,
                    'seed_sku_name': sku_name,
                    'search_key': key,
                    'recall_sku_id': '',
                    'recall_sku_name': '',
                    'sort': -1,
                })
            else:
                for idx, item in enumerate(search_data):
                    self.search_results.append({
                        'seed_sku_id': sku_id,
                        'seed_sku_name': sku_name,
                        'search_key': key,
                        'recall_sku_id': str(item.get('skuId', '')),
                        'recall_sku_name': item.get('skuTitle', ''),
                        'sort': idx,
                    })

            completed += 1
            self.update_progress(2, total + completed, total * 2, f"搜索召回 {completed}/{total}")

        recall_sku_ids = set(r['recall_sku_id'] for r in self.search_results if r['recall_sku_id'])
        self.log(f"✅ 搜索召回完成: 种子 {total}个, 召回去重 {len(recall_sku_ids)}个, 搜索失败 {len(self.error_records)}个")

    # ==================== Step 3 ====================

    def step3_get_recall_sku_details(self):
        all_sku_ids = set(self.seed_skus)
        for r in self.search_results:
            if r['recall_sku_id']:
                all_sku_ids.add(r['recall_sku_id'])

        total = len(all_sku_ids)
        self.log(f"📋 步骤3: 获取SKU详细信息 ({total}个)...")

        to_query = [sid for sid in all_sku_ids if sid not in self.sku_info_map]
        self.log(f"  → 需要新查询 {len(to_query)} 个SKU信息")

        completed = len(all_sku_ids) - len(to_query)
        batch_size = JSF_BATCH_SIZE
        batches = [to_query[i:i + batch_size] for i in range(0, len(to_query), batch_size)]

        for batch in batches:
            if self.should_stop:
                return

            try:
                sku_ids_dict = {sid: "0" for sid in batch}
                result = api_client.query_product(sku_ids_dict)
                self.sku_info_map.update(result)
            except Exception as e:
                self.log(f"  ⚠ 批量查询失败: {e}")

            completed += len(batch)
            self.update_progress(3, completed, total, f"获取SKU详情 {completed}/{total}")

        # 查询兄弟SKU映射
        self.log("  → 正在查询兄弟SKU映射...")
        sku_ids_list = list(all_sku_ids)
        map_batches = [sku_ids_list[i:i + 10] for i in range(0, len(sku_ids_list), 10)]
        for batch in map_batches:
            if self.should_stop:
                return
            try:
                api_client.query_map_info(batch)
            except Exception as e:
                self.log(f"  ⚠ 映射查询失败: {e}")

        self.log(f"✅ SKU详细信息获取完成, 已缓存 {len(self.sku_info_map)} 条")

    # ==================== Step 4 ====================

    def step4_calculate_features(self):
        total = len(self.seed_skus)
        self.log(f"🧮 步骤4: 计算SKU特征 ({total}个)...")
        completed = 0
        failed = 0

        for sku_id in self.seed_skus:
            if self.should_stop:
                return

            sku_info = self.sku_info_map.get(sku_id, {})
            if not sku_info:
                self.log(f"  ⚠ SKU {sku_id} 无详情信息，跳过特征计算")
                completed += 1
                failed += 1
                continue

            # 构建兄弟信息
            with api_client._cache_lock:
                sku_ids_str = api_client.SKU_MAP_CACHE.get(sku_id, [])
            brothers_msg = {sku_id: sku_info}

            if sku_ids_str:
                for bro_sid in sku_ids_str:
                    bro_sid = str(bro_sid)
                    bro_info = self.sku_info_map.get(bro_sid)
                    if bro_info:
                        brothers_msg[bro_sid] = bro_info

            try:
                features = api_client.query_sku_features(sku_info, brothers_msg)
                self.sku_features[sku_id] = features
            except Exception as e:
                self.log(f"  ⚠ 特征计算失败 sku={sku_id}: {e}")
                self.sku_features[sku_id] = {}
                failed += 1

            completed += 1
            self.update_progress(4, completed, total, f"计算特征 {completed}/{total}")

        self.log(f"✅ 特征计算完成: 成功 {total - failed}, 失败 {failed}")

    # ==================== Step 5 ====================

    def step5_match_same_products(self):
        total = len(self.seed_skus)
        self.log(f"🔗 步骤5: 同品匹配 ({total}个)...")
        completed = 0
        failed = 0

        for sku_id in self.seed_skus:
            if self.should_stop:
                return

            recall_ids = [
                r['recall_sku_id'] for r in self.search_results
                if r['seed_sku_id'] == sku_id and r['recall_sku_id'] and r['recall_sku_id'] != sku_id
            ]

            all_infos = {}
            seed_feature = self.sku_features.get(sku_id, {})
            if seed_feature:
                all_infos[sku_id] = seed_feature
            for rid in recall_ids:
                r_feature = self.sku_features.get(rid, {})
                if r_feature:
                    all_infos[rid] = r_feature

            try:
                result = api_client.query_high_recall_same_compare(sku_id, recall_ids, all_infos)
                self.match_results[sku_id] = result
            except Exception as e:
                self.log(f"  ⚠ 匹配失败 sku={sku_id}: {e}")
                self.match_results[sku_id] = {
                    'query_id': sku_id,
                    'match_ids': [],
                    'high_precision_ids': []
                }
                failed += 1

            completed += 1
            self.update_progress(5, completed, total, f"同品匹配 {completed}/{total}")

        total_match = sum(len(r.get('match_ids', [])) for r in self.match_results.values())
        total_hp = sum(len(r.get('high_precision_ids', [])) for r in self.match_results.values())
        self.log(f"✅ 同品匹配完成: 高召 {total_match} 对, 高准 {total_hp} 对, 失败 {failed}")

    # ==================== 导出结果 ====================

    def export_results(self, output_path):
        self.log(f"📤 导出结果到: {output_path}")

        # Sheet1: 种子SKU信息
        seed_rows = []
        for sku_id in self.seed_skus:
            info = self.sku_info_map.get(sku_id, {})
            match_res = self.match_results.get(sku_id, {})
            seed_rows.append({
                '种子SKU': sku_id,
                '商品名称': info.get('product_name', ''),
                '品牌': info.get('barndname_cn', ''),
                '型号': info.get('item_type', ''),
                '颜色': info.get('jd_colour', ''),
                '尺寸': info.get('size', '') or info.get('jd_size', ''),
                '分类': info.get('leaf_jd_name', ''),
                '价格': info.get('jd_prc', ''),
                '高召匹配数': len(match_res.get('match_ids', [])),
                '高准匹配数': len(match_res.get('high_precision_ids', [])),
            })
        df_seed = pd.DataFrame(seed_rows)

        # Sheet2: 召回结果
        if self.search_results:
            df_recall = pd.DataFrame(self.search_results)
            df_recall.columns = ['种子SKU', '种子SKU名称', '搜索关键词', '召回SKU', '召回SKU名称', '排序']
        else:
            df_recall = pd.DataFrame(
                columns=['种子SKU', '种子SKU名称', '搜索关键词', '召回SKU', '召回SKU名称', '排序']
            )

        # Sheet3: 匹配结果明细
        match_rows = []
        for sku_id in self.seed_skus:
            match_res = self.match_results.get(sku_id, {})
            seed_info = self.sku_info_map.get(sku_id, {})

            match_rows.append({
                '种子SKU': sku_id,
                '种子商品名称': seed_info.get('product_name', ''),
                '匹配SKU': sku_id,
                '匹配类型': '种子',
            })

            for mid in match_res.get('match_ids', []):
                match_rows.append({
                    '种子SKU': sku_id,
                    '种子商品名称': seed_info.get('product_name', ''),
                    '匹配SKU': str(mid),
                    '匹配类型': '高召',
                })

            for pid in match_res.get('high_precision_ids', []):
                match_rows.append({
                    '种子SKU': sku_id,
                    '种子商品名称': seed_info.get('product_name', ''),
                    '匹配SKU': str(pid),
                    '匹配类型': '高准',
                })

        df_match = pd.DataFrame(match_rows) if match_rows else pd.DataFrame(
            columns=['种子SKU', '种子商品名称', '匹配SKU', '匹配类型']
        )

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_seed.to_excel(writer, sheet_name='种子SKU信息', index=False)
            df_recall.to_excel(writer, sheet_name='召回结果', index=False)
            df_match.to_excel(writer, sheet_name='匹配结果', index=False)

        self.log(f"✅ 结果已导出: {output_path}")

    # ==================== 完整流程 ====================

    def run_full_pipeline(self, input_file, output_path):
        self._stop_requested = False
        self.error_records = []
        self.search_results = []
        self.sku_features = {}
        self.match_results = {}

        try:
            count = self.step1_load_seed_skus(input_file)
            if count == 0:
                raise ProcessingError("未读取到任何种子SKU")

            self.step2_search_and_recall()
            if self.should_stop:
                self.log("⏹ 流程已停止")
                return False

            self.step3_get_recall_sku_details()
            if self.should_stop:
                self.log("⏹ 流程已停止")
                return False

            self.step4_calculate_features()
            if self.should_stop:
                self.log("⏹ 流程已停止")
                return False

            self.step5_match_same_products()
            if self.should_stop:
                self.log("⏹ 流程已停止")
                return False

            self.export_results(output_path)
            self.log("🎉 全站同品检测流程完成!")
            return True

        except ProcessingError as e:
            self.log(f"❌ 处理异常: {e}")
            return False
        except Exception as e:
            self.log(f"❌ 未知异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
