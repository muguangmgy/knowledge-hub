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

    # --- BASE ---
    DATABASE_URL: str
    CORS_ORIGINS: str = "http://localhost:5173"
    KB_DIR: str = "data/kb"

    # --- JWT ---
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # --- CHROMA ---
    CHROMA_DIR: str = "data/chroma"

    # --- LLM ---
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "deepseek-ai/DeepSeek-V4-Flash"

    # --- EMBEDDING ---
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    # --- RERANK ---
    # KEY/URL 为空时回落 EMBEDDING_*
    RERANK_API_KEY: str = ""
    RERANK_BASE_URL: str = ""
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # --- RAG ---
    INGEST_MAX_MB: int = 50  # 单文件上传上限（MB）
    RAG_TOP_K: int = 8  # 精排后最终给模型的片段条数
    RAG_HYBRID_PATH_TOP_K: int = 20  # 向量 / BM25 各路先召回多少条再 RRF 融合
    RAG_RERANK_MIN_SCORE: float = 0.05  # 精排软地板：低于此分视为噪声（约 0~1）
    RAG_RERANK_RELATIVE_RATIO: float = 0.5  # 精排相对落差：须 ≥ Top1分数×该比例，否则丢掉
    RAG_RERANK_KEEP_TOP1_FLOOR: float = 0.15  # 滤完为空时，Top1≥此值则至少保留 Top1，避免短问误拒答
    RAG_REJECT_MAX_DISTANCE: float = 0.55  # 向量距离上限（仅 filter_relevant 调试用；正式问答以精排分数为准）
    RAG_RELATIVE_MAX_GAP: float = 0.15  # 与 Top1 距离差过大则丢（同上，调试用）

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
