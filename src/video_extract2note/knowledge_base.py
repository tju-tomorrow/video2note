"""知识库模块：基于 ChromaDB 的向量存储与检索。

初始化: kb = KnowledgeBase()
重建索引: kb.rebuild()
搜索: kb.search("查询内容", top_k=5)
"""

import logging
import os
from pathlib import Path

import video_extract2note.config as cfg

logger = logging.getLogger(__name__)

_CHROMA_DIR = cfg.COOKIE_CACHE_DIR / "chroma"


def _get_embedding_client():
    """使用已有的 API key 创建 embedding 客户端。"""
    from openai import OpenAI

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        return OpenAI(api_key=deepseek_key, base_url=cfg.DEEPSEEK_BASE_URL), "deepseek-chat"
    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    if mimo_key:
        return OpenAI(api_key=mimo_key, base_url=cfg.MIMO_BASE_URL), cfg.MIMO_MODEL
    raise RuntimeError("未设置 DEEPSEEK_API_KEY 或 MIMO_API_KEY")


class KnowledgeBase:
    def __init__(self, persist_dir: Path | None = None):
        self._persist_dir = str(persist_dir or _CHROMA_DIR)
        self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb
        client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = client.get_or_create_collection("transcripts")
        return self._collection

    def _embed(self, texts: list[str]) -> list[list[float]]:
        client, model = _get_embedding_client()
        embeddings = []
        for text in texts:
            resp = client.embeddings.create(model=model, input=text[:8000])
            embeddings.append(resp.data[0].embedding)
        return embeddings

    def rebuild(self) -> int:
        """从素材库重建知识库索引。返回索引文档数。"""
        from video_extract2note.db import init_db, list_records

        init_db()
        records = list_records(limit=10000, offset=0)

        if not records:
            logger.info("素材库为空，跳过索引")
            return 0

        collection = self._ensure_collection()
        # 清空旧数据
        try:
            collection.delete(ids=collection.get()["ids"])
        except Exception:
            pass

        texts = []
        metadatas = []
        ids = []
        for r in records:
            content = (r.get("formatted_text") or r.get("raw_text") or "").strip()
            if not content or len(content) < 50:
                continue
            texts.append(content)
            metadatas.append({
                "id": str(r["id"]),
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "platform": r.get("platform") or "",
            })
            ids.append(str(r["id"]))

        if not texts:
            logger.info("素材库无有效文本，跳过索引")
            return 0

        logger.info("正在为 %d 篇文档创建 embedding...", len(texts))
        embeddings = self._embed(texts)

        collection.add(embeddings=embeddings, documents=texts, metadatas=metadatas, ids=ids)
        logger.info("知识库索引完成: %d 篇文档", len(texts))
        return len(texts)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """搜索相关文档。返回 [{id, title, url, platform, content, score}]。"""
        collection = self._ensure_collection()
        if collection.count() == 0:
            return []

        query_embedding = self._embed([query])[0]
        results = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, collection.count()))

        docs = []
        if not results["ids"] or not results["ids"][0]:
            return docs

        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            doc_text = results["documents"][0][i] if results["documents"] else ""
            distance = results["distances"][0][i] if results.get("distances") else 0
            docs.append({
                "id": int(doc_id) if doc_id.isdigit() else doc_id,
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "platform": meta.get("platform", ""),
                "content": doc_text[:1500],
                "score": round(1 - min(distance, 1), 4),
            })
        return docs

    def is_built(self) -> bool:
        try:
            collection = self._ensure_collection()
            return collection.count() > 0
        except Exception:
            return False


# 单例
_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
