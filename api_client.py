# -*- coding: utf-8 -*-
"""全站同品检测工具 - API 接口调用层"""

import json
import time
import base64
import pickle
import logging
import requests
import threading
from config import (
    JSF_BASE_URL, JSF_APP_ID, JSF_TIMEOUT,
    SEARCH_URL, FEATURE_URL, MATCH_HIGH_RECALL_URL, MATCH_HIGH_PRECISION_URL,
    MAX_RETRY_ATTEMPTS, RETRY_WAIT_SECONDS, SEARCH_CALL_INTERVAL,
    SKU_INFO_CACHE, SKU_FEATURE_CACHE, SKU_MAP_CACHE,
)

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_search_lock = threading.Lock()
_last_search_time = 0.0


def _snake_to_camel(snake_str):
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def _convert_keys_to_camel_case(d):
    new_dict = {}
    for k, v in d.items():
        new_key = _snake_to_camel(k)
        if isinstance(v, dict):
            new_dict[new_key] = _convert_keys_to_camel_case(v)
        else:
            new_dict[new_key] = v
    return new_dict


def _pickle_ser_convert_base64(data):
    data = pickle.dumps(data)
    return base64.b64encode(data).decode('utf-8')


def _base64_convert_pickle_inverse_ser(m_str):
    decoded_bytes = base64.b64decode(m_str)
    return pickle.loads(decoded_bytes)


# ==================== JSF 通用调用 ====================

def call_jsf(data, method_name, timeout=None):
    if timeout is None:
        timeout = JSF_TIMEOUT
    url = f"{JSF_BASE_URL}/{method_name}/{JSF_APP_ID}/jsf/{timeout}"
    headers = {'Content-Type': 'application/json'}

    last_exception = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = requests.post(url, json=data, headers=headers, timeout=timeout / 1000 + 1)
            if response.status_code == 200:
                return response.json()
            else:
                last_exception = Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning(f"JSF调用失败(第{attempt + 1}次): {method_name}, 错误: {e}")

        if attempt < MAX_RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_WAIT_SECONDS)

    logger.error(f"JSF调用最终失败: {method_name}, 错误: {last_exception}")
    return None


# ==================== 查询SKU商品信息 ====================

def query_product(sku_ids_dict):
    result = {}
    uncached = {}

    with _cache_lock:
        for k, v in sku_ids_dict.items():
            if k in SKU_INFO_CACHE:
                result[k] = SKU_INFO_CACHE[k]
            else:
                uncached[k] = v

    if not uncached:
        return result

    response = call_jsf([uncached], 'queryProduct')
    if response and response.get('code') == 0:
        info_list = response.get('result', [])
        with _cache_lock:
            for info in info_list:
                sku_id = str(info.get('sku_id', ''))
                result[sku_id] = info
                SKU_INFO_CACHE[sku_id] = info
    else:
        error_msg = response.get('msg', '未知错误') if response else '接口无响应'
        raise Exception(f"查询SKU信息接口异常: {error_msg}")

    return result


def query_single_sku_info(sku_id):
    sku_id = str(sku_id)
    with _cache_lock:
        if sku_id in SKU_INFO_CACHE:
            return SKU_INFO_CACHE[sku_id]
    result = query_product({sku_id: "0"})
    return result.get(sku_id)


def query_map_info(sku_ids):
    uncached = []
    result = {}
    with _cache_lock:
        for sid in sku_ids:
            sid = str(sid)
            if sid in SKU_MAP_CACHE:
                result[sid] = SKU_MAP_CACHE[sid]
            else:
                uncached.append(sid)

    if not uncached:
        return result

    response = call_jsf([uncached], 'queryMapInfo')
    if response and response.get('code') == 0:
        map_result = response.get('result', {})
        with _cache_lock:
            for k, v in map_result.items():
                result[str(k)] = v
                SKU_MAP_CACHE[str(k)] = v
    else:
        error_msg = response.get('msg', '未知错误') if response else '接口无响应'
        raise Exception(f"查询SKU映射接口异常: {error_msg}")

    return result


# ==================== 搜索服务 ====================

def search_sku_info(key):
    global _last_search_time

    with _search_lock:
        now = time.time()
        elapsed = now - _last_search_time
        if elapsed < SEARCH_CALL_INTERVAL:
            time.sleep(SEARCH_CALL_INTERVAL - elapsed)
        _last_search_time = time.time()

    try:
        resp = requests.post(SEARCH_URL, json={'content': key}, timeout=30)
        data = resp.json()
        return data.get('data', [])[:100]
    except Exception as e:
        logger.error(f"搜索接口异常: key={key}, 错误: {e}")
        return []


# ==================== 特征计算 ====================

def query_sku_features(sku_msg, brothers_msg):
    sku_id = str(sku_msg.get('sku_id', ''))

    with _cache_lock:
        if sku_id in SKU_FEATURE_CACHE:
            return SKU_FEATURE_CACHE[sku_id]

    sku_msg_camel = _convert_keys_to_camel_case(sku_msg)
    brothers_msg_camel = _convert_keys_to_camel_case(brothers_msg)

    data = {
        'msg': sku_msg_camel,
        'brothersMsg': brothers_msg_camel,
        'customTag': 'qz'
    }

    last_exception = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = requests.post(
                FEATURE_URL,
                data=json.dumps(data),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            res = response.json()
            if res.get('status') == 'success':
                features = res.get('features')
                with _cache_lock:
                    SKU_FEATURE_CACHE[sku_id] = features
                return features
            else:
                last_exception = Exception(f"特征计算失败: {response.text[:200]}")
        except Exception as e:
            last_exception = e
            logger.warning(f"特征计算接口失败(第{attempt + 1}次): sku={sku_id}, 错误: {e}")

        if attempt < MAX_RETRY_ATTEMPTS - 1:
            time.sleep(2)

    logger.error(f"特征计算最终失败: sku={sku_id}")
    raise last_exception or Exception("特征计算未知错误")


# ==================== 同品匹配 ====================

def query_high_precision_same_compare(query_id):
    input_data = {'queryId': str(query_id)}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(
            MATCH_HIGH_PRECISION_URL,
            headers=headers,
            data=json.dumps(input_data),
            timeout=30
        )
        data = response.json()
        if data.get('status') == 'success':
            return data.get('matchResult', {}).get('fuzzyMatchIds', [])
        else:
            return []
    except Exception as e:
        logger.error(f"高准匹配接口异常: sku={query_id}, 错误: {e}")
        return []


def query_high_recall_same_compare(query_id, recall_ids, all_infos):
    pre_match_ids = query_high_precision_same_compare(query_id) or []

    same_compare_res = {
        'query_id': str(query_id),
        'match_ids': [],
        'high_precision_ids': pre_match_ids
    }

    if not recall_ids:
        return same_compare_res

    data = {
        'queryId': str(query_id),
        'recallIds': [str(rid) for rid in recall_ids],
        'features': all_infos,
        'customTag': 'qz_high_recall'
    }

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(
            MATCH_HIGH_RECALL_URL,
            headers=headers,
            data=json.dumps(data),
            timeout=30
        )
        res = response.json()
        if res.get('status') == 'success':
            match_ids = res.get('matchResult', {}).get('fuzzyMatchIds', [])
            m_ids = list(set(match_ids or []) - set(pre_match_ids or []))
            same_compare_res['match_ids'] = m_ids
        else:
            logger.warning(f"高召匹配返回异常: sku={query_id}")
    except Exception as e:
        logger.error(f"高召匹配接口异常: sku={query_id}, 错误: {e}")
        same_compare_res['match_ids'] = []

    return same_compare_res
