"""本地持久化 Chroma 客户端。

Phase 1 只负责打开目录并探活；cosine collection（kh_chunks）在 Phase 3 入库时创建。
"""

from chromadb import PersistentClient
from chromadb.api import ClientAPI

from app.common.config import Settings

_client: ClientAPI | None = None


def open_chroma(settings: Settings) -> ClientAPI:
    """lifespan 调用：目录不存在则创建，并 list_collections 做一次可用性探测。"""
    global _client
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    _client = PersistentClient(path=str(settings.chroma_dir))
    _client.list_collections()
    return _client


def get_chroma() -> ClientAPI:
    """返回已初始化客户端；未走 lifespan 时禁止使用。"""
    if _client is None:
        raise RuntimeError("Chroma client is not initialized")
    return _client
