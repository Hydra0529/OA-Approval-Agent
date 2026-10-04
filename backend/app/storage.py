from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.config import settings
from app.models.schema import ApprovalCase, ProcessTemplate


def ensure_data_dirs() -> None:
    for d in (
        settings.data_dir,
        settings.policies_dir,
        settings.templates_dir,
        settings.cases_dir,
        settings.eval_dir,
        settings.chroma_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)


def generated_dir() -> Path:
    d = settings.data_dir / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_yaml_templates(folder: Path) -> list[ProcessTemplate]:
    items: list[ProcessTemplate] = []
    if not folder.exists():
        return items
    for path in sorted(folder.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data:
            items.append(ProcessTemplate.model_validate(data))
    return items


def load_templates() -> list[ProcessTemplate]:
    """Canonical / learned templates shown in the library dropdown."""
    ensure_data_dirs()
    return _load_yaml_templates(settings.templates_dir)


def load_all_templates() -> list[ProcessTemplate]:
    """Library templates plus per-case generated plans (for engine / calendar)."""
    ensure_data_dirs()
    items = load_templates()
    seen = {t.id for t in items}
    for t in _load_yaml_templates(generated_dir()):
        if t.id not in seen:
            items.append(t)
            seen.add(t.id)
    return items


def get_template(template_id: str) -> ProcessTemplate | None:
    for t in load_all_templates():
        if t.id == template_id:
            return t
    return None


def save_template(template: ProcessTemplate) -> Path:
    ensure_data_dirs()
    folder = generated_dir() if str(template.id).startswith("dyn-") else settings.templates_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{template.id}.yaml"
    path.write_text(
        yaml.safe_dump(
            template.model_dump(),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def load_cases() -> list[ApprovalCase]:
    ensure_data_dirs()
    items: list[ApprovalCase] = []
    for path in sorted(settings.cases_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append(ApprovalCase.model_validate(data))
    return items


def get_case(case_id: str) -> ApprovalCase | None:
    for c in load_cases():
        if c.case_id == case_id:
            return c
    return None


def save_case(case: ApprovalCase) -> Path:
    ensure_data_dirs()
    path = settings.cases_dir / f"{case.case_id}.json"
    path.write_text(
        case.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path


def delete_case(case_id: str) -> bool:
    """Remove a case JSON and its generated per-case template, if any."""
    ensure_data_dirs()
    cid = (case_id or "").strip()
    if not cid:
        return False
    path = settings.cases_dir / f"{cid}.json"
    if not path.exists():
        return False
    template_id = ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        template_id = str(data.get("template_id") or "")
    except (OSError, json.JSONDecodeError):
        template_id = ""
    path.unlink(missing_ok=True)
    generated = generated_dir()
    candidates = [generated / f"dyn-{cid}.yaml"]
    if template_id.startswith("dyn-"):
        candidates.append(generated / f"{template_id}.yaml")
    for yaml_path in candidates:
        yaml_path.unlink(missing_ok=True)
    return True


def list_policy_files() -> list[dict]:
    ensure_data_dirs()
    return [
        {
            "filename": p.name,
            "size": p.stat().st_size,
            "path": str(p),
        }
        for p in sorted(settings.policies_dir.glob("*.pdf"))
    ]
