from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models.schema import ApprovalCase, ProcessTemplate
from app.storage import ensure_data_dirs


def org_dir() -> Path:
    d = settings.data_dir / "org"
    d.mkdir(parents=True, exist_ok=True)
    return d


def knowledge_dir() -> Path:
    d = settings.data_dir / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_departments() -> list[dict]:
    path = org_dir() / "departments.json"
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    return data.get("departments", []) if isinstance(data, dict) else []


def save_departments(items: list[dict]) -> Path:
    org_dir().mkdir(parents=True, exist_ok=True)
    path = org_dir() / "departments.json"
    ordered = sorted(items, key=lambda x: x.get("name", ""))
    payload = json.dumps({"departments": ordered}, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return path


def known_department_names() -> set[str]:
    return {d["name"] for d in load_departments()}


def load_knowledge() -> dict:
    path = knowledge_dir() / "functions.json"
    if not path.exists():
        return {"functions": [], "history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_knowledge(data: dict) -> Path:
    knowledge_dir().mkdir(parents=True, exist_ok=True)
    path = knowledge_dir() / "functions.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
