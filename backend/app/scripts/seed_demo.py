"""Generate demo PDFs, templates, cases, gold eval set, and ingest RAG."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow `python -m app.scripts.seed_demo` from backend/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.config import settings
from app.models.schema import ApprovalCase, CaseEvent, ProcessEdge, ProcessNode, ProcessTemplate
from app.rag.store import get_policy_store
from app.storage import ensure_data_dirs, save_case, save_template


POLICIES: dict[str, str] = {
    "费用报销管理办法.pdf": """
公司费用报销管理办法

第一条 目的
规范员工费用报销审批流程，明确审批权限与时限。

第二条 适用范围
本公司全体员工的差旅费、招待费、办公费等费用报销。

第三条 审批流程
1. 员工提交：申请人在 OA 系统填写报销单并提交附件，即时完成。
2. 部门经理审批：部门经理应在 1 个工作日内完成审批。
3. 财务审核：财务专员应在 2 个工作日内完成票据与合规审核。
4. 财务负责人审批：单笔金额大于等于 10000 元时，须由财务负责人在 2 个工作日内审批。
5. 出纳付款：审核通过后，出纳在 1 个工作日内完成付款。

第四条 金额权限
- 金额 < 10000 元：财务审核通过后直接进入出纳付款。
- 金额 >= 10000 元：须增加财务负责人审批节点。

第五条 时限合计
常规报销（金额 < 10000）计划周期约 4 个工作日；大额报销约 6 个工作日。
""",
    "采购管理制度.pdf": """
公司采购管理制度

第一条 目的
规范物资与服务采购申请、审批与下单流程。

第二条 审批流程
1. 采购申请提交：申请人提交采购需求，即时完成。
2. 部门经理审批：1 个工作日。
3. 采购部审核：采购专员核价与供应商评估，2 个工作日。
4. 财务预算审核：财务专员确认预算，1 个工作日。
5. 总经理审批：金额大于等于 50000 元时，总经理 2 个工作日内审批。
6. 下采购订单：采购专员 1 个工作日内下达订单。

第三条 金额分支
- 金额 < 50000 元：财务预算审核后直接下单。
- 金额 >= 50000 元：须经总经理审批后下单。
""",
    "合同审批管理办法.pdf": """
合同审批管理办法

第一条 流程
1. 合同起草提交：经办人提交合同文本，即时。
2. 法务审核：法务专员 2 个工作日。
3. 财务审核：财务专员 1 个工作日。
4. 部门总监审批：1 个工作日。
5. 总经理审批：合同标的金额大于等于 100000 元时，总经理 2 个工作日审批。
6. 用印归档：行政专员 1 个工作日完成用印与归档。

第二条 金额规则
金额 < 100000 元：部门总监审批后可直接用印；金额 >= 100000 元须总经理审批。
""",
    "员工请假管理制度.pdf": """
员工请假管理制度

第一条 请假流程
1. 员工提交请假：申请人提交请假单，即时。
2. 部门经理审批：1 个工作日。
3. 总监审批：连续请假天数大于等于 3 天时，部门总监 1 个工作日内审批。
4. 人力资源备案：HR 专员 1 个工作日内备案。

第二条 分支规则
- 请假天数 < 3：部门经理审批后直接人力资源备案。
- 请假天数 >= 3：须经总监审批后再备案。
""",
    "差旅费报销标准.pdf": """
差旅费报销标准

第一条 交通与住宿按职级执行标准，超标部分不予报销。
第二条 差旅报销适用《费用报销管理办法》审批流程与时限。
第三条 跨城市出差须在出发前完成行程报备。
""",
    "招待费管理规定.pdf": """
招待费管理规定

第一条 业务招待须事先申请，事后按费用报销流程报销。
第二条 单笔招待费 >= 5000 元须部门总监知会财务负责人。
第三条 禁止虚报招待事由，违规移交纪检。
""",
    "印章使用管理办法.pdf": """
印章使用管理办法

第一条 合同用印须完成合同审批流程后方可盖章。
第二条 行政专员在审批通过后 1 个工作日内完成用印与登记。
第三条 外带印章须总经理批准。
""",
    "加班与调休规定.pdf": """
加班与调休规定

第一条 加班申请由部门经理 1 个工作日内审批，人力资源备案。
第二条 调休优先于加班费发放，调休有效期 90 天。
""",
}


def _register_font() -> str:
    """Try register a Chinese-capable font on Windows; fallback to Helvetica."""
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont("CN", str(p), subfontIndex=0))
                return "CN"
            except Exception:
                continue
    return "Helvetica"


def write_pdf(path: Path, text: str, font_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFont(font_name, 11)
    y = height - 50
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            y -= 14
            continue
        # simple wrap
        while len(line) > 42:
            c.drawString(50, y, line[:42])
            line = line[42:]
            y -= 16
            if y < 50:
                c.showPage()
                c.setFont(font_name, 11)
                y = height - 50
        c.drawString(50, y, line)
        y -= 16
        if y < 50:
            c.showPage()
            c.setFont(font_name, 11)
            y = height - 50
    c.save()


def seed_templates() -> None:
    templates = [
        ProcessTemplate(
            id="expense_reimburse_v1",
            name="费用报销审批",
            category="报销",
            policy_refs=["费用报销管理办法.pdf"],
            approved=True,
            source="seed",
            nodes=[
                ProcessNode(id="submit", name="员工提交", role="申请人", sla_days=0),
                ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
                ProcessNode(id="finance", name="财务审核", role="财务专员", sla_days=2),
                ProcessNode(id="cfo", name="财务负责人审批", role="财务负责人", sla_days=2),
                ProcessNode(id="pay", name="出纳付款", role="出纳", sla_days=1),
            ],
            edges=[
                ProcessEdge(source="submit", target="dept_manager"),
                ProcessEdge(source="dept_manager", target="finance"),
                ProcessEdge(source="finance", target="cfo", condition="amount >= 10000"),
                ProcessEdge(source="finance", target="pay", condition="amount < 10000"),
                ProcessEdge(source="cfo", target="pay"),
            ],
        ),
        ProcessTemplate(
            id="purchase_approve_v1",
            name="采购审批",
            category="采购",
            policy_refs=["采购管理制度.pdf"],
            approved=True,
            source="seed",
            nodes=[
                ProcessNode(id="submit", name="采购申请提交", role="申请人", sla_days=0),
                ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
                ProcessNode(id="procurement", name="采购部审核", role="采购专员", sla_days=2),
                ProcessNode(id="finance", name="财务预算审核", role="财务专员", sla_days=1),
                ProcessNode(id="gm", name="总经理审批", role="总经理", sla_days=2),
                ProcessNode(id="po", name="下采购订单", role="采购专员", sla_days=1),
            ],
            edges=[
                ProcessEdge(source="submit", target="dept_manager"),
                ProcessEdge(source="dept_manager", target="procurement"),
                ProcessEdge(source="procurement", target="finance"),
                ProcessEdge(source="finance", target="gm", condition="amount >= 50000"),
                ProcessEdge(source="finance", target="po", condition="amount < 50000"),
                ProcessEdge(source="gm", target="po"),
            ],
        ),
        ProcessTemplate(
            id="contract_approve_v1",
            name="合同审批",
            category="合同",
            policy_refs=["合同审批管理办法.pdf"],
            approved=True,
            source="seed",
            nodes=[
                ProcessNode(id="submit", name="合同起草提交", role="经办人", sla_days=0),
                ProcessNode(id="legal", name="法务审核", role="法务专员", sla_days=2),
                ProcessNode(id="finance", name="财务审核", role="财务专员", sla_days=1),
                ProcessNode(id="dept_director", name="部门总监审批", role="部门总监", sla_days=1),
                ProcessNode(id="gm", name="总经理审批", role="总经理", sla_days=2),
                ProcessNode(id="seal", name="用印归档", role="行政专员", sla_days=1),
            ],
            edges=[
                ProcessEdge(source="submit", target="legal"),
                ProcessEdge(source="legal", target="finance"),
                ProcessEdge(source="finance", target="dept_director"),
                ProcessEdge(source="dept_director", target="gm", condition="amount >= 100000"),
                ProcessEdge(source="dept_director", target="seal", condition="amount < 100000"),
                ProcessEdge(source="gm", target="seal"),
            ],
        ),
        ProcessTemplate(
            id="leave_request_v1",
            name="请假审批",
            category="请假",
            policy_refs=["员工请假管理制度.pdf"],
            approved=True,
            source="seed",
            nodes=[
                ProcessNode(id="submit", name="员工提交请假", role="申请人", sla_days=0),
                ProcessNode(id="dept_manager", name="部门经理审批", role="部门经理", sla_days=1),
                ProcessNode(id="director", name="总监审批", role="部门总监", sla_days=1),
                ProcessNode(id="hr", name="人力资源备案", role="HR专员", sla_days=1),
            ],
            edges=[
                ProcessEdge(source="submit", target="dept_manager"),
                ProcessEdge(source="dept_manager", target="director", condition="days >= 3"),
                ProcessEdge(source="dept_manager", target="hr", condition="days < 3"),
                ProcessEdge(source="director", target="hr"),
            ],
        ),
    ]
    for t in templates:
        save_template(t)


def _case(
    case_id: str,
    title: str,
    template_id: str,
    category: str,
    amount: float,
    dept: str,
    applicant: str,
    submit_at: datetime,
    current_node: str,
    status: str = "running",
    fields: dict | None = None,
    history_nodes: list[tuple[str, str, str]] | None = None,
    stall_code: str = "",
    stall_note: str = "",
) -> ApprovalCase:
    history: list[CaseEvent] = []
    if history_nodes:
        t = submit_at
        for i, (nid, nname, role) in enumerate(history_nodes):
            history.append(
                CaseEvent(
                    at=t + timedelta(days=i),
                    node_id=nid,
                    node_name=nname,
                    role=role,
                    action="submit" if i == 0 else "approve",
                )
            )
    return ApprovalCase(
        case_id=case_id,
        title=title,
        template_id=template_id,
        category=category,
        amount=amount,
        dept=dept,
        applicant=applicant,
        submit_at=submit_at,
        current_node=current_node,
        status=status,  # type: ignore[arg-type]
        fields=fields or {},
        history=history,
        stall_code=stall_code,
        stall_note=stall_note,
    )


def seed_cases() -> None:
    base = datetime(2026, 1, 10, 9, 0, 0)
    cases = [
        _case(
            "C-20260110-EXP001",
            "市场部差旅报销-上海拜访",
            "expense_reimburse_v1",
            "报销",
            3200,
            "市场部",
            "王小明",
            base,
            "finance",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260112-EXP002",
            "研发部设备耗材报销",
            "expense_reimburse_v1",
            "报销",
            15800,
            "研发部",
            "李华",
            base + timedelta(days=2),
            "cfo",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
                ("finance", "财务审核", "财务专员"),
            ],
        ),
        _case(
            "C-20260108-EXP003",
            "行政部办公用品报销",
            "expense_reimburse_v1",
            "报销",
            860,
            "行政部",
            "赵敏",
            base - timedelta(days=2),
            "pay",
            status="completed",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
                ("finance", "财务审核", "财务专员"),
                ("pay", "出纳付款", "出纳"),
            ],
        ),
        _case(
            "C-20260111-PUR001",
            "服务器扩容采购申请",
            "purchase_approve_v1",
            "采购",
            120000,
            "信息技术部",
            "陈刚",
            base + timedelta(days=1),
            "gm",
            history_nodes=[
                ("submit", "采购申请提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
                ("procurement", "采购部审核", "采购专员"),
                ("finance", "财务预算审核", "财务专员"),
            ],
        ),
        _case(
            "C-20260113-PUR002",
            "团队团建物资采购",
            "purchase_approve_v1",
            "采购",
            8500,
            "人力资源部",
            "周倩",
            base + timedelta(days=3),
            "procurement",
            history_nodes=[
                ("submit", "采购申请提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260109-CON001",
            "年度云服务框架合同",
            "contract_approve_v1",
            "合同",
            350000,
            "信息技术部",
            "陈刚",
            base - timedelta(days=1),
            "gm",
            history_nodes=[
                ("submit", "合同起草提交", "经办人"),
                ("legal", "法务审核", "法务专员"),
                ("finance", "财务审核", "财务专员"),
                ("dept_director", "部门总监审批", "部门总监"),
            ],
        ),
        _case(
            "C-20260114-CON002",
            "市场推广合作协议",
            "contract_approve_v1",
            "合同",
            48000,
            "市场部",
            "王小明",
            base + timedelta(days=4),
            "dept_director",
            history_nodes=[
                ("submit", "合同起草提交", "经办人"),
                ("legal", "法务审核", "法务专员"),
                ("finance", "财务审核", "财务专员"),
            ],
            stall_code="missing_docs",
            stall_note="缺少对方营业执照复印件与授权委托书",
            fields={"missing_docs": ["对方营业执照复印件", "授权委托书"]},
        ),
        _case(
            "C-20260115-LEA001",
            "年假申请-3天",
            "leave_request_v1",
            "请假",
            0,
            "研发部",
            "李华",
            base + timedelta(days=5),
            "director",
            fields={"days": 3},
            history_nodes=[
                ("submit", "员工提交请假", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260116-LEA002",
            "事假申请-1天",
            "leave_request_v1",
            "请假",
            0,
            "财务部",
            "孙悦",
            base + timedelta(days=6),
            "hr",
            fields={"days": 1},
            history_nodes=[
                ("submit", "员工提交请假", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260107-PUR003",
            "办公电脑采购（已完成）",
            "purchase_approve_v1",
            "采购",
            22000,
            "行政部",
            "赵敏",
            base - timedelta(days=3),
            "po",
            status="completed",
            history_nodes=[
                ("submit", "采购申请提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
                ("procurement", "采购部审核", "采购专员"),
                ("finance", "财务预算审核", "财务专员"),
                ("po", "下采购订单", "采购专员"),
            ],
        ),
        _case(
            "C-20260812-EXP101",
            "市场部展会差旅报销",
            "expense_reimburse_v1",
            "报销",
            6800,
            "市场部",
            "王小明",
            datetime(2026, 8, 12, 9, 0, 0),
            "finance",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260813-EXP102",
            "研发部加班餐费报销",
            "expense_reimburse_v1",
            "报销",
            2100,
            "研发部",
            "李华",
            datetime(2026, 8, 13, 10, 0, 0),
            "finance",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260814-EXP103",
            "行政部快递费报销",
            "expense_reimburse_v1",
            "报销",
            540,
            "行政部",
            "赵敏",
            datetime(2026, 8, 14, 11, 0, 0),
            "finance",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260815-EXP104",
            "信息技术部云资源报销",
            "expense_reimburse_v1",
            "报销",
            18600,
            "信息技术部",
            "陈刚",
            datetime(2026, 8, 15, 9, 30, 0),
            "finance",
            stall_code="overloaded",
            stall_note="财务部并行已满，排队延迟",
            history_nodes=[
                ("submit", "员工提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260816-CON101",
            "供应商框架补充协议",
            "contract_approve_v1",
            "合同",
            88000,
            "采购部",
            "周倩",
            datetime(2026, 8, 16, 9, 0, 0),
            "legal",
            stall_code="missing_docs",
            stall_note="缺少法务意见书与相对方资质文件",
            fields={"missing_docs": ["法务意见书", "相对方资质文件"]},
            history_nodes=[
                ("submit", "合同起草提交", "经办人"),
            ],
        ),
        _case(
            "C-20260817-PUR101",
            "办公家具紧急采购",
            "purchase_approve_v1",
            "采购",
            42000,
            "行政部",
            "赵敏",
            datetime(2026, 8, 17, 14, 0, 0),
            "procurement",
            stall_code="key_person_busy",
            stall_note="采购专员同时处理多单，关键人物忙碌",
            history_nodes=[
                ("submit", "采购申请提交", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
        _case(
            "C-20260818-LEA101",
            "事假申请-2天",
            "leave_request_v1",
            "请假",
            0,
            "市场部",
            "王小明",
            datetime(2026, 8, 18, 9, 0, 0),
            "hr",
            fields={"days": 2},
            history_nodes=[
                ("submit", "员工提交请假", "申请人"),
                ("dept_manager", "部门经理审批", "部门经理"),
            ],
        ),
    ]
    for c in cases:
        save_case(c)


def seed_gold() -> None:
    rows = [
        {
            "id": "g1",
            "template_id": "expense_reimburse_v1",
            "current_node": "finance",
            "amount": 3200,
            "expected_next": "pay",
        },
        {
            "id": "g2",
            "template_id": "expense_reimburse_v1",
            "current_node": "finance",
            "amount": 15800,
            "expected_next": "cfo",
        },
        {
            "id": "g3",
            "template_id": "purchase_approve_v1",
            "current_node": "finance",
            "amount": 120000,
            "expected_next": "gm",
        },
        {
            "id": "g4",
            "template_id": "purchase_approve_v1",
            "current_node": "finance",
            "amount": 8500,
            "expected_next": "po",
        },
        {
            "id": "g5",
            "template_id": "contract_approve_v1",
            "current_node": "dept_director",
            "amount": 350000,
            "expected_next": "gm",
        },
        {
            "id": "g6",
            "template_id": "contract_approve_v1",
            "current_node": "dept_director",
            "amount": 48000,
            "expected_next": "seal",
        },
        {
            "id": "g7",
            "template_id": "leave_request_v1",
            "current_node": "dept_manager",
            "amount": 0,
            "fields": {"days": 3},
            "expected_next": "director",
        },
        {
            "id": "g8",
            "template_id": "leave_request_v1",
            "current_node": "dept_manager",
            "amount": 0,
            "fields": {"days": 1},
            "expected_next": "hr",
        },
        {
            "id": "g9",
            "template_id": "expense_reimburse_v1",
            "current_node": "dept_manager",
            "amount": 500,
            "expected_next": "finance",
        },
        {
            "id": "g10",
            "template_id": "purchase_approve_v1",
            "current_node": "dept_manager",
            "amount": 1000,
            "expected_next": "procurement",
        },
    ]
    path = settings.eval_dir / "gold.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ensure_data_dirs()
    real_policies = [
        p
        for p in settings.policies_dir.glob("*.pdf")
        if not p.name.startswith("费用报销") and p.name not in POLICIES
    ]
    if real_policies:
        print("Skip writing demo PDFs/templates; real company policies already present.")
    else:
        font = _register_font()
        print(f"Using font: {font}")
        for name, text in POLICIES.items():
            write_pdf(settings.policies_dir / name, text, font)
            print(f"Wrote policy {name}")
        seed_templates()
        print("Wrote templates")
    seed_cases()
    print("Wrote cases")
    seed_gold()
    print("Wrote gold.jsonl")
    result = get_policy_store().ingest_all()
    print("Ingested RAG:", result)
    print("Done. Data dir:", settings.data_dir)


if __name__ == "__main__":
    main()
