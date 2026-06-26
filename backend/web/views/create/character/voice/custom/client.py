import logging
import os

import requests

logger = logging.getLogger(__name__)


# 调用阿里云百炼音色复刻 API，统一处理 VOICE_URL 缺失/网络错误/非 JSON，失败返回 {'error': ...}。
def call_voice_api(data):
    voice_url = os.getenv("VOICE_URL")
    if not voice_url:
        logger.error("VOICE_URL 环境变量未设置")
        return {"error": "音色服务未配置"}

    headers = {
        "Authorization": f"Bearer {os.getenv('API_KEY')}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(voice_url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        logger.exception("voice API 请求失败")
        return {"error": "音色服务请求失败"}
    except ValueError:
        logger.exception("voice API 返回非 JSON")
        return {"error": "音色服务返回异常"}
