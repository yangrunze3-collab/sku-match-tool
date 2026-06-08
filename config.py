# -*- coding: utf-8 -*-
"""全站同品检测工具 - 配置常量"""

# ==================== JSF 接口配置 ====================
JSF_CLASS_NAME = 'com.jdi.isee.jsf.api.RealTimeProductService'
JSF_ALIAS = 'PRE'  # 预发环境
JSF_APP_ID = '1541605'
JSF_TIMEOUT = 20000  # ms

# ==================== 接口地址 ====================
JSF_BASE_URL = f"http://g.jsf.jd.local/{JSF_CLASS_NAME}/{JSF_ALIAS}"
SEARCH_URL = 'http://alout.jd.com/open/search'
FEATURE_URL = 'http://idt-sku-feature-algo-service-pre.jdindustry.com/get_feature_online'
MATCH_HIGH_RECALL_URL = 'http://idt-sku-match-algo-service-pre.jdindustry.com/common_product_compare'
MATCH_HIGH_PRECISION_URL = 'http://idt-sku-match-algo-service-pre.jdindustry.com/sku_search_service'

# ==================== 重试与限流配置 ====================
MAX_RETRY_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 20
SEARCH_CALL_INTERVAL = 0.1
JSF_BATCH_SIZE = 10
MAX_CONCURRENT_WORKERS = 5

# ==================== 内存缓存 ====================
SKU_INFO_CACHE = {}
SKU_FEATURE_CACHE = {}
SKU_MAP_CACHE = {}

# ==================== 导出配置 ====================
OUTPUT_DATE_FORMAT = '%Y%m%d'
OUTPUT_FILE_PREFIX = '匹配结果_'
