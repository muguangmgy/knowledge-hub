from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# common/config.py → parents[2] = backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """环境配置；字段名与 .env 键一致。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Phase 1 必用
    DATABASE_URL: str
    KB_DIR: str = "data/kb"
    CHROMA_DIR: str = "data/chroma"
    CORS_ORIGINS: str = "http://localhost:5173"

    # Phase 2+（预留）
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # Phase 3/4（预留）
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "deepseek-ai/DeepSeek-V4-Flash"

    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    INGEST_MAX_MB: int = 50
    RAG_TOP_K: int = 8
    RAG_REJECT_MAX_DISTANCE: float = 0.55

    def resolve_path(self, value: str) -> Path:
        """相对路径锚定到 backend 根，避免受启动 cwd 影响。"""
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def kb_dir(self) -> Path:
        """原文落盘根目录。"""
        return self.resolve_path(self.KB_DIR)

    @property
    def chroma_dir(self) -> Path:
        """Chroma 持久化目录。"""
        return self.resolve_path(self.CHROMA_DIR)

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS 允许源列表。"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """进程内单例，避免重复读 .env。"""
    return Settings()
