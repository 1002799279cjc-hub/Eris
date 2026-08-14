"""OCR 识别服务：硅基流动 DeepSeek-OCR 多模态 VLM（首选）→ 本地 PaddleOCR（兜底）→ Mock 占位。
- 路径：硅基流动 /v1/chat/completions 传 image_url；
- 失败降级：本地 PaddleOCR 3.x；再失败返回通用占位，提示用户手动输入。
"""
import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any

# 在 import PaddleOCR 之前关闭 oneDNN/MKLDNN 加速（避免 PaddlePaddle 3.3.1 onednn 兼容 bug）
os.environ.setdefault("FLAGS_enable_onednn", "0")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")

from ..config import settings

# 启动时同步加载持久化的 Key（避免 settings.json 写入后未生效）
from .ai_service import _load_persisted_key
_load_persisted_key()

log = logging.getLogger(__name__)

# 引擎状态（供前端展示）
_engine_status: str = "未初始化"
_engine_error: str = ""

# 首选远端 OCR 模型（硅基流动托管的 DeepSeek 专用 OCR 模型）
REMOTE_OCR_MODEL = "deepseek-ai/DeepSeek-OCR"
REMOTE_OCR_PROMPT = (
    "请把图片中的题目文字完整提取出来，纯文本输出。"
    "不要修改任何内容，不要加任何说明，不要使用 Markdown 标记，"
    "直接输出题目原文。"
)


def _build_remote_client():
    """构造硅基流动 OpenAI 客户端（用 settings 中的 key/base_url）。"""
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url or "https://api.siliconflow.cn/v1",
    )


async def _recognize_remote(image_path: Path) -> tuple[str, str]:
    """调用硅基流动 DeepSeek-OCR 多模态识别图片。返回 (text, status)。"""
    if not settings.deepseek_api_key:
        return "", "未配置 API Key"
    try:
        with open(image_path, "rb") as f:
            data_url = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        client = _build_remote_client()
        resp = await client.chat.completions.create(
            model=REMOTE_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": REMOTE_OCR_PROMPT},
                    ],
                }
            ],
            max_tokens=2048,
        )
        text = (resp.choices[0].message.content or "").strip()
        # 清理模型自带的提示污染（"请不要复制粘贴..."等）
        text = _clean_ocr_text(text)
        if text:
            return text, f"远端 OCR · {REMOTE_OCR_MODEL}"
        return "", "远端 OCR 未识别到文字"
    except Exception as e:
        return "", f"远端 OCR 失败（已降级）：{e}"


def _clean_ocr_text(text: str) -> str:
    """清理 OCR 模型输出：①模型附加说明 ②markdown 残余 ③过多样本检测。"""
    import re
    if not text:
        return text
    # 1) 去除常见的 OCR 模型附加说明
    noise_patterns = [
        r"^请不要复制粘贴.*?[\n。]",
        r"^请保留.*?[\n。]",
        r"^无任何商业用途.*?[\n。]",
        r"^希望对你有所帮助.*?[\n。]",
        r"^例如[：:].*?[\n]",
        r"^示例[：:].*?[\n]",
        r"^以上.*?[\n。]",
    ]
    for p in noise_patterns:
        text = re.sub(p, "", text, flags=re.MULTILINE)
    # 2) OCR 容易把引号/书名号/方框识别成 **（markdown 加粗），删除连续 2+ 的 *
    #    单 * 保留（可能是数学乘号 a*b）
    text = re.sub(r"\*{2,}", " ", text)
    # 3) OCR 缺字占位符过多（** 或问号连续）→ 视为识别失败，前端会自动走占位文本
    suspicious = len(re.findall(r"[\*?]{3,}|\.{3,}", text))
    if suspicious >= 2:
        # 把整段替换为占位引导语，避免半残题目进错题库误导复习
        return "【图片识别不完整】题目中存在较多占位/缺字，请换一张清晰的图片，或直接输入/粘贴题目文字。"
    text = text.lstrip()
    return text.strip()


def _get_paddle():
    global _engine_status, _engine_error
    try:
        from paddleocr import PaddleOCR
        _engine = PaddleOCR()
        _engine_status = "PaddleOCR (本地) 已就绪"
        _engine_error = ""
        return _engine
    except Exception as e:
        _engine_status = f"PaddleOCR 本地推理不可用"
        _engine_error = str(e)
        return None


def _recognize_paddle_sync(image_path: Path) -> tuple[str, str]:
    """本地 PaddleOCR 兜底识别。"""
    engine = _get_paddle()
    if not engine:
        return "", "PaddleOCR 不可用"
    try:
        if hasattr(engine, "predict"):
            result = engine.predict(str(image_path))
        else:
            result = engine.ocr(str(image_path), cls=True)
        lines: list[str] = []
        if result is not None and hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
            for page in result:
                if hasattr(page, "rec_texts"):
                    lines.extend(page.rec_texts or [])
                elif isinstance(page, list):
                    for item in page:
                        if isinstance(item, list) and len(item) >= 2 and item[1]:
                            lines.append(str(item[1][0]))
        text = "\n".join(lines).strip()
        if text:
            return text, "PaddleOCR (本地)"
        return "", "PaddleOCR 未识别到文字"
    except Exception as e:
        return "", f"PaddleOCR 推理失败：{e}"


def _mock_text() -> str:
    """OCR 全部失败时的占位文本（绝不污染数据库，引导用户手动输入）。"""
    return (
        "【OCR 占位文本】本图片识别暂不可用，请将真实题目粘贴或输入到下方输入框，"
        "或前往「错题集 → 录入」用文字录入。"
    )


async def recognize_image(image_path: Path) -> tuple[str, str]:
    """识别图片文字，状态：(text, status)。三层降级。"""
    global _engine_status, _engine_error
    # 1) 优先远端 DeepSeek-OCR（最快、最准）
    text, status = await _recognize_remote(image_path)
    if text.strip():
        _engine_status = status
        return text, status
    # 2) 兜底本地 PaddleOCR
    text2, status2 = await asyncio.to_thread(_recognize_paddle_sync, image_path)
    if text2.strip():
        return text2, status2
    # 3) 返回通用占位 + 失败原因
    _engine_status = status2 or status
    _engine_error = status2 or status
    return _mock_text(), _engine_status


def save_upload(content: bytes, filename: str) -> Path:
    """保存上传图片到本地 uploads 目录。"""
    safe = Path(filename).name
    dest = settings.upload_dir / f"{Path(safe).stem}_{int(time.time() * 1000)}.{Path(safe).suffix or 'png'}"
    dest.write_bytes(content)
    return dest


def engine_status() -> dict[str, str]:
    """返回 OCR 引擎状态（供前端）。"""
    return {"status": _engine_status, "error": _engine_error}