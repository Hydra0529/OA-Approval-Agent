from __future__ import annotations

from app.engine.monitor import estimate_timeline, next_step, planned_span, resolve_path
from app.llm.client import chat_text
from app.models.schema import ApprovalCase, ProcessTemplate
from app.rag.store import get_policy_store


def generate_case_report(
    case: ApprovalCase, template: ProcessTemplate
) -> tuple[str, list[dict]]:
    path = resolve_path(template, case)
    _, _, next_summary = next_step(case, template)
    start, end, duration = planned_span(case, template)
    timeline = estimate_timeline(case, template)
    bottleneck = max(path, key=lambda n: n.sla_days) if path else None

    store = get_policy_store()
    citations = store.query(
        f"{template.name} {case.category} 审批时限 权限",
        top_k=4,
    )

    facts = {
        "title": case.title,
        "category": case.category,
        "amount": case.amount,
        "dept": case.dept,
        "status": case.status,
        "nodes": [f"{n.name}({n.role}, SLA {n.sla_days}日)" for n in path],
        "planned": f"{start} ~ {end}（约 {duration} 自然日）",
        "next": next_summary,
        "bottleneck": (
            f"{bottleneck.name}（{bottleneck.sla_days} 工作日）" if bottleneck else "无"
        ),
        "timeline": [t.summary for t in timeline],
        "citations": [c["text"][:240] for c in citations],
        "stall": case.stall_note or case.stall_code or "",
        "city": (case.fields or {}).get("city"),
        "equipment": (case.fields or {}).get("equipment"),
        "compliance": (case.fields or {}).get("compliance"),
        "missing_docs": (case.fields or {}).get("missing_docs"),
        "plan_note": (case.fields or {}).get("plan_note"),
    }

    llm = chat_text(
        "你是 OA 流程分析顾问。根据事实写简明中文分析报告（300-500字），"
        "包含：流程概览、当前进度与下一步、瓶颈与风险、制度依据摘要。不要编造事实。",
        str(facts),
    )
    if llm:
        return llm, citations

    lines = [
        f"# {case.title} — 流程分析报告",
        "",
        f"- 流程类型：{template.name}（{case.category}）",
        f"- 申请部门：{case.dept}；申请人：{case.applicant}；金额：{case.amount}",
        f"- 状态：{case.status}",
        f"- 计划周期：{start} ~ {end}（约 {duration} 自然日）",
        f"- 下一步：{next_summary}",
        f"- 瓶颈节点（按模板 SLA）：{facts['bottleneck']}",
        "",
        "## 路径节点",
    ]
    for n in path:
        lines.append(f"- {n.name} / {n.role} / SLA {n.sla_days} 工作日")
    lines.append("")
    lines.append("## 时间线")
    for t in timeline:
        lines.append(f"- [{t.status}] {t.summary}")
    if citations:
        lines.append("")
        lines.append("## 制度依据（检索片段）")
        for c in citations:
            lines.append(f"- 《{c.get('source', '')}》：{c['text'][:180]}…")
    if (case.fields or {}).get("plan_note"):
        lines.append("")
        lines.append("## 本单如何生成")
        lines.append(str(case.fields.get("plan_note")))
    findings = (case.fields or {}).get("compliance") or []
    if findings:
        lines.append("")
        lines.append("## 合规与当地限制")
        for f in findings:
            lines.append(f"- {f.get('topic')}: {f.get('summary')}")
            miss = f.get("missing_docs") or []
            if miss:
                lines.append("  缺件：" + "、".join(miss))
    web = (case.fields or {}).get("web_hits") or []
    if web:
        lines.append("")
        lines.append("## 联网查询")
        for h in web[:5]:
            lines.append(f"- {h.get('title') or h.get('query')}: {h.get('snippet','')[:160]}")
    return "\n".join(lines), citations
