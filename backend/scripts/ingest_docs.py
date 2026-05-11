#!/usr/bin/env python3
"""
VeriAssist v2.0 — Document Ingestion Script

Reads all documents from the docs/ folder, chunks them using the
appropriate strategy, embeds via nomic-embed-text, and stores in
ChromaDB for RAG retrieval.

Usage:
    python scripts/ingest_docs.py                    # Ingest all docs
    python scripts/ingest_docs.py --source docs/     # Specify folder
    python scripts/ingest_docs.py --reset             # Wipe and re-ingest
    python scripts/ingest_docs.py --stats             # Show collection stats
    python scripts/ingest_docs.py --file docs/sva_patterns.md  # Single file

Supported file types: .md, .txt, .pdf, .sv, .svh, .v, .vh
"""

import sys
import os
import time
import logging
import argparse
from pathlib import Path

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.chunker import chunk_file, Chunk
from app.services.rag_service import RAGService, COLLECTION_NAMES, DOC_TYPE_TO_COLLECTION, CHROMA_DIR
from app.services.embedding_service import EmbeddingServiceSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".sv", ".svh", ".v", ".vh"}


def discover_files(source_dir: str) -> list[Path]:
    """Find all supported files in the source directory."""
    source = Path(source_dir)
    if not source.exists():
        logger.error(f"Source directory not found: {source_dir}")
        logger.info(f"Create it with: mkdir -p {source_dir}")
        sys.exit(1)

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(source.rglob(f"*{ext}"))

    # Sort for consistent ordering
    files.sort()
    return files


def display_file_summary(files: list[Path], source_dir: str):
    """Print a summary of files found, grouped by type."""
    print(f"\n{'='*60}")
    print(f"  Files found in {source_dir}")
    print(f"{'='*60}")

    by_ext = {}
    for f in files:
        ext = f.suffix.lower()
        by_ext.setdefault(ext, []).append(f)

    for ext in sorted(by_ext.keys()):
        flist = by_ext[ext]
        print(f"\n  {ext} files ({len(flist)}):")
        for f in flist:
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name:40s} {size_kb:8.1f} KB")

    total_size = sum(f.stat().st_size for f in files) / 1024
    print(f"\n  Total: {len(files)} files, {total_size:.1f} KB")
    print(f"{'='*60}\n")


def ingest_single_file(
    filepath: Path,
    rag: RAGService,
    embed_fn,
    doc_type: str = None,
) -> tuple[int, int]:
    """
    Ingest a single file: chunk → embed → store.
    Returns (chunks_created, chunks_stored).
    """
    logger.info(f"Processing: {filepath.name}")

    # Chunk the file
    chunks = chunk_file(str(filepath), doc_type=doc_type)
    if not chunks:
        logger.warning(f"  No chunks generated from {filepath.name}")
        return 0, 0

    # Determine collection
    first_doc_type = chunks[0].metadata.get("doc_type", "docs")
    collection_name = DOC_TYPE_TO_COLLECTION.get(first_doc_type, "uvm_docs")

    # Ingest into ChromaDB
    stored = rag.ingest_chunks_sync(
        chunks=chunks,
        embed_fn=embed_fn,
        collection_name=collection_name,
    )

    logger.info(f"  {filepath.name}: {len(chunks)} chunks created, {stored} new chunks stored → {collection_name}")
    return len(chunks), stored


def ingest_all(source_dir: str, reset: bool = False):
    """Main ingestion pipeline."""
    t0 = time.time()

    # Discover files
    files = discover_files(source_dir)
    if not files:
        logger.error(f"No supported files found in {source_dir}")
        logger.info("Add .md, .txt, .pdf, or .sv files to the docs/ folder.")
        logger.info("Start with the curated docs we provide:")
        logger.info("  - docs/sva2sby_constructs.md")
        logger.info("  - docs/sva_patterns.md")
        logger.info("  - docs/uvm_quick_reference.md")
        sys.exit(1)

    display_file_summary(files, source_dir)

    # Initialize services
    print("Connecting to Ollama for embeddings...")
    embed = EmbeddingServiceSync()

    # Verify embedding model works
    try:
        test_emb = embed.embed_text("test connection")
        if not test_emb:
            raise ValueError("Empty embedding returned")
        print(f"  Embedding model ready (dimension: {len(test_emb)})")
    except Exception as e:
        print(f"\n  ERROR: Cannot connect to Ollama embedding model.")
        print(f"  Make sure Ollama is running and nomic-embed-text is pulled:")
        print(f"    ollama serve")
        print(f"    ollama pull nomic-embed-text")
        print(f"\n  Error: {e}")
        sys.exit(1)

    # Initialize RAG service
    rag = RAGService()

    # Reset collections if requested
    if reset:
        print("\nResetting all collections...")
        for name in COLLECTION_NAMES:
            rag.reset_collection(name)
        print("  All collections cleared.\n")

    # Ingest each file
    print("\nStarting ingestion...\n")
    total_chunks = 0
    total_stored = 0
    file_results = []

    for filepath in files:
        try:
            chunks, stored = ingest_single_file(filepath, rag, embed.embed_text)
            total_chunks += chunks
            total_stored += stored
            file_results.append((filepath.name, chunks, stored, "OK"))
        except Exception as e:
            logger.error(f"  FAILED: {filepath.name} — {e}")
            file_results.append((filepath.name, 0, 0, f"FAILED: {e}"))

    # Cleanup
    embed.close()

    # Print results
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  INGESTION COMPLETE")
    print(f"{'='*60}")
    print(f"\n  Results per file:")

    for name, chunks, stored, status in file_results:
        status_icon = "\033[92m✓\033[0m" if status == "OK" else "\033[91m✗\033[0m"
        skip_note = "" if stored == chunks else f" ({chunks - stored} skipped/duplicate)"
        print(f"    {status_icon} {name:40s} {stored:4d} chunks stored{skip_note}")

    print(f"\n  Collection sizes:")
    stats = rag.get_stats()
    for name in COLLECTION_NAMES:
        count = stats.get(name, 0)
        if count > 0:
            print(f"    {name:20s} {count:6d} chunks")
    print(f"    {'─'*30}")
    print(f"    {'TOTAL':20s} {stats.get('total', 0):6d} chunks")

    print(f"\n  Time: {elapsed:.1f}s")
    print(f"  Files processed: {len(files)}")
    print(f"  Chunks created: {total_chunks}")
    print(f"  New chunks stored: {total_stored}")
    print(f"  Duplicates skipped: {total_chunks - total_stored}")
    print(f"{'='*60}\n")


def show_stats():
    """Print current collection statistics."""
    rag = RAGService()
    stats = rag.get_stats()

    print(f"\n{'='*60}")
    print(f"  ChromaDB Collection Statistics")
    print(f"{'='*60}\n")

    for name in COLLECTION_NAMES:
        count = stats.get(name, 0)
        bar = "█" * min(count // 10, 40)
        print(f"  {name:20s} {count:6d} chunks  {bar}")

    print(f"\n  {'TOTAL':20s} {stats.get('total', 0):6d} chunks")
    print(f"\n  ChromaDB location: {CHROMA_DIR}")
    print(f"{'='*60}\n")


def ingest_single(filepath: str, doc_type: str = None):
    """Ingest a single file."""
    path = Path(filepath)
    if not path.exists():
        logger.error(f"File not found: {filepath}")
        sys.exit(1)

    print(f"\nIngesting single file: {path.name}")
    embed = EmbeddingServiceSync()

    try:
        test_emb = embed.embed_text("test")
        if not test_emb:
            raise ValueError("Empty embedding")
        print(f"  Embedding model ready (dim: {len(test_emb)})")
    except Exception as e:
        print(f"  ERROR: Ollama not available — {e}")
        sys.exit(1)

    rag = RAGService()
    chunks, stored = ingest_single_file(path, rag, embed.embed_text, doc_type)
    embed.close()

    stats = rag.get_stats()
    print(f"\n  Result: {chunks} chunks created, {stored} stored")
    print(f"  Total chunks in DB: {stats.get('total', 0)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="VeriAssist v2.0 — Document Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/ingest_docs.py                         # Ingest all docs
  python scripts/ingest_docs.py --source docs/          # Specify folder
  python scripts/ingest_docs.py --reset                  # Wipe and re-ingest all
  python scripts/ingest_docs.py --stats                  # Show collection stats
  python scripts/ingest_docs.py --file docs/sva_patterns.md  # Ingest one file
  python scripts/ingest_docs.py --file my.pdf --doc-type sv_lrm  # Override doc type
        """,
    )
    parser.add_argument(
        "--source", default="docs",
        help="Source directory containing documents (default: docs/)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Wipe all collections and re-ingest from scratch",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show current collection statistics and exit",
    )
    parser.add_argument(
        "--file", type=str,
        help="Ingest a single file instead of the whole directory",
    )
    parser.add_argument(
        "--doc-type", type=str, choices=COLLECTION_NAMES,
        help="Override the auto-detected document type",
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.file:
        ingest_single(args.file, args.doc_type)
        return

    ingest_all(args.source, args.reset)


if __name__ == "__main__":
    main()