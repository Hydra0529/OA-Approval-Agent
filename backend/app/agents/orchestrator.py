from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.agents.dept_learner import (
    apply_parallel_limits,
    extract_department_names,
    extract_parallel_limits,
    merge_departments,
)
from app.extract.policy_extract import (
    CANONICAL_IDS,
    CANONICAL_NAMES,
    category_from_filename,
    extract_template_from_policy,
)
from app.ingest.pdf_parser import extract_pdf_text
from app.models.schema import LearnedFunction, LearningReport, ProcessTemplate
from app.org_store import load_knowledge, save_knowledge
from app.rag.store import get_policy_store
from app.storage import get_template, save_template

CANONICAL = CANONICAL_IDS

AGENT_NAMES = [
    "制度解析智能体",
    "职能识别智能体",
    "组织识别智能体",
    "模板合并智能体",
    "知识发布智能体",
]


def _detect_functions(text: str, filename: str) -> list[dict]:
    found: list[dict] = []
    file_cat = category_from_filename(filename)
    if not file_cat:
        return [
            {
                "name": Path(filename).stem.replace("三胞集团_", ""),
                "category": "其他",
                "summary": "已入库的集团制度，不进入报销/采购/合同/请假主流程",
            }
        ]
    checks = [
        ("报销", "费用报销", "规范报销节点、票据与金额权限", "报销"),
        ("差旅", "差旅管理", "差旅标准与报销时限", "报销"),
        ("招待", "业务招待", "招待费申请与报销约束", "报销"),
        ("审批权限", "财务审批权限", "金额阈值与审定人", "报销"),
        ("采购", "采购管理", "采购申请、核价与下单", "采购"),
        ("低值易耗", "物资采购", "低值易耗品归口采购与台账", "采购"),
        ("合同", "合同管理", "法务审核、用印与归档", "合同"),
        ("印章", "用印管理", "用印登记与审批", "合同"),
        ("请假", "请假管理", "请假天数与审批层级", "请假"),
        ("休假", "请假管理", "休假申请与备案", "请假"),
        ("加班", "加班调休", "加班审批与调休备案", "请假"),
        ("考勤", "假期与考勤", "假期、加班与出差审批", "请假"),
    ]
    seen = set()
    blob = filename + "\n" + (text or "")[:8000]
    for key, name, desc, cat in checks:
        if cat != file_cat:
            continue
        if key in blob and name not in seen:
            seen.add(name)
            found.append({"name": name, "category": cat, "summary": desc})
    if not found:
        found.append(
            {
                "name": Path(filename).stem.replace("三胞集团_", ""),
                "category": file_cat,
                "summary": "从制度中识别的公司职能",
            }
        )
    return found


def _merge_template(existing: ProcessTemplate, incoming: ProcessTemplate, policy: str) -> ProcessTemplate:
    node_ids = {n.id for n in existing.nodes}
    nodes = list(existing.nodes)
    for n in incoming.nodes:
        if n.id not in node_ids:
            nodes.append(n)
            node_ids.add(n.id)
        else:
            for i, old in enumerate(nodes):
                if old.id == n.id and n.sla_days and n.sla_days != old.sla_days:
                    nodes[i] = old.model_copy(update={"sla_days": n.sla_days, "name": n.name or old.name})
    edge_keys = {(e.source, e.target, e.condition) for e in existing.edges}
    edges = list(existing.edges)
    for e in incoming.edges:
        key = (e.source, e.target, e.condition)
        if key not in edge_keys:
            edges.append(e)
            edge_keys.add(key)
    refs = list(dict.fromkeys([*existing.policy_refs, policy, *incoming.policy_refs]))
    try:
        ver = str(int(existing.version) + 1)
    except ValueError:
        ver = existing.version + ".1"
    return existing.model_copy(
        update={
            "nodes": nodes,
            "edges": edges,
            "policy_refs": refs,
            "version": ver,
            "source": "multi_agent_update",
            "approved": True,
        }
    )


def learn_from_pdf(path: Path, approve: bool = True) -> LearningReport:
    """Multi-agent pipeline: parse → identify functions → merge/update templates → publish."""
    store = get_policy_store()
    chunks = store.ingest_pdf(path)
    text = extract_pdf_text(path)
    functions_meta = _detect_functions(text, path.name)
    dept_names = extract_department_names(text + "\n" + path.name)
    added_depts = merge_departments(dept_names, source=path.name)
    capacity_notes = apply_parallel_limits(extract_parallel_limits(text), source=path.name)
    incoming = extract_template_from_policy(path, template_id=None, approve=approve)
    file_cat = category_from_filename(path.name)
    if file_cat:
        incoming = incoming.model_copy(
            update={
                "id": CANONICAL[file_cat],
                "category": file_cat,
                "name": CANONICAL_NAMES[file_cat],
            }
        )
    else:
        incoming = incoming.model_copy(update={"category": "其他"})

    learned: list[LearnedFunction] = []
    primary: ProcessTemplate | None = None
    canon_id = CANONICAL.get(incoming.category)

    if not canon_id:
        action = "ingested"
        tid = ""
        version = "0"
        summary = f"已入库《{path.name}》。该文件不属于报销/采购/合同/请假主流程，未新建流程模板，避免与四类审批混淆。"
    else:
        incoming = incoming.model_copy(update={"id": canon_id})
        existing = get_template(canon_id)
        if existing:
            merged = _merge_template(existing, incoming, path.name)
            save_template(merged)
            primary = merged
            action = "updated"
            tid = merged.id
            version = merged.version
            summary = f"已用《{path.name}》更新既有职能「{merged.name}」，版本 {version}。"
        else:
            incoming.source = "multi_agent_new"
            incoming.approved = approve
            if path.name not in incoming.policy_refs:
                incoming.policy_refs.append(path.name)
            save_template(incoming)
            primary = incoming
            action = "created"
            tid = incoming.id
            version = incoming.version
            summary = f"识别到新公司职能「{incoming.name}」，已建立流程模板。"

    for fn in functions_meta:
        cat_id = CANONICAL.get(fn["category"])
        fn_action = "unchanged" if action == "ingested" else (
            action if fn["category"] == incoming.category else (
                "updated" if cat_id and get_template(cat_id) else "created"
            )
        )
        learned.append(
            LearnedFunction(
                id=f"{tid}:{fn['name']}" if tid else fn["name"],
                name=fn["name"],
                category=fn["category"],
                action=fn_action,
                template_id=tid,
                version=version,
                policy=path.name,
                summary=fn["summary"],
            )
        )

    kb = load_knowledge()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    for item in learned:
        rec = item.model_dump()
        rec["updated_at"] = now
        kb.setdefault("functions", [])
        prev = next((x for x in kb["functions"] if x.get("name") == item.name), None)
        if prev:
            if rec.get("template_id") or not prev.get("template_id"):
                prev.update(rec)
        else:
            kb["functions"].append(rec)
    kb.setdefault("history", []).append(
        {
            "at": now,
            "policy": path.name,
            "chunks": chunks,
            "action": action,
            "template_id": tid,
            "agents": AGENT_NAMES,
        }
    )
    save_knowledge(kb)

    notes = summary + " 多角色智能体已完成学习：新制度用于理解新职能或刷新已有职能。"
    if added_depts:
        notes += " 从制度识别并登记部门：" + "、".join(added_depts) + "。"
    if capacity_notes:
        notes += " 已按制度更新部门并行工作数：" + "、".join(capacity_notes) + "。刷新日历可见忙闲变化。"
    elif dept_names:
        notes += " 申请部门以制度识别清单为准，提交时不可自填新部门。"
    return LearningReport(
        filename=path.name,
        chunks=chunks,
        agents=AGENT_NAMES,
        functions=learned,
        template=primary.model_dump() if primary else None,
        notes=notes,
    )
