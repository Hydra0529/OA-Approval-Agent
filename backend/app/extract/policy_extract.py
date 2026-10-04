from __future__ import annotations

from pathlib import Path

from app.ingest.pdf_parser import extract_pdf_text
from app.llm.client import chat_json
from app.models.schema import ProcessEdge, ProcessGateway, ProcessNode, ProcessTemplate
from app.rag.store import get_policy_store


CANONICAL_IDS = {
    "报销": "expense_reimburse_v1",
    "采购": "purchase_approve_v1",
    "合同": "contract_approve_v1",
    "请假": "leave_request_v1",
}

CANONICAL_NAMES = {
    "报销": "费用报销审批",
    "采购": "采购审批",
    "合同": "合同审批",
    "请假": "假期与考勤审批",
}

SYSTEM_PROMPT = """你是公司 OA 审批制度分析专家。根据制度文本抽取可执行的审批流程模板。
只输出 JSON，字段：
{
  "id": "snake_case_id",
  "name": "流程名称",
  "category": "报销|采购|合同|请假|其他",
  "nodes": [{"id","name","role","sla_days","description"}],
  "edges": [{"source","target","condition"}],
  "gateways": [{"id","when","then","else_to"}]
}
规则：
- nodes 按主路径顺序；条件分支用 gateways.when（如 amount >= 10000）与 edges.condition
- role 用中文角色名；sla_days 为工作日整数
- 不要编造制度中不存在的节点
- 同一类流程必须用固定 id：报销 expense_reimburse_v1，采购 purchase_approve_v1，合同 contract_approve_v1，请假 leave_request_v1
"""


def category_from_filename(filename: str) -> str | None:
    """Classify by file name only, so one company's docs are not mixed across processes."""
    name = filename.replace(".pdf", "")
    rules: list[tuple[tuple[str, ...], str]] = [
        (("请假", "休假", "加班", "调休", "假期", "考勤"), "请假"),
        (("合同",), "合同"),
        (("采购", "低值易耗", "物资"), "采购"),
        (("报销", "差旅", "审批权限", "招待", "借款", "公务接待"), "报销"),
    ]
    for keys, cat in rules:
        if any(k in name for k in keys):
            return cat
    return None


def extract_template_from_policy(
    policy_path: Path,
    template_id: str | None = None,
    approve: bool = True,
) -> ProcessTemplate:
    text = extract_pdf_text(policy_path)
    # Prefer RAG snippets for long docs
    store = get_policy_store()
    snippets = store.query(f"{policy_path.stem} 审批流程 节点 时限 权限", top_k=8)
    context = "\n\n".join(s["text"] for s in snippets) if snippets else text[:12000]

    data = chat_json(
        SYSTEM_PROMPT,
        f"制度文件：{policy_path.name}\n\n制度内容：\n{context[:14000]}",
    )
    if data:
        tmpl = _from_llm_dict(data, policy_path.name, template_id, approve)
        return _force_canonical(tmpl, policy_path.name)
    return _heuristic_extract(policy_path.name, approve)


def _from_llm_dict(
    data: dict,
    policy_name: str,
    template_id: str | None,
    approve: bool,
) -> ProcessTemplate:
    file_cat = category_from_filename(policy_name)
    cat = file_cat or data.get("category") or "其他"
    tid = template_id or CANONICAL_IDS.get(cat) or data.get("id") or "process_other"
    nodes = [ProcessNode.model_validate(n) for n in data.get("nodes") or []]
    edges = [ProcessEdge.model_validate(e) for e in data.get("edges") or []]
    gateways = [ProcessGateway.model_validate(g) for g in data.get("gateways") or []]
    if not edges and len(nodes) > 1:
        edges = [
            ProcessEdge(source=nodes[i].id, target=nodes[i + 1].id)
            for i in range(len(nodes) - 1)
        ]
    return ProcessTemplate(
        id=tid,
        name=CANONICAL_NAMES.get(cat) or data.get("name") or tid,
        category=cat,
        policy_refs=[policy_name],
        nodes=nodes,
        edges=edges,
        gateways=gateways,
        approved=approve,
        source="llm_extract",
    )


def _heuristic_extract(policy_name: str, approve: bool) -> ProcessTemplate:
    """Rule fallback when LLM is unavailable — classify by filename only."""
    cat = category_from_filename(policy_name)
    if cat == "请假":
        return _leave_template(policy_name, approve)
    if cat == "合同":
        return _contract_template(policy_name, approve)
    if cat == "采购":
        return _purchase_template(policy_name, approve)
    if cat == "报销":
        return _expense_template(policy_name, approve)
    return _other_template(policy_name, approve)


def _force_canonical(tmpl: ProcessTemplate, policy_name: str) -> ProcessTemplate:
    cat = category_from_filename(policy_name) or tmpl.category
    canon_id = CANONICAL_IDS.get(cat)
    if not canon_id:
        return tmpl.model_copy(update={"category": cat or "其他"})
    return tmpl.model_copy(
        update={
            "id": canon_id,
            "category": cat,
            "name": CANONICAL_NAMES.get(cat) or tmpl.name,
        }
    )


def _expense_template(policy: str, approve: bool) -> ProcessTemplate:
    nodes = [
        ProcessNode(id="submit", name="员工提交", role="申请人", sla_days=0),
        ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
        ProcessNode(id="finance", name="财务审核", role="财务专员", sla_days=2),
        ProcessNode(id="cfo", name="财务负责人审批", role="财务负责人", sla_days=2),
        ProcessNode(id="pay", name="出纳付款", role="出纳", sla_days=1),
    ]
    edges = [
        ProcessEdge(source="submit", target="dept_manager"),
        ProcessEdge(source="dept_manager", target="finance"),
        ProcessEdge(source="finance", target="cfo", condition="amount >= 10000"),
        ProcessEdge(source="finance", target="pay", condition="amount < 10000"),
        ProcessEdge(source="cfo", target="pay"),
    ]
    gateways = [
        ProcessGateway(
            id="gw_after_finance",
            when="amount >= 10000",
            then="cfo",
            else_to="pay",
        )
    ]
    return ProcessTemplate(
        id="expense_reimburse_v1",
        name="费用报销审批",
        category="报销",
        policy_refs=[policy],
        nodes=nodes,
        edges=edges,
        gateways=[],  # edges already encode branch; keep empty to avoid double jump
        approved=approve,
        source="heuristic",
    )


def _purchase_template(policy: str, approve: bool) -> ProcessTemplate:
    nodes = [
        ProcessNode(id="submit", name="采购申请提交", role="申请人", sla_days=0),
        ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
        ProcessNode(id="procurement", name="采购部审核", role="采购专员", sla_days=2),
        ProcessNode(id="finance", name="财务预算审核", role="财务专员", sla_days=1),
        ProcessNode(id="gm", name="总经理审批", role="总经理", sla_days=2),
        ProcessNode(id="po", name="下采购订单", role="采购专员", sla_days=1),
    ]
    edges = [
        ProcessEdge(source="submit", target="dept_manager"),
        ProcessEdge(source="dept_manager", target="procurement"),
        ProcessEdge(source="procurement", target="finance"),
        ProcessEdge(source="finance", target="gm", condition="amount >= 50000"),
        ProcessEdge(source="finance", target="po", condition="amount < 50000"),
        ProcessEdge(source="gm", target="po"),
    ]
    return ProcessTemplate(
        id="purchase_approve_v1",
        name="采购审批",
        category="采购",
        policy_refs=[policy],
        nodes=nodes,
        edges=edges,
        gateways=[],
        approved=approve,
        source="heuristic",
    )


def _contract_template(policy: str, approve: bool) -> ProcessTemplate:
    nodes = [
        ProcessNode(id="submit", name="合同起草提交", role="经办人", sla_days=0),
        ProcessNode(id="legal", name="法务审核", role="法务专员", sla_days=2),
        ProcessNode(id="finance", name="财务审核", role="财务专员", sla_days=1),
        ProcessNode(id="dept_director", name="部门总监审批", role="部门总监", sla_days=1),
        ProcessNode(id="gm", name="总经理审批", role="总经理", sla_days=2),
        ProcessNode(id="seal", name="用印归档", role="行政专员", sla_days=1),
    ]
    edges = [
        ProcessEdge(source="submit", target="legal"),
        ProcessEdge(source="legal", target="finance"),
        ProcessEdge(source="finance", target="dept_director"),
        ProcessEdge(source="dept_director", target="gm", condition="amount >= 100000"),
        ProcessEdge(source="dept_director", target="seal", condition="amount < 100000"),
        ProcessEdge(source="gm", target="seal"),
    ]
    return ProcessTemplate(
        id="contract_approve_v1",
        name="合同审批",
        category="合同",
        policy_refs=[policy],
        nodes=nodes,
        edges=edges,
        gateways=[],
        approved=approve,
        source="heuristic",
    )


def _leave_template(policy: str, approve: bool) -> ProcessTemplate:
    nodes = [
        ProcessNode(id="submit", name="员工提交请假", role="申请人", sla_days=0),
        ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
        ProcessNode(id="hr", name="人力资源备案", role="HR专员", sla_days=1),
        ProcessNode(id="director", name="总监审批", role="部门总监", sla_days=1),
    ]
    edges = [
        ProcessEdge(source="submit", target="dept_manager"),
        ProcessEdge(source="dept_manager", target="director", condition="days >= 3"),
        ProcessEdge(source="dept_manager", target="hr", condition="days < 3"),
        ProcessEdge(source="director", target="hr"),
    ]
    return ProcessTemplate(
        id="leave_request_v1",
        name="假期与考勤审批",
        category="请假",
        policy_refs=[policy],
        nodes=nodes,
        edges=edges,
        gateways=[],
        approved=approve,
        source="heuristic",
    )


def _other_template(policy: str, approve: bool) -> ProcessTemplate:
    return ProcessTemplate(
        id="policy_other",
        name=policy.replace(".pdf", ""),
        category="其他",
        policy_refs=[policy],
        nodes=[],
        edges=[],
        gateways=[],
        approved=approve,
        source="heuristic",
    )
