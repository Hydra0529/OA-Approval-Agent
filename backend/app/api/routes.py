from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.bpmn.generator import template_to_bpmn
from app.config import settings
from app.engine.monitor import build_portfolio_item, estimate_timeline, next_step
from app.agents.orchestrator import learn_from_pdf
from app.agents.stall import diagnose_stall
from app.engine.org import calendar_day
from app.extract.policy_extract import extract_template_from_policy
from app.models.schema import (
    ApprovalCase,
    CaseDetail,
    CaseEvent,
    DeleteCasesRequest,
    EvalResult,
    ExtractTemplateRequest,
    PolicyAskRequest,
    PortfolioResponse,
    SubmitCaseRequest,
)
from app.rag.store import get_policy_store
from app.report.generator import generate_case_report
from app.org_store import load_departments, load_knowledge
from app.storage import (
    delete_case,
    ensure_data_dirs,
    get_case,
    get_template,
    list_policy_files,
    load_all_templates,
    load_cases,
    load_templates,
    save_case,
    save_template,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_enabled": settings.llm_enabled,
        "templates": len(load_templates()),
        "cases": len(load_cases()),
    }


@router.get("/policies")
def policies() -> list[dict]:
    return list_policy_files()


@router.post("/policies/ingest")
def ingest_policies() -> dict:
    store = get_policy_store()
    result = store.ingest_all()
    return {"ingested": result, "total_chunks": sum(result.values())}


def _safe_pdf_name(raw: str) -> str:
    name = Path(raw or "policy.pdf").name
    name = name.replace("\\", "_").replace("/", "_")
    stem = Path(name).stem.strip() or "policy"
    stem = "".join(ch for ch in stem if ch not in '<>:"|?*')
    return f"{stem}.pdf"


@router.post("/policies/upload")
async def upload_policy(
    file: UploadFile = File(...),
    extract: bool = True,
    approve: bool = True,
) -> dict:
    ensure_data_dirs()
    original = file.filename or "policy.pdf"
    if not original.lower().endswith(".pdf"):
        raise HTTPException(400, "只支持 PDF 文件")
    data = await file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "文件过大（上限 12MB）")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "不是有效的 PDF 文件")

    filename = _safe_pdf_name(original)
    dest = settings.policies_dir / filename
    dest.write_bytes(data)

    chunks = get_policy_store().ingest_pdf(dest)
    report = None
    template = None
    if extract:
        report = learn_from_pdf(dest, approve=approve)
        template = report.template
        chunks = report.chunks

    return {
        "filename": filename,
        "size": len(data),
        "chunks": chunks,
        "template": template,
        "learning": report.model_dump() if report else None,
    }


@router.post("/policies/ask")
def ask_policy(body: PolicyAskRequest) -> dict:
    store = get_policy_store()
    hits = store.query(body.question, top_k=body.top_k)
    return {"question": body.question, "citations": hits}


@router.get("/policies/{filename}")
def download_policy(filename: str):
    path = settings.policies_dir / filename
    if not path.exists():
        raise HTTPException(404, "policy not found")
    return FileResponse(path)


@router.get("/templates")
def templates() -> list[dict]:
    return [t.model_dump() for t in load_templates()]


@router.get("/templates/{template_id}")
def template_detail(template_id: str) -> dict:
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, "template not found")
    return t.model_dump()


@router.post("/templates/extract")
def extract_template(body: ExtractTemplateRequest) -> dict:
    path = settings.policies_dir / body.policy_filename
    if not path.exists():
        raise HTTPException(404, "policy file not found")
    # Ensure RAG has this file
    get_policy_store().ingest_pdf(path)
    report = learn_from_pdf(path, approve=body.approve)
    return report.model_dump()


@router.post("/templates/{template_id}/approve")
def approve_template(template_id: str) -> dict:
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, "template not found")
    t.approved = True
    save_template(t)
    return t.model_dump()


@router.get("/portfolio", response_model=PortfolioResponse)
def portfolio() -> PortfolioResponse:
    items = []
    for case in load_cases():
        tmpl = get_template(case.template_id)
        if not tmpl:
            continue
        items.append(build_portfolio_item(case, tmpl))
    items.sort(key=lambda x: x.actual_start, reverse=True)
    return PortfolioResponse(items=items, total=len(items))


@router.get("/cases")
def cases() -> list[dict]:
    return [c.model_dump() for c in load_cases()]


@router.get("/cases/{case_id}", response_model=CaseDetail)
def case_detail(case_id: str) -> CaseDetail:
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    tmpl = get_template(case.template_id)
    if not tmpl:
        raise HTTPException(404, "template not found")
    timeline = estimate_timeline(case, tmpl)
    _, _, next_summary = next_step(case, tmpl)
    bpmn_xml = template_to_bpmn(tmpl, case)
    report, citations = generate_case_report(case, tmpl)
    all_cases = load_cases()
    tmpls = {t.id: t for t in load_all_templates()}
    stall_code, stall_reason, delay_days = diagnose_stall(case, tmpl, all_cases, tmpls)
    from app.engine.org import case_current_dept_load

    load = case_current_dept_load(case, tmpl, all_cases, tmpls)
    return CaseDetail(
        case=case,
        timeline=timeline,
        next_summary=next_summary,
        bpmn_xml=bpmn_xml,
        report=report,
        citations=citations,
        stall_reason=stall_reason,
        delay_days=delay_days,
        department_load=load,
    )


@router.post("/cases/submit", response_model=CaseDetail)
def submit_case(body: SubmitCaseRequest) -> CaseDetail:
    tmpl = get_template(body.template_id)
    if not tmpl:
        raise HTTPException(404, "template not found")
    if not tmpl.nodes:
        raise HTTPException(400, "template has no nodes")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    allowed = {d["name"] for d in load_departments()}
    if body.dept not in allowed:
        raise HTTPException(
            400,
            f"部门必须从制度识别清单中选择，不能自填。可选：{'、'.join(sorted(allowed))}",
        )
    first = tmpl.nodes[0]
    # After submit, current node is typically the first approval node
    current = tmpl.nodes[1].id if len(tmpl.nodes) > 1 else first.id
    case_id = f"C-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    case = ApprovalCase(
        case_id=case_id,
        title=body.title,
        template_id=tmpl.id,
        category=tmpl.category,
        amount=body.amount,
        level=body.level,
        dept=body.dept,
        applicant=body.applicant,
        submit_at=now,
        current_node=current,
        status="running",
        fields=body.fields,
        history=[
            CaseEvent(
                at=now,
                node_id=first.id,
                node_name=first.name,
                role=first.role,
                action="submit",
                note="模拟提交",
            )
        ],
    )
    save_case(case)
    return case_detail(case_id)


@router.post("/cases/submit-pack", response_model=CaseDetail)
async def submit_pack(
    files: list[UploadFile] | None = File(default=None),
    title: str = Form(""),
    applicant: str = Form(""),
    dept: str = Form(""),
    amount: float = Form(0),
    body_text: str = Form(""),
) -> CaseDetail:
    """Read uploaded application files (and/or pasted text), then generate a per-case process."""
    ensure_data_dirs()
    uploads_dir = settings.data_dir / "applications"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    texts: list[tuple[str, str]] = []
    for f in files or []:
        raw_name = Path(f.filename or "申报.txt").name
        data = await f.read()
        if not data:
            continue
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = uploads_dir / f"{stamp}_{raw_name}"
        dest.write_bytes(data)
        if raw_name.lower().endswith(".pdf"):
            from app.ingest.pdf_parser import extract_pdf_text

            texts.append((raw_name, extract_pdf_text(dest)))
        else:
            texts.append((raw_name, data.decode("utf-8", errors="ignore")))
    if body_text.strip():
        texts.append(("粘贴正文.txt", body_text.strip()))
    if not texts:
        raise HTTPException(400, "请上传申报文件或粘贴申报正文")

    from app.agents.intake import case_from_intake, run_intake

    overrides: dict = {}
    if title.strip():
        overrides["title"] = title.strip()
    if applicant.strip():
        overrides["applicant"] = applicant.strip()
    if dept.strip():
        overrides["dept"] = dept.strip()
    if amount:
        overrides["amount"] = amount
    pack = run_intake(texts, overrides)
    case = case_from_intake(pack)
    save_case(case)
    return case_detail(case.case_id)


@router.post("/cases/{case_id}/supplement", response_model=CaseDetail)
async def supplement_case(
    case_id: str,
    files: list[UploadFile] | None = File(default=None),
) -> CaseDetail:
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    if case.status != "running":
        raise HTTPException(400, "已结束的单据不能再补充材料")
    uploads_dir = settings.data_dir / "applications"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    extra: list[str] = []
    for f in files or []:
        raw_name = Path(f.filename or "补充材料.txt").name
        data = await f.read()
        if not data:
            continue
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = uploads_dir / f"{stamp}_{case_id}_{raw_name}"
        dest.write_bytes(data)
        extra.append(raw_name)
    if not extra:
        raise HTTPException(400, "请选择要补充的文件")
    from app.agents.intake import apply_supplement

    case = apply_supplement(case, extra)
    save_case(case)
    return case_detail(case.case_id)


@router.delete("/cases/{case_id}")
def remove_case(case_id: str) -> dict:
    if not get_case(case_id):
        raise HTTPException(404, "case not found")
    delete_case(case_id)
    return {"deleted": [case_id]}


@router.post("/cases/delete")
def remove_cases(body: DeleteCasesRequest) -> dict:
    ids = [cid.strip() for cid in body.case_ids if cid and cid.strip()]
    if not ids:
        raise HTTPException(400, "请选择要删除的项目")
    deleted: list[str] = []
    missing: list[str] = []
    for cid in ids:
        if get_case(cid):
            delete_case(cid)
            deleted.append(cid)
        else:
            missing.append(cid)
    if not deleted:
        raise HTTPException(404, "没有找到可删除的项目")
    return {"deleted": deleted, "missing": missing}


@router.get("/eval/run", response_model=EvalResult)
def run_eval() -> EvalResult:
    ensure_data_dirs()
    gold_path = settings.eval_dir / "gold.jsonl"
    if not gold_path.exists():
        raise HTTPException(404, "gold.jsonl not found")

    details: list[dict] = []
    correct = 0
    total = 0
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        total += 1
        tmpl = get_template(item["template_id"])
        if not tmpl:
            details.append({**item, "ok": False, "reason": "template missing"})
            continue
        case = ApprovalCase(
            case_id=f"eval-{total}",
            title="eval",
            template_id=tmpl.id,
            category=tmpl.category,
            amount=item.get("amount", 0),
            dept=item.get("dept", "测试部"),
            applicant="评测",
            submit_at=datetime(2026, 1, 10),
            current_node=item["current_node"],
            status="running",
            fields=item.get("fields", {}),
        )
        _, nxt, _ = next_step(case, tmpl)
        predicted = nxt.id if nxt else None
        expected = item["expected_next"]
        ok = predicted == expected
        if ok:
            correct += 1
        details.append(
            {
                "id": item.get("id", total),
                "expected": expected,
                "predicted": predicted,
                "ok": ok,
            }
        )
    acc = (correct / total) if total else 0.0
    return EvalResult(total=total, correct=correct, accuracy=acc, details=details)


@router.get("/departments")
def departments() -> dict:
    return {"departments": load_departments()}


@router.get("/knowledge")
def knowledge() -> dict:
    return load_knowledge()


@router.get("/calendar")
def calendar(month: str | None = None, date_str: str | None = None) -> dict:
    today = date.today()
    if date_str:
        try:
            selected = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(400, "date_str 格式应为 YYYY-MM-DD")
    else:
        selected = today
    if selected > today:
        raise HTTPException(400, "只能查看今天及以前的部门忙闲")

    if month:
        try:
            y, m = month.split("-")
            year, mon = int(y), int(m)
        except Exception:
            raise HTTPException(400, "month 格式应为 YYYY-MM")
    else:
        year, mon = selected.year, selected.month

    cases = load_cases()
    templates = {t.id: t for t in load_all_templates()}
    from calendar import monthrange

    n = monthrange(year, mon)[1]
    days = {}
    for d in range(1, n + 1):
        day = date(year, mon, d)
        if day > today:
            days[day.isoformat()] = "future"
            continue
        info = calendar_day(day, cases, templates)
        days[day.isoformat()] = info["overall"]

    picked = calendar_day(selected, cases, templates)
    return {
        "today": today.isoformat(),
        "month": f"{year:04d}-{mon:02d}",
        "selected": picked,
        "days": days,
        "legend": {
            "idle": "空闲",
            "busy": "忙碌",
            "saturated": "饱和",
            "future": "尚未发生",
        },
    }
