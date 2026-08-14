"""ChromaDB 向量库：知识点向量检索，支撑相似题推荐与变体题生成。

- 使用本地哈希 Embedding（零联网、零下载），避免 ChromaDB 默认 ONNX 模型
  在受限网络下首次 upsert 挂起。
- 未安装 chromadb 时自动降级为内存模拟，保证功能链路完整。
"""
from typing import Any

from ..config import settings

_client: Any = None
_collection: Any = None


class _LocalEmbedding:
    """确定性本地哈希向量（256 维字符频次 + L2 归一化），无需任何下载。"""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _featurize(self, text: str) -> list[float]:
        try:
            import numpy as np
            v = np.zeros(self.dim, dtype=np.float32)
            for ch in text:
                v[ord(ch) % self.dim] += 1.0
            norm = float(np.linalg.norm(v))
            if norm > 0:
                v = v / norm
            return v.tolist()
        except Exception:
            # numpy 不可用时退化为纯字符计数
            v = [0.0] * self.dim
            for ch in text:
                v[ord(ch) % self.dim] += 1.0
            return v

    def __call__(self, input: str | list[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            return self._featurize(input)
        return [self._featurize(t) for t in input]


def _get_collection():
    global _client, _collection
    if _collection is None:
        try:
            import chromadb
            _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
            _collection = _client.get_or_create_collection(
                name="knowledge_points",
                metadata={"hnsw:space": "cosine"},
                embedding_function=_LocalEmbedding(),
            )
        except Exception:
            _collection = _MemoryCollection()
    return _collection


class _MemoryCollection:
    """无 chromadb 时的内存模拟实现（同接口）。"""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}

    def upsert(self, ids, documents, metadatas):
        for i, doc in zip(ids, documents):
            self._docs[i] = {"document": doc, "metadata": (metadatas or [{}])[0]}

    def query(self, query_texts, n_results):
        q = (query_texts[0] if query_texts else "").lower()
        scored = []
        for i, item in self._docs.items():
            doc = item["document"].lower()
            score = len(set(q) & set(doc)) / max(1, len(set(q)))
            scored.append((score, i, item["metadata"]))
        scored.sort(key=lambda x: -x[0])
        top = scored[:n_results]
        return {
            "ids": [[i for _, i, _ in top]],
            "metadatas": [[m for _, _, m in top]],
        }

    def count(self) -> int:
        return len(self._docs)


def index_mistake(mistake_id: int, content: str, metadata: dict[str, Any]) -> None:
    col = _get_collection()
    try:
        col.upsert(
            ids=[str(mistake_id)],
            documents=[f"{content} 知识点：{metadata.get('knowledge_point','')}"],
            metadatas=[metadata],
        )
    except Exception:
        pass


def search_similar(content: str, top_k: int = 3) -> list[dict[str, Any]]:
    """返回相似错题列表。"""
    col = _get_collection()
    try:
        res = col.query(query_texts=[content], n_results=top_k)
        ids = (res.get("ids") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        return [{"mistake_id": int(i), "metadata": m or {}} for i, m in zip(ids, metas)]
    except Exception:
        return []


def ensure_index() -> None:
    """应用启动时确保集合存在。"""
    _get_collection()
