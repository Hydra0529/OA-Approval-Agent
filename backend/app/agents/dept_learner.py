from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.config import settings
from app.ingest.pdf_parser import extract_pdf_text
from app.org_store import load_departments, save_departments

# 制度里常见写法 → 统一部门名称 / id
ALIASES: dict[str, tuple[str, str, int]] = {
    "财务部": ("finance", "财务部", 3),
    "财务": ("finance", "财务部", 3),
    "财务管理中心": ("finance", "财务部", 3),
    "集团财务管理中心": ("finance", "财务部", 3),
    "采购部": ("procurement", "采购部", 2),
    "采购": ("procurement", "采购部", 2),
    "法务部": ("legal", "法务部", 2),
    "法务": ("legal", "法务部", 2),
    "法律部": ("legal", "法务部", 2),
    "总经办": ("gm_office", "总经办", 1),
    "总经理办公室": ("gm_office", "总经办", 1),
    "总裁办": ("gm_office", "总经办", 1),
    "人力资源部": ("hr", "人力资源部", 2),
    "人力部": ("hr", "人力资源部", 2),
    "人事部": ("hr", "人力资源部", 2),
    "人资部": ("hr", "人力资源部", 2),
    "行政部": ("admin", "行政部", 2),
    "综合部": ("admin", "行政部", 2),
    "综合管理部": ("admin", "行政部", 2),
    "市场部": ("market", "市场部", 3),
    "营销部": ("market", "市场部", 3),
    "销售部": ("market", "市场部", 3),
    "研发部": ("rd", "研发部", 3),
    "技术部": ("rd", "研发部", 3),
    "信息技术部": ("it", "信息技术部", 2),
    "信息部": ("it", "信息技术部", 2),
    "IT部": ("it", "信息技术部", 2),
    "信息化部": ("it", "信息技术部", 2),
    "人力资源管理中心": ("hr", "人力资源部", 2),
    "集团人力资源管理中心": ("hr", "人力资源部", 2),
    "法律事务管理中心": ("legal", "法务部", 2),
    "集团法律事务管理中心": ("legal", "法务部", 2),
    "公共关系与行政管理中心": ("admin", "行政部", 2),
    "公共事务与行政管理中心": ("admin", "行政部", 2),
    "信息管理中心": ("it", "信息技术部", 2),
    "集总室": ("gm_office", "总经办", 1),
    "董事长办公室": ("gm_office", "总经办", 1),
}

SKIP = {
    "各部门",
    "有关部门",
    "本部门",
    "所在部门",
    "上级部门",
    "主管部门",
    "业务部门",
    "职能部门",
    "相关部门",
    "归口部门",
    "审批部门",
    "对口部门",
    "承办部门",
    "使用部门",
    "需求部门",
    "申请部门",
    "责任部门",
    "其他部门",
    "内部",
    "外部",
    "全部",
    "本部",
    "干部",
    "总部",
    "局部",
}

ROLE_HINTS = {
    "财务专员": "财务部",
    "财务负责人": "财务部",
    "出纳": "财务部",
    "采购专员": "采购部",
    "法务专员": "法务部",
    "HR专员": "人力资源部",
    "行政专员": "行政部",
    "总经理": "总经办",
}

DEPT_RE = re.compile(
    r"(?:由|经|报)((?:集团)?[\u4e00-\u9fff]{2,6}(?:部|中心)|总经办|总裁办)|"
    r"((?:集团)?[\u4e00-\u9fff]{2,6}(?:部|中心)|总经办|总裁办)(?:负责|审核|审批|备案|复核|审定)"
)


def _canon(raw: str) -> tuple[str, str, int] | None:
    name = raw.strip()
    if name in SKIP or len(name) < 2:
        return None
    if any(bad in name for bad in ("各", "有关", "所在", "上级", "主管", "相关", "归口", "对口", "办法", "规定", "细则")):
        return None
    if not name.endswith(("部", "中心", "办公室", "办")):
        return None
    if name.endswith("办") and name not in ("总经办", "总裁办", "董行办"):
        return None
    if name.endswith("门") and name not in ALIASES:
        return None
    if name in ALIASES:
        return ALIASES[name]
    # 去掉「集团」前缀再匹配
    stripped = name[2:] if name.startswith("集团") else name
    if stripped in ALIASES:
        return ALIASES[stripped]
    # Only mint a new roster entry for short official-looking names, not running text.
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}部", name) or re.fullmatch(r"[\u4e00-\u9fff]{2,6}(?:中心|办公室)", name):
        did = "dept_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
        return did, name, 2
    return None


def extract_department_names(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    blob = text or ""
    # Alias hits first — these are the company functions we actually calendar.
    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in blob:
            item = _canon(alias)
            if item and item[1] not in seen:
                seen.add(item[1])
                found.append(item[1])
    for m in DEPT_RE.finditer(blob):
        raw = next((g for g in m.groups() if g), "")
        item = _canon(raw)
        if not item:
            continue
        _, display, _ = item
        if display not in seen:
            seen.add(display)
            found.append(display)
    return found


PARALLEL_PATTERNS = [
    re.compile(
        r"([\u4e00-\u9fff]{2,12}(?:部|中心|办))\s*(?:的)?"
        r"(?:建议)?并行(?:工作数|上限|容量|处理数|单数)?\s*(?:为|是|:|：)?\s*(\d+)"
    ),
    re.compile(
        r"([\u4e00-\u9fff]{2,12}(?:部|中心|办)).{0,16}"
        r"同时(?:处理|审批|办理)不超过\s*(\d+)"
    ),
]


def extract_parallel_limits(text: str) -> list[tuple[str, int]]:
    """Read '研发部建议并行工作数为1' style clauses from policy text."""
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    blob = text or ""
    for pat in PARALLEL_PATTERNS:
        for m in pat.finditer(blob):
            raw, num = m.group(1), m.group(2)
            item = _canon(raw)
            if not item:
                continue
            _, display, _ = item
            limit = max(1, min(20, int(num)))
            if display in seen:
                continue
            seen.add(display)
            found.append((display, limit))
    return found


def apply_parallel_limits(pairs: list[tuple[str, int]], source: str = "") -> list[str]:
    """Create or update department parallel_limit so calendar reflects policy edits."""
    if not pairs:
        return []
    current = {d["id"]: dict(d) for d in load_departments()}
    by_name = {d["name"]: d for d in current.values()}
    changed: list[str] = []
    for raw, limit in pairs:
        item = _canon(raw)
        if not item:
            continue
        did, display, _default = item
        rec = by_name.get(display)
        if rec is None:
            rec = current.get(did)
        if rec is None:
            rec = {
                "id": did,
                "name": display,
                "parallel_limit": limit,
                "source": source,
            }
            current[did] = rec
            by_name[display] = rec
            changed.append(f"{display}→{limit}")
            continue
        if int(rec.get("parallel_limit") or 0) != limit:
            rec["parallel_limit"] = limit
            rec["source"] = source
            changed.append(f"{display}→{limit}")
    save_departments(list(current.values()))
    return changed


def merge_departments(names: list[str], source: str = "") -> list[dict]:
    current = {d["id"]: dict(d) for d in load_departments()}
    by_name = {d["name"]: d for d in current.values()}
    added: list[str] = []
    for raw in names:
        item = _canon(raw)
        if not item:
            continue
        did, display, limit = item
        if display in by_name:
            continue
        if did in current:
            continue
        rec = {
            "id": did,
            "name": display,
            "parallel_limit": limit,
            "source": source,
        }
        current[did] = rec
        by_name[display] = rec
        added.append(display)
    save_departments(list(current.values()))
    return added


def sync_departments_from_policies() -> dict:
    """Scan all policy PDFs and refresh the company department roster."""
    names: list[str] = []
    files: list[str] = []
    for path in sorted(settings.policies_dir.glob("*.pdf")):
        files.append(path.name)
        try:
            text = extract_pdf_text(path)
        except Exception:
            continue
        names.extend(extract_department_names(text + "\n" + path.name))
    added = merge_departments(names, source="policy_scan")
    pairs: list[tuple[str, int]] = []
    for path in sorted(settings.policies_dir.glob("*.pdf")):
        try:
            text = extract_pdf_text(path)
        except Exception:
            continue
        pairs.extend(extract_parallel_limits(text))
    updated = apply_parallel_limits(pairs, source="policy_scan")
    return {
        "files": len(files),
        "added": added,
        "parallel_updated": updated,
        "departments": load_departments(),
    }
