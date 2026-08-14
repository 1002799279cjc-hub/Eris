"""系统设置路由：查询运行模式 / 运行时配置 DeepSeek Key（供测试面板使用）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings as app_settings
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"


class KeyIn(BaseModel):
    api_key: str
    model: str = ""


async def _verify_key(api_key: str) -> str:
    """实测验证 Key：调硅基流动 models 接口。失败抛 HTTPException(400)。"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=app_settings.deepseek_base_url or DEFAULT_BASE_URL,
    )
    try:
        await client.models.list()
    except Exception as e:
        raise HTTPException(400, f"Key 验证失败：{str(e)[:120]}")
    return "ok"


@router.get("")
def get_settings():
    return {
        "ai_mode": ai_service.mode,
        "has_key": ai_service.has_key,
        "provider": "SiliconFlow（硅基流动）",
        "model": ai_service.model_name,
        "message": "AI 功能运行中；配置 Key 后自动切换为真实模型。"
        if ai_service.mode == "deepseek"
        else "当前为 Mock 演示模式，配置 Key 后启用真实 AI（硅基流动）。",
    }


@router.post("")
async def set_key(data: KeyIn):
    key = (data.api_key or "").strip()
    # ① 格式预检（sk- 前缀 + 最小长度）
    if not key.startswith("sk-") or len(key) < 20:
        raise HTTPException(400, "Key 格式无效：应以 sk- 开头且长度不少于 20 字符")
    # ② 真实 API 验证（无效 Key 拒绝，且不污染运行时配置）
    await _verify_key(key)
    # ③ 验证通过才落盘
    try:
        mode = ai_service.configure(key, data.model)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "ai_mode": mode,
        "has_key": ai_service.has_key,
        "model": ai_service.model_name,
        "message": "已配置，AI 已切换为真实模型。"
        if mode == "deepseek"
        else "Key 无效或未配置，仍为 Mock 模式。",
    }
