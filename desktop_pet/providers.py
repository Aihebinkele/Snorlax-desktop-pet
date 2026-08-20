"""AI 供应商注册表：统一管理可「监控 Token」的服务商及其余额查询方式。

每个供应商：id（配置/存储键）、name（展示名）、balance（余额查询是否支持）。
余额查询接口差异很大，只有公开了简单 HTTP 余额接口的服务商才实现 `fetch_balance`，
其余在数据条显示 `--`（余额仅能在平台控制台查看）。
"""

import json
import urllib.error
import urllib.request

# 展示顺序即下拉框/面板顺序
# recharge_url：该供应商平台的充值/用量页面（「投喂」按钮打开）
PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek", "balance": True,  "recharge_url": "https://platform.deepseek.com/usage"},
    {"id": "doubao",   "name": "豆包",     "balance": False, "recharge_url": "https://console.volcengine.com/ark"},
    {"id": "qwen",     "name": "千问",     "balance": False, "recharge_url": "https://bailian.console.aliyun.com/"},
    {"id": "zhipu",    "name": "智谱",     "balance": True,  "recharge_url": "https://open.bigmodel.cn/usercenter/proj-mgmt"},
    {"id": "hunyuan",  "name": "混元",     "balance": False, "recharge_url": "https://console.cloud.tencent.com/hunyuan"},
]

_PROVIDER_BY_ID = {p["id"]: p for p in PROVIDERS}

DEFAULT_PROVIDER = "deepseek"

TIMEOUT_SECONDS = 10


def provider_name(provider_id):
    p = _PROVIDER_BY_ID.get(provider_id)
    return p["name"] if p else provider_id


def supports_balance(provider_id):
    p = _PROVIDER_BY_ID.get(provider_id)
    return bool(p and p.get("balance"))


def normalize_provider(provider_id):
    """未知 id（如用户自定义供应商名）原样保留；仅空值回退到默认供应商。"""
    pid = (provider_id or "").strip()
    return pid if pid else DEFAULT_PROVIDER


def provider_recharge_url(provider_id):
    """返回该供应商平台的充值/用量页面地址（「投喂」按钮打开），无则返回空串。"""
    p = _PROVIDER_BY_ID.get(provider_id)
    return p.get("recharge_url", "") if p else ""


def fetch_balance(provider_id, key):
    """查询指定供应商余额（元），返回 float；不支持或失败抛异常。

    由 balance.BalanceFetcher 捕获异常并保留上次值。
    """
    if provider_id == "deepseek":
        return _fetch_deepseek(key)
    if provider_id == "zhipu":
        return _fetch_zhipu(key)
    raise ValueError(f"{provider_name(provider_id)} 未开放公开余额接口")


def _http_json(url, key, auth_prefix="Bearer "):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": auth_prefix + key,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_deepseek(key):
    data = _http_json("https://api.deepseek.com/user/balance", key)
    infos = data.get("balance_infos") or []
    for info in infos:
        if info.get("currency") == "CNY" and info.get("total_balance") is not None:
            return float(info["total_balance"])
    if infos and infos[0].get("total_balance") is not None:
        return float(infos[0]["total_balance"])
    raise ValueError("balance 字段缺失")


def _fetch_zhipu(key):
    # 社区/第三方确认的端点（非官方文档）：Authorization 直接传 API Key（id.secret）
    data = _http_json(
        "https://open.bigmodel.cn/api/biz/account/query-customer-account-report",
        key,
        auth_prefix="",
    )
    # 余额字段位于 data 子对象下
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    for field in ("availableBalance", "balance"):
        if inner.get(field) is not None:
            return float(inner[field])
    raise ValueError("balance 字段缺失")
