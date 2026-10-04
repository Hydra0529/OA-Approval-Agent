from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from app.config import settings
from app.ingest.pdf_parser import chunk_text, extract_pdf_text


def _tokenize(text: str) -> list[str]:
    # Lightweight Chinese/English tokenizer for demo RAG
    en = re.findall(r"[A-Za-z0-9_]+", text.lower())
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return en + cn


class PolicyStore:
    """File-backed lexical RAG — no remote embedding model download."""

    def __init__(self) -> None:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = settings.chroma_dir / "policy_index.json"
        self._chunks: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            self._chunks = json.loads(self._index_path.read_text(encoding="utf-8"))
        else:
            self._chunks = []

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps(self._chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ingest_pdf(self, path: Path) -> int:
        text = extract_pdf_text(path)
        chunks = chunk_text(text, source=path.name)
        self._chunks = [c for c in self._chunks if c.get("source") != path.name]
        for c in chunks:
            tokens = _tokenize(c["text"])
            c["tf"] = dict(Counter(tokens))
            c["len"] = len(tokens) or 1
        self._chunks.extend(chunks)
        self._save()
        return len(chunks)

    def ingest_all(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for path in sorted(settings.policies_dir.glob("*.pdf")):
            result[path.name] = self.ingest_pdf(path)
        return result

    def count(self) -> int:
        return len(self._chunks)

    def query(self, question: str, top_k: int = 5) -> list[dict]:
        if not self._chunks:
            return []
        q_tokens = _tokenize(question)
        if not q_tokens:
            return []
        q_tf = Counter(q_tokens)
        scored: list[tuple[float, dict]] = []
        for c in self._chunks:
            tf: dict = c.get("tf") or {}
            score = 0.0
            for t, qf in q_tf.items():
                if t in tf:
                    # tf-idf-ish: raw tf * log dampening
                    score += qf * (1.0 + math.log(1 + tf[t]))
            # Prefer shorter dense hits slightly
            score = score / math.sqrt(c.get("len", 1))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[dict] = []
        for score, c in scored[:top_k]:
            out.append(
                {
                    "id": c["id"],
                    "text": c["text"],
                    "source": c.get("source", ""),
                    "meta": c.get("meta") or {},
                    "score": round(score, 4),
                }
            )
        return out


_store: PolicyStore | None = None


def get_policy_store() -> PolicyStore:
    global _store
    if _store is None:
        _store = PolicyStore()
    return _store
