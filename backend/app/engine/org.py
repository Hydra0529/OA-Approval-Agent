from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from app.org_store import load_departments

if TYPE_CHECKING:
    from app.models.schema import ApprovalCase, ProcessTemplate

ROLE_DEPT: dict[str, str] = {
    "财务专员": "finance",
    "财务负责人": "finance",
    "出纳": "finance",
    "采购专员": "procurement",
    "法务专员": "legal",
    "总经理": "gm_office",
    "董事长": "gm_office",
    "HR专员": "hr",
    "行政专员": "admin",
}

DEPT_NAME_ID: dict[str, str] = {
    "财务部": "finance",
    "采购部": "procurement",
    "法务部": "legal",
    "总经办": "gm_office",
    "人力资源部": "hr",
    "行政部": "admin",
    "市场部": "market",
    "研发部": "rd",
    "信息技术部": "it",
}


def departments_by_id() -> dict[str, dict]:
    return {d["id"]: d for d in load_departments()}


def role_department_id(role: str, applicant_dept: str) -> str:
    if role in ROLE_DEPT:
        return ROLE_DEPT[role]
    depts = load_departments()
    by_name = {d["name"]: d["id"] for d in depts}
    if applicant_dept in by_name:
        return by_name[applicant_dept]
    if role in by_name:
        return by_name[role]
    return by_name.get("行政部", depts[0]["id"] if depts else "admin")


def load_level(load: int, limit: int) -> str:
    if limit <= 0:
        return "busy"
    if load <= 0:
        return "idle"
    if load < limit:
        return "busy" if load * 2 >= limit else "idle"
    return "saturated"


def overflow_delay(load: int, limit: int) -> int:
    return max(0, load - limit)


def occupancy_windows(case, template) -> list[tuple[date, date, str, str]]:
    """(start, end_inclusive, dept_id, case_id) for each node window."""
    from app.engine.monitor import add_business_days, resolve_path

    path = resolve_path(template, case)
    if not path:
        return []
    cursor = case.submit_at.date()
    windows: list[tuple[date, date, str, str]] = []
    for node in path:
        start = cursor
        sla_end = add_business_days(start, max(node.sla_days, 1))
        end = sla_end
        if case.status == "running" and node.id == case.current_node:
            today = date.today()
            if (today - start).days <= 45:
                end = max(end, today)
        dept_id = role_department_id(node.role, case.dept)
        windows.append((start, end, dept_id, case.case_id))
        cursor = sla_end
        if node.id == case.current_node:
            break
    return windows


def occupancy_on(
    day: date,
    cases: list,
    templates: dict,
) -> dict[str, list]:
    """dept_id -> list of {case_id, title, node-ish} occupying that day."""
    occ: dict[str, list] = {d["id"]: [] for d in load_departments()}
    for case in cases:
        tmpl = templates.get(case.template_id)
        if not tmpl:
            continue
        for start, end, dept_id, cid in occupancy_windows(case, tmpl):
            if start <= day <= end:
                occ.setdefault(dept_id, []).append(
                    {
                        "case_id": cid,
                        "title": case.title,
                        "dept": case.dept,
                        "status": case.status,
                    }
                )
    return occ


def calendar_day(day: date, cases: list, templates: dict) -> dict:
    occ = occupancy_on(day, cases, templates)
    depts = []
    worst = "idle"
    rank = {"idle": 0, "busy": 1, "saturated": 2}
    for d in load_departments():
        items = occ.get(d["id"], [])
        # unique by case_id
        seen = set()
        uniq = []
        for it in items:
            if it["case_id"] in seen:
                continue
            seen.add(it["case_id"])
            uniq.append(it)
        load = len(uniq)
        level = load_level(load, d["parallel_limit"])
        if rank[level] > rank[worst]:
            worst = level
        depts.append(
            {
                "id": d["id"],
                "name": d["name"],
                "parallel_limit": d["parallel_limit"],
                "load": load,
                "level": level,
                "delay_days": overflow_delay(load, d["parallel_limit"]),
                "cases": uniq,
            }
        )
    return {"date": day.isoformat(), "overall": worst, "departments": depts}


def case_current_dept_load(case, template, cases, templates, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    node = next((n for n in template.nodes if n.id == case.current_node), None)
    role = node.role if node else ""
    dept_id = role_department_id(role, case.dept)
    day = calendar_day(as_of, cases, templates)
    for d in day["departments"]:
        if d["id"] == dept_id:
            return d
    return {
        "id": dept_id,
        "name": dept_id,
        "parallel_limit": 2,
        "load": 0,
        "level": "idle",
        "delay_days": 0,
        "cases": [],
    }
