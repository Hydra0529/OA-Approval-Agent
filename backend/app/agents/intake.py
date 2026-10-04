"""Submit-time agents: read application → retrieve policy → generate path → compliance + web."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.agents.compliance import detect_activities, identify_requirements, review_activities
from app.extract.policy_extract import CANONICAL_IDS, CANONICAL_NAMES, category_from_filename
from app.ingest.pdf_parser import extract_pdf_text
from app.llm.client import chat_json
from app.models.schema import (
    ApprovalCase,
    CaseEvent,
    ProcessEdge,
    ProcessNode,
    ProcessTemplate,
)
from app.org_store import load_departments
from app.rag.store import get_policy_store
from app.storage import get_template, save_template

INTAKE_AGENTS = [
    "申请解析智能体",
    "制度检索智能体",
    "流程生成智能体",
    "合规审查智能体",
    "联网查法智能体",
]

CITIES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "成都",
    "武汉",
    "西安",
    "天津",
    "重庆",
    "苏州",
    "青岛",
    "厦门",
    "合肥",
    "长沙",
)

EQUIPMENT_WORDS = ("无人机", "无人驾驶航空器", "航拍器", "drone")

DEFAULT_PROJECT_THRESHOLD = 5_000_000


def read_application_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_amount(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if m:
        return float(m.group(1)) * 10000
    m = re.search(r"预算[^\d]{0,8}(\d[\d,]*)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"(\d[\d,]{3,})\s*元", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def _parse_city(text: str) -> str:
    for city in CITIES:
        if city in text:
            return city
    m = re.search(r"([\u4e00-\u9fff]{2,3}(?:市|县))", text)
    return m.group(1) if m else ""


def _parse_dept(text: str, allowed: list[str]) -> str:
    for name in allowed:
        if name and name in text:
            return name
    return allowed[0] if allowed else "研发部"


def _parse_category(text: str, filename: str) -> str:
    blob = filename + "\n" + text
    file_cat = category_from_filename(filename)
    if file_cat:
        return file_cat
    if any(k in blob for k in ("立项", "项目申报", "项目申请", "航拍", "测绘")):
        return "立项"
    if any(k in blob for k in ("请假", "休假", "调休")):
        return "请假"
    if "合同" in blob:
        return "合同"
    if any(k in blob for k in ("采购", "低值易耗")):
        return "采购"
    if any(k in blob for k in ("报销", "差旅", "借款")):
        return "报销"
    return "立项"


def extract_application(text: str, filename: str = "") -> dict:
    allowed = [d["name"] for d in load_departments()]
    data = chat_json(
        "从项目/审批申报材料中抽取 JSON："
        '{"title","category","amount","city","district","dept","applicant","equipment":[],'
        '"activities":[],"has_filing_docs":false}。category 只能是 报销|采购|合同|请假|立项。'
        "金额用元。activities 填写正文描述的外业或管制作业名称，不要等正文自己列出许可文件。",
        text[:12000],
    ) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        m = re.search(r"项目名称[:：]\s*(.+)", text)
        title = (m.group(1).strip() if m else "") or Path(filename).stem or "未命名申报"
    category = str(data.get("category") or _parse_category(text, filename))
    if category not in {"报销", "采购", "合同", "请假", "立项"}:
        category = _parse_category(text, filename)
    amount = data.get("amount")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = _parse_amount(text)
    city = str(data.get("city") or _parse_city(text))
    dept = str(data.get("dept") or _parse_dept(text, allowed))
    if dept not in allowed:
        dept = _parse_dept(text, allowed)
    applicant = str(data.get("applicant") or "")
    if not applicant:
        m = re.search(r"申请人[:：]\s*(\S+)", text)
        applicant = (m.group(1) if m else "") or "申报人"
    equipment = data.get("equipment") if isinstance(data.get("equipment"), list) else []
    equipment = [str(x) for x in equipment]
    blob = text + filename
    equipment = [x for x in equipment if _mentions_equipment(blob, x)]
    for w in EQUIPMENT_WORDS:
        if _mentions_equipment(blob, w) and "无人机" not in equipment:
            equipment.append("无人机")
    activities = [str(x) for x in data.get("activities") or [] if str(x).strip()]
    for item in detect_activities(blob):
        if item["name"] not in activities:
            activities.append(item["name"])
    has_filing = _detect_filing_docs(blob, bool(data.get("has_filing_docs")))
    return {
        "title": title[:80],
        "category": category,
        "amount": amount,
        "city": city,
        "district": str(data.get("district") or ""),
        "dept": dept,
        "applicant": applicant[:40],
        "equipment": equipment,
        "activities": activities,
        "has_filing_docs": has_filing,
        "inner_ring": any(
            k in blob for k in ("一环", "二环以内", "二环内", "核心城区", "中心城区")
        ),
    }


def _detect_filing_docs(blob: str, llm_flag: bool) -> bool:
    """Treat '未附空域批准' as missing; do not count mere mention of 空域 as attached."""
    if re.search(
        r"(未附|未提交|没有附|尚未[提交附]|缺少|未提供|未一并提交).{0,24}(空域|飞行|报备|批准)",
        blob,
    ):
        return False
    if re.search(
        r"(已附|已提交|随附|附件[：:].{0,30})(空域|飞行活动申请|无人机报备|报备材料)",
        blob,
    ):
        return True
    return bool(llm_flag)


def _mentions_equipment(blob: str, word: str) -> bool:
    if not word or word not in blob:
        return False
    if re.search(rf"(不涉及|不使用|不含|没有|未使用).{{0,12}}{re.escape(word)}", blob):
        return False
    return True


def _extract_thresholds(snippets: list[str]) -> list[int]:
    found: list[int] = []
    blob = "\n".join(snippets)
    for m in re.finditer(r"(?:大于等于|不低于|达到|超过|>=)\s*(\d[\d,]*)", blob):
        found.append(int(m.group(1).replace(",", "")))
    for m in re.finditer(r"(\d[\d,]*)\s*元以上", blob):
        found.append(int(m.group(1).replace(",", "")))
    # Drop SLA-like numbers (2 个工作日) so they are not treated as money gates.
    return sorted({x for x in found if x >= 1000})


def _project_threshold(policy_hits: list[dict]) -> int:
    texts = [
        h.get("text") or ""
        for h in policy_hits
        if any(k in (h.get("text") or "") for k in ("立项", "项目申报", "项目投资", "固定资产投资"))
    ]
    found = _extract_thresholds(texts)
    million = [x for x in found if x >= 100_000]
    return million[0] if million else DEFAULT_PROJECT_THRESHOLD


def retrieve_policies(extracted: dict) -> list[dict]:
    q = (
        f"{extracted.get('category','')} {extracted.get('title','')} "
        f"审批 权限 金额 时限 {extracted.get('city','')} "
        f"{''.join(extracted.get('equipment') or [])} "
        f"{' '.join(extracted.get('activities') or [])}"
    )
    return get_policy_store().query(q, top_k=6)


def _copy_canonical(category: str) -> ProcessTemplate | None:
    tid = CANONICAL_IDS.get(category)
    return get_template(tid) if tid else None


def _insert_before_last(tmpl: ProcessTemplate, node: ProcessNode) -> None:
    if any(n.id == node.id for n in tmpl.nodes):
        return
    if len(tmpl.nodes) < 2:
        prev_id = tmpl.nodes[-1].id if tmpl.nodes else "submit"
        tmpl.nodes.append(node)
        tmpl.edges.append(ProcessEdge(source=prev_id, target=node.id))
        return
    last = tmpl.nodes[-1]
    tmpl.nodes.insert(-1, node)
    rewritten: list[ProcessEdge] = []
    for e in tmpl.edges:
        if e.target == last.id:
            rewritten.append(ProcessEdge(source=e.source, target=node.id, condition=e.condition))
        else:
            rewritten.append(e)
    rewritten.append(ProcessEdge(source=node.id, target=last.id))
    tmpl.edges = rewritten


def build_process(extracted: dict, policy_hits: list[dict], case_id: str) -> tuple[ProcessTemplate, str]:
    category = extracted["category"]
    amount = float(extracted.get("amount") or 0)
    notes: list[str] = []
    refs = [h.get("source", "") for h in policy_hits if h.get("source")]

    base = _copy_canonical(category) if category != "立项" else None
    if base:
        tmpl = base.model_copy(deep=True)
        tmpl.id = f"dyn-{case_id}"
        tmpl.name = f"{CANONICAL_NAMES.get(category, base.name)}（本单生成）"
        tmpl.source = "intake_generated"
        tmpl.approved = True
        tmpl.policy_refs = list(dict.fromkeys([*(tmpl.policy_refs or []), *refs]))
        notes.append(f"以制度库中的「{base.name}」为底，按本单金额 {amount:.0f} 元生成路径。")
        thresholds = _extract_thresholds([h.get("text", "") for h in policy_hits])
        if thresholds:
            notes.append("制度片段中的金额门槛：" + "、".join(str(x) for x in thresholds))
    else:
        # 立项 / 项目申报：每次按金额、设备生成不同审批链，不套四类写死模板
        threshold = _project_threshold(policy_hits)
        high = amount >= threshold
        nodes = [
            ProcessNode(id="submit", name="项目申报提交", role="申请人", sla_days=0),
            ProcessNode(id="dept_manager", name="部门经理审核", role="部门经理", sla_days=1),
        ]
        edges = [ProcessEdge(source="submit", target="dept_manager")]
        prev = "dept_manager"
        if high:
            nodes.append(ProcessNode(id="gm", name="总经理审批", role="总经理", sla_days=2))
            nodes.append(ProcessNode(id="chairman", name="董事长审定", role="董事长", sla_days=2))
            edges.append(ProcessEdge(source=prev, target="gm"))
            edges.append(ProcessEdge(source="gm", target="chairman"))
            prev = "chairman"
            src = (
                "制度金额门槛"
                if threshold != DEFAULT_PROJECT_THRESHOLD
                else "业务示例（制度未写明立项门槛时按 500 万元）"
            )
            notes.append(f"金额 {amount:.0f} 元 ≥ {threshold:.0f} 元，按{src}增加总经理、董事长。")
        else:
            notes.append(f"金额 {amount:.0f} 元低于 {threshold:.0f} 元门槛，部门经理审核后即可备案，不经总经理/董事长。")
        nodes.append(ProcessNode(id="archive", name="立项备案", role="行政专员", sla_days=1))
        edges.append(ProcessEdge(source=prev, target="archive"))
        tmpl = ProcessTemplate(
            id=f"dyn-{case_id}",
            name=f"{extracted.get('title') or '项目立项'}审批（本单生成）",
            category=category,
            policy_refs=refs,
            nodes=nodes,
            edges=edges,
            approved=True,
            source="intake_generated",
        )

    if extracted.get("activities") or extracted.get("equipment") or extracted.get("required_docs"):
        _insert_before_last(
            tmpl,
            ProcessNode(id="compliance", name="合规与法务审查", role="法务专员", sla_days=2),
        )
        names = extracted.get("activities") or extracted.get("equipment") or ["受控作业"]
        notes.append(
            "申报含受控作业（"
            + "、".join(str(x) for x in names)
            + "），在归档前插入法务合规审查；缺许可或报备材料则卡住。"
        )

    save_template(tmpl)
    return tmpl, " ".join(notes)


def review_compliance(extracted: dict, filenames: list[str], body: str = "") -> dict:
    return review_activities(extracted, filenames, body)


def run_intake(
    texts: list[tuple[str, str]],
    overrides: dict | None = None,
) -> dict:
    """texts: list of (filename, body)."""
    overrides = overrides or {}
    combined = "\n\n".join(f"【{n}】\n{t}" for n, t in texts)
    filenames = [n for n, _ in texts]
    extracted = extract_application(combined, filenames[0] if filenames else "")
    for key in ("title", "amount", "dept", "applicant"):
        val = overrides.get(key)
        if val not in (None, "", 0, 0.0):
            extracted[key] = val
    policy_hits = retrieve_policies(extracted)
    req = identify_requirements(combined, extracted, policy_hits)
    extracted["activities"] = req["activities"]
    extracted["activity_details"] = req["activity_details"]
    extracted["required_docs"] = req["required_docs"]
    extracted["used_llm"] = req["used_llm"]
    extracted["application_text"] = combined[:6000]
    case_id = f"C-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    tmpl, plan_note = build_process(extracted, policy_hits, case_id)
    compliance = review_compliance(extracted, filenames, combined)
    return {
        "case_id": case_id,
        "extracted": extracted,
        "policy_hits": [
            {"source": h.get("source", ""), "text": (h.get("text") or "")[:280]}
            for h in policy_hits
        ],
        "template": tmpl,
        "plan_note": plan_note,
        "compliance": compliance,
        "agents": INTAKE_AGENTS,
        "source_files": filenames,
    }


def case_from_intake(pack: dict) -> ApprovalCase:
    extracted = pack["extracted"]
    tmpl: ProcessTemplate = pack["template"]
    compliance = pack["compliance"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    missing = compliance.get("missing_docs") or []
    first = tmpl.nodes[0]
    current = tmpl.nodes[1].id if len(tmpl.nodes) > 1 else first.id
    if missing:
        for n in tmpl.nodes:
            if n.id == "compliance":
                current = n.id
                break
    stall_code = "missing_docs" if missing else ""
    stall_note = ""
    if missing:
        stall_note = "申报未附：" + "、".join(missing) + "。合规审查不通过，流程卡住。"
    return ApprovalCase(
        case_id=pack["case_id"],
        title=extracted["title"],
        template_id=tmpl.id,
        category=extracted["category"],
        amount=float(extracted.get("amount") or 0),
        level="一类" if float(extracted.get("amount") or 0) >= DEFAULT_PROJECT_THRESHOLD else "三类",
        dept=extracted["dept"],
        applicant=extracted["applicant"],
        submit_at=now,
        current_node=current,
        status="running",
        stall_code=stall_code,
        stall_note=stall_note,
        fields={
            "generated": True,
            "city": extracted.get("city"),
            "equipment": extracted.get("equipment"),
            "activities": extracted.get("activities"),
            "activity_details": extracted.get("activity_details"),
            "required_docs": extracted.get("required_docs"),
            "used_llm": extracted.get("used_llm"),
            "application_text": extracted.get("application_text"),
            "inner_ring": extracted.get("inner_ring"),
            "plan_note": pack.get("plan_note"),
            "agents": pack.get("agents"),
            "policy_hits": pack.get("policy_hits"),
            "compliance": compliance.get("findings"),
            "web_hits": compliance.get("web_hits"),
            "missing_docs": missing,
            "source_files": pack.get("source_files"),
        },
        history=[
            CaseEvent(
                at=now,
                node_id=first.id,
                node_name=first.name,
                role=first.role,
                action="submit",
                note="智能体读取申报材料后生成审批路径",
            )
        ],
    )


def apply_supplement(case: ApprovalCase, extra_names: list[str]) -> ApprovalCase:
    """Attach extra files and re-run compliance; clear missing-doc stall when complete."""
    fields = dict(case.fields or {})
    old = [str(x) for x in (fields.get("source_files") or [])]
    all_names = list(dict.fromkeys([*old, *extra_names]))
    extracted = {
        "equipment": fields.get("equipment") or [],
        "city": fields.get("city") or "",
        "inner_ring": bool(fields.get("inner_ring")),
        "activities": fields.get("activities") or [],
        "activity_details": fields.get("activity_details") or [],
        "required_docs": fields.get("required_docs") or [],
        "has_filing_docs": False,
    }
    body = str(fields.get("application_text") or "")
    compliance = review_compliance(extracted, all_names, body)
    missing = compliance.get("missing_docs") or []
    fields["source_files"] = all_names
    fields["missing_docs"] = missing
    fields["compliance"] = compliance.get("findings")
    if compliance.get("required_docs"):
        fields["required_docs"] = compliance.get("required_docs")
    if compliance.get("web_hits"):
        fields["web_hits"] = compliance.get("web_hits")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tmpl_node = case.current_node
    case.history.append(
        CaseEvent(
            at=now,
            node_id=tmpl_node,
            node_name="材料补充",
            role="申请人",
            action="submit",
            note="补充材料：" + "、".join(extra_names),
        )
    )
    case.fields = fields
    if missing:
        case.stall_code = "missing_docs"
        case.stall_note = "申报未附：" + "、".join(missing) + "。合规审查不通过，流程卡住。"
    else:
        case.stall_code = ""
        case.stall_note = ""
    return case
