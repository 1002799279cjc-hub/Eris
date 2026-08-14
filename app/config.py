"""全局配置：支持环境变量覆盖，未配置 DeepSeek Key 时自动进入 Mock 降级模式。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    # 大模型 API（硅基流动 SiliconFlow，OpenAI 兼容协议）
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.siliconflow.cn/v1")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-V3.2")

    # 本地存储
    db_path: Path = BASE_DIR / os.getenv("DB_PATH", "data/recall.db")
    chroma_dir: Path = BASE_DIR / os.getenv("CHROMA_DIR", "data/chroma")
    export_dir: Path = BASE_DIR / os.getenv("EXPORT_DIR", "exports")
    upload_dir: Path = BASE_DIR / "data/uploads"

    def __init__(self) -> None:
        for d in (self.db_path.parent, self.chroma_dir, self.export_dir, self.upload_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def ai_enabled(self) -> bool:
        """是否配置了 DeepSeek Key；未配置则全站 AI 功能走 Mock。"""
        return bool(self.deepseek_api_key)


settings = Settings()
