"""
VeriAssist v2.0 — RAG Service

Core Retrieval-Augmented Generation engine.
- Stores document chunks in ChromaDB (local persistent)
- Embeds queries via Ollama nomic-embed-text
- Retrieves top-k relevant chunks with MMR diversity
- Augments LLM prompts with retrieved context + source citations

Collections:
  - uvm_docs: UVM Reference Manual, methodology guides
  - sv_lrm: SystemVerilog LRM, language reference
  - sva_patterns: SVA assertion templates with construct metadata
  - tool_docs: SymbiYosys, sva2sby, Xcelium, Jasper docs
  - code: SystemVerilog code examples
"""

import logging
import hashlib
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from app.services.embedding_service import EmbeddingService, embedding_service
from app.services.chunker import Chunk

logger = logging.getLogger("veriassist.rag")

# ChromaDB persistent storage location
CHROMA_DIR = Path(__file__).parent.parent.parent / "data" / "chromadb"

# All collections we use
COLLECTION_NAMES = ["uvm_docs", "sv_lrm", "sva_patterns", "tool_docs", "code"]

# Map doc_type to collection name
DOC_TYPE_TO_COLLECTION = {
    "uvm_docs": "uvm_docs",
    "sv_lrm": "sv_lrm",
    "sva_patterns": "sva_patterns",
    "tool_docs": "tool_docs",
    "code": "code",
    "docs": "uvm_docs",  # fallback
}

# RAG context template injected into LLM prompt
RAG_CONTEXT_TEMPLATE = """
Use the following reference material to inform your answer.
Cite the source when using specific information (e.g., "According to the UVM Reference Manual...").
If the reference material doesn't contain relevant information, rely on your own knowledge but mention that.

--- REFERENCE MATERIAL ---
{context}
--- END REFERENCE MATERIAL ---
"""

# How many chunks to retrieve per query
DEFAULT_TOP_K = 5


class RAGService:
    def __init__(
        self,
        persist_dir: str = str(CHROMA_DIR),
        embed_service: Optional[EmbeddingService] = None,
    ):
        self.persist_dir = persist_dir
        self.embed = embed_service or embedding_service
        self._client: Optional[chromadb.PersistentClient] = None
        self._collections: dict = {}

    def _get_client(self) -> chromadb.PersistentClient:
        """Lazy-initialize ChromaDB client."""
        if self._client is None:
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info(f"ChromaDB initialized at {self.persist_dir}")
        return self._client

    def _get_collection(self, name: str) -> chromadb.Collection:
        """Get or create a named collection."""
        if name not in self._collections:
            client = self._get_client()
            self._collections[name] = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    # ── Ingestion ──────────────────────────────────────────

    async def ingest_chunks(
        self,
        chunks: list[Chunk],
        collection_name: Optional[str] = None,
    ) -> int:
        """
        Embed and store chunks in ChromaDB.
        Returns number of chunks ingested.
        Skips duplicates based on content hash.
        """
        if not chunks:
            return 0

        # Determine collection
        if collection_name is None:
            doc_type = chunks[0].metadata.get("doc_type", "docs")
            collection_name = DOC_TYPE_TO_COLLECTION.get(doc_type, "uvm_docs")

        collection = self._get_collection(collection_name)

        # Prepare batch
        ids = []
        documents = []
        metadatas = []
        embeddings = []

        for chunk in chunks:
            # Generate deterministic ID from content hash (deduplication)
            chunk_id = _content_hash(chunk.text, chunk.metadata.get("source", ""))

            # Check if already exists
            existing = collection.get(ids=[chunk_id])
            if existing and existing["ids"]:
                continue

            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append(chunk.metadata)

        if not ids:
            logger.info(f"All chunks already ingested for collection '{collection_name}'")
            return 0

        # Embed all texts
        logger.info(f"Embedding {len(ids)} chunks for '{collection_name}'...")
        failed_indices = []
        for i, doc in enumerate(documents):
            try:
                # Truncate very long chunks (Ollama embedding limit)
                truncated = doc[:8000] if len(doc) > 8000 else doc
                emb = embed_fn(truncated)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(f"  Skipping chunk {i} (embed failed): {e}")
                failed_indices.append(i)
                continue
            if (i + 1) % 50 == 0:
                logger.info(f"  Embedded {i+1}/{len(documents)}")

        # Remove failed chunks from all lists
        for idx in reversed(failed_indices):
            ids.pop(idx)
            documents.pop(idx)
            metadatas.pop(idx)

        if failed_indices:
            logger.warning(f"  Skipped {len(failed_indices)} chunks due to embedding errors")

        # Store in ChromaDB
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        logger.info(f"Ingested {len(ids)} chunks into '{collection_name}' (total: {collection.count()})")
        return len(ids)

    def ingest_chunks_sync(
        self,
        chunks: list[Chunk],
        embed_fn,
        collection_name: Optional[str] = None,
    ) -> int:
        """
        Synchronous version for CLI scripts (ingest_docs.py).
        embed_fn: a function that takes str and returns list[float]
        """
        if not chunks:
            return 0

        if collection_name is None:
            doc_type = chunks[0].metadata.get("doc_type", "docs")
            collection_name = DOC_TYPE_TO_COLLECTION.get(doc_type, "uvm_docs")

        collection = self._get_collection(collection_name)

        ids = []
        documents = []
        metadatas = []
        embeddings = []

        for chunk in chunks:
            chunk_id = _content_hash(chunk.text, chunk.metadata.get("source", ""))
            existing = collection.get(ids=[chunk_id])
            if existing and existing["ids"]:
                continue

            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append(chunk.metadata)

        if not ids:
            logger.info(f"All chunks already ingested for '{collection_name}'")
            return 0

        logger.info(f"Embedding {len(ids)} chunks for '{collection_name}'...")
        failed_indices = []
        for i, doc in enumerate(documents):
            try:
                # Truncate very long chunks (Ollama embedding limit)
                truncated = doc[:8000] if len(doc) > 8000 else doc
                emb = embed_fn(truncated)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(f"  Skipping chunk {i} (embed failed): {e}")
                failed_indices.append(i)
                continue
            if (i + 1) % 50 == 0:
                logger.info(f"  Embedded {i+1}/{len(documents)}")

        # Remove failed chunks from all lists
        for idx in reversed(failed_indices):
            ids.pop(idx)
            documents.pop(idx)
            metadatas.pop(idx)

        if failed_indices:
            logger.warning(f"  Skipped {len(failed_indices)} chunks due to embedding errors")

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        logger.info(f"Ingested {len(ids)} chunks into '{collection_name}' (total: {collection.count()})")
        return len(ids)

    # ── Retrieval ──────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        collections: Optional[list[str]] = None,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        Retrieve top-k relevant chunks across one or more collections.

        Returns list of dicts:
        [
            {
                "text": "chunk content...",
                "source": "uvm_reference.pdf",
                "section": "Factory Overrides",
                "score": 0.87,
                "collection": "uvm_docs",
            },
            ...
        ]
        """
        if collections is None:
            collections = COLLECTION_NAMES

        # Embed query
        query_embedding = await self.embed.embed_text(query)
        if not query_embedding:
            logger.error("Failed to embed query")
            return []

        # Query each collection and merge results
        all_results = []

        for col_name in collections:
            try:
                collection = self._get_collection(col_name)
                if collection.count() == 0:
                    continue

                query_params = {
                    "query_embeddings": [query_embedding],
                    "n_results": min(top_k, collection.count()),
                }

                # Apply metadata filters if provided
                if filter_metadata:
                    where = {}
                    for k, v in filter_metadata.items():
                        where[k] = v
                    query_params["where"] = where

                results = collection.query(**query_params)

                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        distance = results["distances"][0][i] if results["distances"] else 1.0
                        # Convert distance to similarity score (cosine: lower distance = more similar)
                        score = 1.0 - distance

                        all_results.append({
                            "text": doc,
                            "source": meta.get("source", "unknown"),
                            "section": meta.get("section", ""),
                            "doc_type": meta.get("doc_type", ""),
                            "score": round(score, 4),
                            "collection": col_name,
                            "metadata": meta,
                        })
            except Exception as e:
                logger.warning(f"Error querying collection '{col_name}': {e}")
                continue

        # Sort by score (highest first) and take top_k
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_results = all_results[:top_k]

        if top_results:
            logger.info(
                f"Retrieved {len(top_results)} chunks for query: '{query[:60]}...' "
                f"(best score: {top_results[0]['score']:.3f} from {top_results[0]['source']})"
            )
        else:
            logger.info(f"No relevant chunks found for query: '{query[:60]}...'")

        return top_results

    # ── Prompt Augmentation ────────────────────────────────

    async def build_augmented_messages(
        self,
        query: str,
        system_prompt: str,
        history: list[dict],
        top_k: int = DEFAULT_TOP_K,
        collections: Optional[list[str]] = None,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        Build the full message list with RAG context injected.

        Returns messages ready to send to Ollama:
        [
            {"role": "system", "content": system_prompt + RAG context},
            ...history...,
            {"role": "user", "content": query}
        ]
        """
        # Retrieve relevant chunks
        results = await self.retrieve(
            query=query,
            top_k=top_k,
            collections=collections,
            filter_metadata=filter_metadata,
        )

        # Build context string with citations
        if results:
            context_parts = []
            for i, r in enumerate(results, 1):
                source_label = r["source"]
                if r["section"]:
                    source_label += f" > {r['section']}"
                context_parts.append(
                    f"[Source {i}: {source_label}]\n{r['text']}"
                )
            context_str = "\n\n".join(context_parts)
            rag_block = RAG_CONTEXT_TEMPLATE.format(context=context_str)
            augmented_system = system_prompt + "\n\n" + rag_block
        else:
            augmented_system = system_prompt

        # Build message list
        messages = [{"role": "system", "content": augmented_system}]

        # Add history (last 10 turns)
        for msg in history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # Add current query
        messages.append({"role": "user", "content": query})

        return messages

    # ── Search API (direct document search) ────────────────

    async def search(
        self,
        query: str,
        top_k: int = 10,
        collection: Optional[str] = None,
    ) -> list[dict]:
        """
        Direct document search endpoint.
        Returns chunks with scores, used by /api/docs/search.
        """
        collections = [collection] if collection else None
        return await self.retrieve(query=query, top_k=top_k, collections=collections)

    # ── Stats & Health ─────────────────────────────────────

    def get_stats(self) -> dict:
        """Get collection sizes and total chunk count."""
        stats = {}
        total = 0
        for name in COLLECTION_NAMES:
            try:
                col = self._get_collection(name)
                count = col.count()
                stats[name] = count
                total += count
            except Exception:
                stats[name] = 0
        stats["total"] = total
        return stats

    async def health(self) -> dict:
        """Health check for RAG subsystem."""
        stats = self.get_stats()
        embed_health = await self.embed.health()
        return {
            "chromadb": "available",
            "collections": stats,
            "embedding_model": embed_health,
        }

    def reset_collection(self, name: str):
        """Delete and recreate a collection. Use for re-ingestion."""
        client = self._get_client()
        try:
            client.delete_collection(name)
            logger.info(f"Deleted collection '{name}'")
        except Exception:
            pass
        self._collections.pop(name, None)
        self._get_collection(name)
        logger.info(f"Recreated collection '{name}'")


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def _content_hash(text: str, source: str) -> str:
    """Generate deterministic ID for deduplication."""
    content = f"{source}::{text[:500]}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ── RAG Decision Logic ─────────────────────────────────────

def should_use_rag(mode: str, query: str) -> bool:
    """
    Decide whether to use RAG for a given mode + query.

    - chat, docs mode: always use RAG
    - generate, sva, formal: only for informational queries
    - debug: always use RAG (error messages benefit from doc context)
    """
    always_rag_modes = {"chat", "docs", "debug"}
    if mode in always_rag_modes:
        return True

    # For generate/sva/formal: use RAG only for questions, not pure generation
    informational_signals = [
        "?",           # question mark
        "what is",     # definition query
        "what are",
        "how to",      # how-to query
        "how do",
        "explain",     # explanation request
        "difference between",
        "when to use",
        "why",
        "which",
        "can you explain",
        "tell me about",
        "describe",
    ]
    query_lower = query.lower()
    return any(signal in query_lower for signal in informational_signals)


def get_rag_collections_for_mode(mode: str) -> Optional[list[str]]:
    """
    Return which collections to search based on mode.
    None means search all collections.
    """
    mode_collections = {
        "chat": None,  # search all
        "docs": None,  # search all
        "generate": ["uvm_docs", "code"],
        "sva": ["sva_patterns", "sv_lrm", "tool_docs"],
        "formal": ["sva_patterns", "tool_docs"],
        "debug": ["uvm_docs", "sv_lrm", "tool_docs"],
    }
    return mode_collections.get(mode)


# Singleton instance (used by FastAPI backend)
rag_service = RAGService()