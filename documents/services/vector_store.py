import os
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

from django.conf import settings
from langchain_openai import OpenAIEmbeddings
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder
from pinecone_text.hybrid import hybrid_convex_scale
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "doc-chat-index")
EMBEDDING_DIM = 1536  # text-embedding-3-small


@lru_cache(maxsize=1)
def get_embeddings_instance():
    base_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    cache_dir = os.path.join(settings.BASE_DIR, "embedding_cache")
    os.makedirs(cache_dir, exist_ok=True)

    embedding_file_store = LocalFileStore(cache_dir)

    return CacheBackedEmbeddings.from_bytes_store(
        base_embeddings,
        embedding_file_store,
        namespace=base_embeddings.model,
        query_embedding_cache=True,
        key_encoder="blake2b",
    )


@lru_cache(maxsize=1)
def get_bm25_encoder():
    """BM25 sparse encoder pre-trained on MS MARCO corpus."""
    return BM25Encoder.default()


@lru_cache(maxsize=1)
def _get_pinecone_client():
    return Pinecone(api_key=os.getenv("PINECONE_API_KEY"))


def get_pinecone_index():
    """Returns the Pinecone Index object. Must exist with dotproduct metric."""
    pc = _get_pinecone_client()
    return pc.Index(PINECONE_INDEX_NAME)


class _HybridRetriever(BaseRetriever):
    """
    Pinecone hybrid retriever combining dense (OpenAI) + sparse (BM25) vectors.
    Supports metadata filter for per-document scoping.
    """

    embeddings: Any = Field(...)
    sparse_encoder: Any = Field(...)
    index: Any = Field(...)
    top_k: int = Field(default=7)
    alpha: float = Field(default=0.5)
    metadata_filter: Optional[Dict] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[LCDocument]:
        sparse_vec = self.sparse_encoder.encode_queries(query)
        dense_vec = self.embeddings.embed_query(query)
        dense_vec, sparse_vec = hybrid_convex_scale(dense_vec, sparse_vec, self.alpha)

        query_kwargs: Dict = {
            "vector": dense_vec,
            "sparse_vector": sparse_vec,
            "top_k": self.top_k,
            "include_metadata": True,
        }
        if self.metadata_filter:
            query_kwargs["filter"] = self.metadata_filter

        response = self.index.query(**query_kwargs)

        docs = []
        for match in response["matches"]:
            metadata = dict(match.get("metadata") or {})
            text = metadata.pop("text", "")
            docs.append(LCDocument(page_content=text, metadata=metadata))
        return docs


def get_hybrid_retriever(document_ids=None, k=7, alpha=0.5):
    """
    Returns a hybrid retriever filtered to the given document_ids.
    alpha=0: pure sparse/BM25 keyword, alpha=1: pure dense/semantic.
    """
    metadata_filter = None
    if document_ids:
        metadata_filter = {"document_id": {"$in": [str(d) for d in document_ids]}}

    return _HybridRetriever(
        embeddings=get_embeddings_instance(),
        sparse_encoder=get_bm25_encoder(),
        index=get_pinecone_index(),
        top_k=k,
        alpha=alpha,
        metadata_filter=metadata_filter,
    )


def create_vector_index(document_id, user_id, langchain_documents):
    """
    Upserts document chunks with both dense (OpenAI) and sparse (BM25) vectors to Pinecone.
    Requires a Pinecone index created with metric='dotproduct'.
    """
    try:
        embeddings = get_embeddings_instance()
        bm25 = get_bm25_encoder()
        index = get_pinecone_index()

        texts = [doc.page_content for doc in langchain_documents]
        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = bm25.encode_documents(texts)

        vectors = []
        for i, (doc, dense, sparse) in enumerate(zip(langchain_documents, dense_vectors, sparse_vectors)):
            vectors.append({
                "id": f"{document_id}_{i}",
                "values": dense,
                "sparse_values": sparse,
                "metadata": {
                    **doc.metadata,
                    "document_id": str(document_id),
                    "user_id": str(user_id),
                    "text": doc.page_content,  # required by _HybridRetriever to reconstruct page_content
                },
            })

        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            index.upsert(vectors=vectors[i:i + batch_size])

        logger.info(f"Upserted {len(vectors)} hybrid vectors for document {document_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to upsert hybrid vectors for document {document_id}: {e}")
        raise


def delete_vector_index(document_id):
    """Deletes all chunks for a document from Pinecone."""
    try:
        index = get_pinecone_index()
        index.delete(filter={"document_id": str(document_id)})
        logger.info(f"Deleted vectors for document {document_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete vectors for document {document_id}: {e}")
        return False


def _format_search_result(doc):
    meta = doc.metadata
    return {
        "text": doc.page_content,
        "page": meta.get("page_label", meta.get("page", 1)),
        "source": meta.get("title", meta.get("source", "Unknown")),
    }


def _deduplicate_by_page(docs, limit=10):
    """Keep only the first (highest-scored) chunk per (document_id, page) pair."""
    seen = set()
    unique = []
    for doc in docs:
        meta = doc.metadata
        key = (meta.get("document_id", ""), meta.get("page_label", meta.get("page", "")))
        if key not in seen:
            seen.add(key)
            unique.append(doc)
        if len(unique) >= limit:
            break
    return unique


def keyword_search_in_vectors(query, document_ids=None):
    """
    Hybrid keyword search (alpha=0.3) — BM25 word matching boosted by light
    semantic ranking so the most relevant chunk surfaces above noise.
    Deduplicates results to one chunk per page.
    Returns list of dicts: [{'text': str, 'page': int, 'source': str}]
    """
    if not document_ids:
        return []
    try:
        # Fetch extra candidates before deduplication
        retriever = get_hybrid_retriever(document_ids=document_ids, k=20, alpha=0.3)
        docs = retriever.invoke(query)
        unique = _deduplicate_by_page(docs, limit=10)
        return [_format_search_result(doc) for doc in unique]
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return []


def phrase_search_in_vectors(query, document_ids=None):
    """
    Exact phrase search — BM25 retrieves candidates, post-filters for the
    exact phrase (case-insensitive), then deduplicates by page.
    Falls back to deduplicated BM25 results if no exact match is found.
    Returns list of dicts: [{'text': str, 'page': int, 'source': str}]
    """
    if not document_ids:
        return []
    try:
        retriever = get_hybrid_retriever(document_ids=document_ids, k=30, alpha=0)
        candidates = retriever.invoke(query)

        phrase = query.lower().strip()
        exact_matches = [doc for doc in candidates if phrase in doc.page_content.lower()]

        results = exact_matches if exact_matches else candidates
        unique = _deduplicate_by_page(results, limit=10)
        return [_format_search_result(doc) for doc in unique]
    except Exception as e:
        logger.error(f"Phrase search failed: {e}")
        return []
