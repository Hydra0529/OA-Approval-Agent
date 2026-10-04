from __future__ import annotations

from app.engine.org import case_current_dept_load, load_level


def diagnose_stall(case, template, cases, templates) -> tuple[str, str, int]:
    """Return stall_code, reason text, delay_days."""
    if case.status != "running":
        return "", "流程未停滞", 0

    missing = case.fields.get("missing_docs") or []
    if isinstance(missing, str):
        missing = [missing]
    load = case_current_dept_load(case, template, cases, templates)
    delay = int(load.get("delay_days") or 0)

    if case.stall_code == "missing_docs" or missing:
        docs = "、".join(str(x) for x in missing) or (case.stall_note or "必要附件")
        return (
            "missing_docs",
            f"停滞在「{load.get('name', '')}」环节：缺少文件（{docs}），无法继续流转。",
            max(delay, 1),
        )

    if load.get("level") == "saturated" or case.stall_code == "key_person_busy":
        return (
            "key_person_busy",
            f"停滞在「{load.get('name', '')}」：该部门并行上限 {load.get('parallel_limit')} 单，"
            f"当日已有 {load.get('load')} 单，关键岗位忙碌，后续审批将延迟 {max(delay, 1)} 个工作日。",
            max(delay, 1),
        )

    if delay > 0 or case.stall_code == "overloaded":
        return (
            "overloaded",
            f"「{load.get('name', '')}」事项过多（{load.get('load')}/{load.get('parallel_limit')}），"
            f"超出并行容量，预计额外延迟 {delay} 个工作日。",
            delay,
        )

    if case.stall_note:
        return case.stall_code or "other", case.stall_note, delay

    return "", "当前按制度时限正常排队，未见材料缺失或部门过载。", 0
