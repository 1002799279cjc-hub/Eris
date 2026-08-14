"""Recall AI错题本 - FastAPI 入口。
启动：uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database as db
from .routers import (chat, dashboard, export, help as help_router, mistakes,
                      review, settings)
from .services import vector_store
from .services.ai_service import ai_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    vector_store.ensure_index()
    yield


app = FastAPI(
    title="Recall AI错题本 API",
    description="拍照录入 · AI标注 · SM-2复习 · 对话答疑 · 数据看板 · 导出",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地开发放开；生产请收窄
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mistakes.router)
app.include_router(chat.router)
app.include_router(review.router)
app.include_router(dashboard.router)
app.include_router(export.router)
app.include_router(help_router.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ai_mode": ai_service.mode,
        "time": db.now_str(),
    }


@app.get("/api/health/deepseek")
async def health_deepseek():
    """帮助页一键测试：发一个 mini 真实对话，按耗时/结果判定，并返回模型回复片段。"""
    from .config import settings
    if not ai_service.has_key:
        return {
            "ok": False,
            "step": "key",
            "message": "未配置 API Key，请先在右下角 🔧 测试面板配置硅基流动 Key。",
        }
    t0 = time.time()
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url or "https://api.siliconflow.cn/v1",
        )
        resp = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": "回复两个字：连接成功"}],
            max_tokens=20,
        )
        elapsed = time.time() - t0
        text = (resp.choices[0].message.content or "").strip()
        return {
            "ok": True,
            "step": "chat",
            "elapsed": round(elapsed, 2),
            "model": settings.deepseek_model,
            "provider": "硅基流动 SiliconFlow",
            "reply": text,
            "message": f"✅ 连接成功（{elapsed:.1f}s）",
        }
    except Exception as e:
        return {
            "ok": False,
            "step": "chat",
            "elapsed": round(time.time() - t0, 2),
            "model": ai_service.model_name,
            "message": f"❌ 调用失败：{e}",
        }
