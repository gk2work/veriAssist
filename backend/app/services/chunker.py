"""
VeriAssist v2.0 — Hybrid Document Chunker

Different document types need different chunking strategies:
- Documentation (UVM manual, SV LRM): section-heading based with overlap
- SVA patterns: each property/sequence = one chunk with metadata
- SystemVerilog code: class/module boundary chunking
- Markdown reference files: heading-based splitting

Standard chunking destroys context. This chunker preserves it.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger("veriassist.chunker")


@dataclass
class Chunk:
    """A single chunk of text with metadata for ChromaDB storage."""
    text: str
    metadata: dict = field(default_factory=dict)

    # Metadata fields:
    # - source: filename or document name
    # - doc_type: "uvm_docs" | "sv_lrm" | "sva_patterns" | "tool_docs" | "code"
    # - section: heading/section name
    # - page: page number (if from PDF)
    # - chunk_index: position within document
    # - constructs: list of SVA constructs used (for sva_patterns)
    # - protocol: protocol name if applicable (axi, ahb, apb, etc)


# ═══════════════════════════════════════════════════════════════
# HEADING-BASED SPLITTER (for markdown docs and general text)
# ═══════════════════════════════════════════════════════════════

def chunk_by_headings(
    text: str,
    source: str,
    doc_type: str = "docs",
    max_chunk_tokens: int = 512,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """
    Split text by markdown headings (## or ###).
    Each section becomes a chunk. Sections exceeding max_chunk_tokens
    are further split with overlap.
    """
    # Split on markdown headings (## and ###)
    heading_pattern = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)

    sections = []
    last_end = 0
    current_heading = "Introduction"

    for match in heading_pattern.finditer(text):
        # Save previous section
        section_text = text[last_end:match.start()].strip()
        if section_text:
            sections.append((current_heading, section_text))

        current_heading = match.group(2).strip()
        last_end = match.end()

    # Last section
    remaining = text[last_end:].strip()
    if remaining:
        sections.append((current_heading, remaining))

    # Convert sections to chunks (split large ones)
    chunks = []
    for idx, (heading, body) in enumerate(sections):
        if not body or len(body.split()) < 10:
            continue

        # Prepend heading to body for context
        full_text = f"## {heading}\n\n{body}"
        approx_tokens = len(full_text.split()) * 1.3  # rough estimate

        if approx_tokens <= max_chunk_tokens:
            chunks.append(Chunk(
                text=full_text,
                metadata={
                    "source": source,
                    "doc_type": doc_type,
                    "section": heading,
                    "chunk_index": len(chunks),
                }
            ))
        else:
            # Split large sections into sub-chunks with overlap
            sub_chunks = _split_with_overlap(full_text, max_chunk_tokens, overlap_tokens)
            for i, sc in enumerate(sub_chunks):
                chunks.append(Chunk(
                    text=sc,
                    metadata={
                        "source": source,
                        "doc_type": doc_type,
                        "section": f"{heading} (part {i+1})",
                        "chunk_index": len(chunks),
                    }
                ))

    logger.info(f"Chunked '{source}' into {len(chunks)} chunks (heading-based)")
    return chunks


# ═══════════════════════════════════════════════════════════════
# SVA PATTERN CHUNKER (each property = one chunk)
# ═══════════════════════════════════════════════════════════════

# SVA constructs we tag in metadata for filtered retrieval
SVA_CONSTRUCTS = {
    r'\|->': 'overlapping_implication',
    r'\|=>': 'non_overlapping_implication',
    r'##\d+': 'fixed_delay',
    r'##\[\d+:\d+\]': 'range_delay',
    r'\[\*\d*:?\d*\]': 'repetition',
    r'\[->\d+\]': 'goto_repetition',
    r'\[=\d+\]': 'nonconsec_repetition',
    r'\$rose': 'rose',
    r'\$fell': 'fell',
    r'\$stable': 'stable',
    r'\$changed': 'changed',
    r'disable\s+iff': 'disable_iff',
    r'throughout': 'throughout',
}

# Known protocol keywords
PROTOCOL_KEYWORDS = {
    'axi': ['axi', 'awvalid', 'awready', 'wvalid', 'wready', 'bvalid', 'bready',
            'arvalid', 'arready', 'rvalid', 'rready', 'amba'],
    'ahb': ['ahb', 'hready', 'htrans', 'hburst', 'hsize', 'hwrite', 'hsel'],
    'apb': ['apb', 'psel', 'penable', 'pready', 'pwrite', 'paddr'],
    'spi': ['spi', 'sclk', 'mosi', 'miso', 'cs_n', 'ss_n'],
    'i2c': ['i2c', 'scl', 'sda', 'start', 'stop', 'ack', 'nack'],
    'uart': ['uart', 'tx', 'rx', 'baud', 'parity', 'start_bit', 'stop_bit'],
    'fifo': ['fifo', 'wr_en', 'rd_en', 'full', 'empty', 'overflow', 'underflow'],
}


def chunk_sva_patterns(
    text: str,
    source: str,
) -> list[Chunk]:
    """
    Split SVA pattern files. Each pattern block (delimited by markdown
    headings or blank-line-separated property blocks) becomes one chunk.

    Automatically detects SVA constructs used and protocol type,
    storing them as metadata for filtered retrieval.
    """
    # Split by markdown headings (### Pattern: ...)
    pattern_blocks = re.split(r'\n(?=###?\s)', text)

    chunks = []
    for block in pattern_blocks:
        block = block.strip()
        if not block or len(block) < 30:
            continue

        # Extract heading if present
        heading_match = re.match(r'^#{1,4}\s+(.+)$', block, re.MULTILINE)
        heading = heading_match.group(1) if heading_match else "SVA Pattern"

        # Detect constructs used
        constructs = []
        for pattern, name in SVA_CONSTRUCTS.items():
            if re.search(pattern, block):
                constructs.append(name)

        # Detect protocol
        protocol = _detect_protocol(block)

        # Check sva2sby compatibility (no banned constructs)
        banned = [r'\$past', r'first_match', r'\bintersect\b', r'\bwithin\b', r'\[\*\]', r'\[\+\]']
        sva2sby_compatible = not any(re.search(b, block) for b in banned)

        chunks.append(Chunk(
            text=block,
            metadata={
                "source": source,
                "doc_type": "sva_patterns",
                "section": heading,
                "chunk_index": len(chunks),
                "constructs": ",".join(constructs),
                "protocol": protocol,
                "sva2sby_compatible": str(sva2sby_compatible),
            }
        ))

    logger.info(f"Chunked '{source}' into {len(chunks)} SVA pattern chunks")
    return chunks


def _detect_protocol(text: str) -> str:
    """Detect which protocol an SVA pattern targets based on signal names."""
    text_lower = text.lower()
    scores = {}
    for proto, keywords in PROTOCOL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[proto] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"


# ═══════════════════════════════════════════════════════════════
# SYSTEMVERILOG CODE CHUNKER (class/module boundaries)
# ═══════════════════════════════════════════════════════════════

def chunk_sv_code(
    text: str,
    source: str,
) -> list[Chunk]:
    """
    Split SystemVerilog code by module/class/interface boundaries.
    Each module, class, or interface becomes a single chunk regardless
    of size — preserving full context for code generation RAG.
    """
    # Match module...endmodule, class...endclass, interface...endinterface
    block_pattern = re.compile(
        r'((?:module|class|interface|package)\s+\w+[\s\S]*?'
        r'(?:endmodule|endclass|endinterface|endpackage))',
        re.MULTILINE
    )

    chunks = []
    matches = list(block_pattern.finditer(text))

    if not matches:
        # No module/class boundaries found — treat as single chunk
        if len(text.strip()) > 50:
            chunks.append(Chunk(
                text=text.strip(),
                metadata={
                    "source": source,
                    "doc_type": "code",
                    "section": "full_file",
                    "chunk_index": 0,
                }
            ))
        return chunks

    for match in matches:
        block = match.group(0).strip()

        # Extract block name
        name_match = re.match(r'(module|class|interface|package)\s+(\w+)', block)
        block_name = name_match.group(2) if name_match else "unknown"
        block_type = name_match.group(1) if name_match else "block"

        chunks.append(Chunk(
            text=block,
            metadata={
                "source": source,
                "doc_type": "code",
                "section": f"{block_type}:{block_name}",
                "chunk_index": len(chunks),
                "block_type": block_type,
                "block_name": block_name,
            }
        ))

    logger.info(f"Chunked '{source}' into {len(chunks)} code blocks")
    return chunks


# ═══════════════════════════════════════════════════════════════
# PDF TEXT CHUNKER (page-aware)
# ═══════════════════════════════════════════════════════════════

def chunk_pdf_text(
    pages: list[tuple[int, str]],  # [(page_num, text), ...]
    source: str,
    doc_type: str = "docs",
    max_chunk_tokens: int = 512,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """
    Chunk extracted PDF text. Tries heading-based splitting first.
    Falls back to page-based splitting if no headings found.
    Each chunk retains page number in metadata.
    """
    # Combine all pages
    full_text = "\n\n".join(text for _, text in pages)

    # Check if document has markdown-style headings
    has_headings = bool(re.search(r'^#{1,4}\s+', full_text, re.MULTILINE))

    if has_headings:
        return chunk_by_headings(full_text, source, doc_type, max_chunk_tokens, overlap_tokens)

    # Fall back to page-based chunking with overlap
    chunks = []
    for page_num, page_text in pages:
        page_text = page_text.strip()
        if not page_text or len(page_text.split()) < 15:
            continue

        approx_tokens = len(page_text.split()) * 1.3

        if approx_tokens <= max_chunk_tokens:
            chunks.append(Chunk(
                text=page_text,
                metadata={
                    "source": source,
                    "doc_type": doc_type,
                    "section": f"page_{page_num}",
                    "page": str(page_num),
                    "chunk_index": len(chunks),
                }
            ))
        else:
            sub_chunks = _split_with_overlap(page_text, max_chunk_tokens, overlap_tokens)
            for i, sc in enumerate(sub_chunks):
                chunks.append(Chunk(
                    text=sc,
                    metadata={
                        "source": source,
                        "doc_type": doc_type,
                        "section": f"page_{page_num}_part_{i+1}",
                        "page": str(page_num),
                        "chunk_index": len(chunks),
                    }
                ))

    logger.info(f"Chunked PDF '{source}' into {len(chunks)} chunks (page-based)")
    return chunks


# ═══════════════════════════════════════════════════════════════
# AUTO-DETECT CHUNKER (routes to the right strategy)
# ═══════════════════════════════════════════════════════════════

def chunk_file(filepath: str, doc_type: Optional[str] = None) -> list[Chunk]:
    """
    Auto-detect file type and apply the right chunking strategy.

    Routing logic:
    - .md files with 'sva_pattern' or 'assertion' in name → SVA pattern chunker
    - .md files → heading-based chunker
    - .sv / .svh / .v files → SV code chunker
    - .pdf files → PDF text chunker
    - .txt files → heading-based chunker
    """
    path = Path(filepath)
    source = path.name
    suffix = path.suffix.lower()
    name_lower = path.stem.lower()

    text = None

    if suffix == ".pdf":
        # Extract text from PDF
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                pages.append((i + 1, page_text))

            dt = doc_type or _guess_doc_type(source)
            return chunk_pdf_text(pages, source, dt)
        except Exception as e:
            logger.error(f"Failed to read PDF {filepath}: {e}")
            return []

    # Read text files
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return []

    if not text.strip():
        return []

    # Route to appropriate chunker
    if suffix in (".sv", ".svh", ".v", ".vh"):
        return chunk_sv_code(text, source)

    if suffix == ".md" and any(kw in name_lower for kw in ["sva_pattern", "assertion", "sva_"]):
        return chunk_sva_patterns(text, source)

    dt = doc_type or _guess_doc_type(source)
    return chunk_by_headings(text, source, dt)


def _guess_doc_type(filename: str) -> str:
    """Guess doc_type from filename."""
    name = filename.lower()
    if "uvm" in name:
        return "uvm_docs"
    if "sva" in name or "assertion" in name:
        return "sva_patterns"
    if "lrm" in name or "ieee" in name or "systemverilog" in name:
        return "sv_lrm"
    if "sby" in name or "symbiyosys" in name or "sva2sby" in name or "yosys" in name:
        return "tool_docs"
    return "docs"


# ═══════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════

def _split_with_overlap(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 100,
) -> list[str]:
    """Split text into chunks of ~max_tokens words with overlap."""
    words = text.split()
    # Approximate: 1 token ≈ 0.75 words
    max_words = int(max_tokens * 0.75)
    overlap_words = int(overlap_tokens * 0.75)

    if len(words) <= max_words:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + max_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)

        if end >= len(words):
            break
        start = end - overlap_words

    return chunks