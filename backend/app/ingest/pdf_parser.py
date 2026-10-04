from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(path)
    parts: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        parts.append(f"\n--- 第{i + 1}页 ---\n{text}")
    doc.close()
    return "\n".join(parts).strip()


def chunk_text(
    text: str,
    source: str,
    max_chars: int = 800,
    overlap: int = 120,
) -> list[dict]:
    # Split by chapter-like headings first
    sections = re.split(r"(?=\n第[一二三四五六七八九十0-9]+[章节条]\s*)", text)
    chunks: list[dict] = []
    idx = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chars:
            chunks.append(
                {
                    "id": f"{source}::{idx}",
                    "text": section,
                    "source": source,
                    "meta": {"chunk_index": idx},
                }
            )
            idx += 1
            continue
        start = 0
        while start < len(section):
            end = min(start + max_chars, len(section))
            piece = section[start:end].strip()
            if piece:
                chunks.append(
                    {
                        "id": f"{source}::{idx}",
                        "text": piece,
                        "source": source,
                        "meta": {"chunk_index": idx},
                    }
                )
                idx += 1
            if end >= len(section):
                break
            start = max(0, end - overlap)
    return chunks
