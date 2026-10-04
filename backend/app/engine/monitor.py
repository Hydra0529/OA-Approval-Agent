from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.models.schema import (
    ApprovalCase,
    PortfolioItem,
    ProcessNode,
    ProcessTemplate,
    TimelineStep,
)


def _eval_condition(expr: str, ctx: dict[str, Any]) -> bool:
    if not expr or not expr.strip():
        return True
    safe_builtins: dict[str, Any] = {
        "True": True,
        "False": False,
        "None": None,
        "abs": abs,
        "min": min,
        "max": max,
    }
    try:
        return bool(eval(expr, {"__builtins__": safe_builtins}, ctx))  # noqa: S307
    except Exception:
        return False


def _case_context(case: ApprovalCase) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "amount": case.amount,
        "dept": case.dept,
        "level": case.level,
        "category": case.category,
        **case.fields,
    }
    return ctx


def resolve_path(template: ProcessTemplate, case: ApprovalCase) -> list[ProcessNode]:
    """Resolve linear path including conditional gateway insertions."""
    node_map = {n.id: n for n in template.nodes}
    # Build adjacency from edges (unconditional preferred order)
    adj: dict[str, list[tuple[str, str | None]]] = {}
    for e in template.edges:
        adj.setdefault(e.source, []).append((e.target, e.condition))

    start = template.nodes[0].id if template.nodes else None
    if not start:
        return []

    ctx = _case_context(case)
    path: list[ProcessNode] = []
    current = start
    visited: set[str] = set()

    while current and current not in visited:
        visited.add(current)
        node = node_map.get(current)
        if not node:
            break
        path.append(node)

        # Gateway overrides: if condition matches, jump to then
        jumped = False
        for gw in template.gateways:
            # Apply gateway when we are at a node that can branch — match by
            # checking if current has an edge that the gateway affects, or
            # gateway.id equals current, or when evaluating after current.
            if gw.id == current or gw.id == f"gw_after_{current}":
                if _eval_condition(gw.when, ctx):
                    current = gw.then
                    jumped = True
                    break
                if gw.else_to:
                    current = gw.else_to
                    jumped = True
                    break
        if jumped:
            continue

        outs = adj.get(current, [])
        next_id: str | None = None
        for target, cond in outs:
            if cond is None or _eval_condition(cond, ctx):
                next_id = target
                break
        # Prefer unconditional if none matched
        if next_id is None and outs:
            for target, cond in outs:
                if cond is None:
                    next_id = target
                    break
            if next_id is None:
                next_id = outs[0][0]
        current = next_id

    return path


def add_business_days(start: date, days: int) -> date:
    if days <= 0:
        return start
    d = start
    left = days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def next_step(
    case: ApprovalCase, template: ProcessTemplate
) -> tuple[ProcessNode | None, ProcessNode | None, str]:
    path = resolve_path(template, case)
    if not path:
        return None, None, "无法解析流程路径"

    idx = next((i for i, n in enumerate(path) if n.id == case.current_node), None)
    if idx is None:
        # fallback: first node
        cur = path[0]
        nxt = path[1] if len(path) > 1 else None
    else:
        cur = path[idx]
        nxt = path[idx + 1] if idx + 1 < len(path) else None

    if case.status == "completed":
        return cur, None, f"流程已完成，末节点：{cur.name}"

    if nxt is None:
        summary = f"当前处于「{cur.name}」，由{cur.role}处理；其后无后续节点。"
        return cur, None, summary

    # Estimate arrival date for next step
    base = case.submit_at.date()
    # accumulate SLA of nodes up to and including current
    elapsed = 0
    for n in path:
        if n.id == cur.id:
            elapsed += n.sla_days
            break
        elapsed += n.sla_days
    arrive = add_business_days(base, elapsed)
    delay = 0
    try:
        from app.engine.org import case_current_dept_load
        from app.storage import load_all_templates, load_cases

        all_cases = load_cases()
        tmpls = {t.id: t for t in load_all_templates()}
        load = case_current_dept_load(case, template, all_cases, tmpls)
        delay = int(load.get("delay_days") or 0)
        arrive = add_business_days(base, elapsed + delay)
    except Exception:
        delay = 0
    extra = f"；因部门并行已满额外延迟 {delay} 个工作日" if delay else ""
    summary = (
        f"{arrive.isoformat()}，提交至{nxt.name}，由{nxt.role}进行审批"
        f"（模板 SLA {nxt.sla_days} 个工作日{extra}）。"
    )
    return cur, nxt, summary


def estimate_timeline(
    case: ApprovalCase, template: ProcessTemplate, as_of: date | None = None
) -> list[TimelineStep]:
    path = resolve_path(template, case)
    as_of = as_of or date.today()
    steps: list[TimelineStep] = []
    cursor = case.submit_at.date()
    seen_current = False
    history_ids = {h.node_id for h in case.history if h.action in ("submit", "approve")}

    for node in path:
        start = cursor
        end = add_business_days(start, max(node.sla_days, 0))
        if case.status == "completed" or node.id in history_ids or (
            not seen_current and node.id != case.current_node and _is_before_current(path, node.id, case.current_node)
        ):
            status = "done"
        elif node.id == case.current_node and case.status == "running":
            status = "current"
            seen_current = True
        else:
            status = "planned" if seen_current or node.id != case.current_node else "current"
            if node.id == case.current_node:
                seen_current = True
                status = "current"

        summary = f"{start.isoformat()} → {end.isoformat()}，{node.name}（{node.role}）"
        steps.append(
            TimelineStep(
                date=start if status != "planned" else start,
                node_id=node.id,
                node_name=node.name,
                role=node.role,
                status=status,
                summary=summary,
            )
        )
        cursor = end
    return steps


def _is_before_current(path: list[ProcessNode], node_id: str, current_id: str) -> bool:
    ids = [n.id for n in path]
    if node_id not in ids or current_id not in ids:
        return False
    return ids.index(node_id) < ids.index(current_id)


def planned_span(case: ApprovalCase, template: ProcessTemplate) -> tuple[date, date, int]:
    path = resolve_path(template, case)
    start = case.submit_at.date()
    total = sum(max(n.sla_days, 0) for n in path)
    end = add_business_days(start, total)
    # calendar days approx
    duration = (end - start).days
    return start, end, duration


def build_portfolio_item(case: ApprovalCase, template: ProcessTemplate) -> PortfolioItem:
    cur, nxt, next_summary = next_step(case, template)
    planned_start, planned_end, duration = planned_span(case, template)
    actual_start = case.submit_at.date()
    actual_end: date | None = None
    if case.status == "completed" and case.history:
        actual_end = max(h.at for h in case.history).date()
        duration = (actual_end - actual_start).days

    level = case.level or _amount_level(case.amount)
    stall_code, stall_reason, delay_days = "", "", 0
    load_level = ""
    try:
        from app.agents.stall import diagnose_stall
        from app.engine.org import case_current_dept_load
        from app.storage import load_all_templates, load_cases

        all_cases = load_cases()
        tmpls = {t.id: t for t in load_all_templates()}
        stall_code, stall_reason, delay_days = diagnose_stall(case, template, all_cases, tmpls)
        load = case_current_dept_load(case, template, all_cases, tmpls)
        load_level = load.get("level") or ""
    except Exception:
        pass

    return PortfolioItem(
        case_id=case.case_id,
        title=case.title,
        category=case.category or template.category,
        level=level,
        dept=case.dept,
        applicant=case.applicant,
        current_role=cur.role if cur else "",
        current_node_name=cur.name if cur else case.current_node,
        next_summary=next_summary,
        planned_start=planned_start,
        planned_end=planned_end,
        actual_start=actual_start,
        actual_end=actual_end,
        duration_days=duration,
        status=case.status,
        template_id=template.id,
        stall_code=stall_code,
        stall_reason=stall_reason,
        delay_days=delay_days,
        load_level=load_level,
    )


def _amount_level(amount: float) -> str:
    if amount >= 100000:
        return "一类"
    if amount >= 10000:
        return "二类"
    if amount > 0:
        return "三类"
    return "常规"
