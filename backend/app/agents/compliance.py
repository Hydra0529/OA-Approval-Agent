"""Identify extra legal documents for regulated field work."""

from __future__ import annotations

import re

from app.agents.web_lookup import lookup_restriction
from app.llm.client import chat_json

ACTIVITY_RULES: list[dict] = [
    {
        "name": "无人机作业",
        "keywords": ("无人机", "无人驾驶航空器", "航拍器", "drone"),
        "required_docs": ["民用无人驾驶航空器飞行活动申请", "空域批准/报备材料"],
        "lookup_topic": "无人机",
    },
    {
        "name": "道路占用或封路施工",
        "keywords": ("封路", "道路封闭", "占道施工", "占道作业", "交通管制", "挖掘道路", "道路开挖"),
        "required_docs": ["道路占用/挖掘许可", "交通组织或封路方案"],
        "lookup_topic": "占道施工 封路",
    },
    {
        "name": "垂钓或捕捞作业",
        "keywords": ("钓鱼", "垂钓", "捕捞", "禁渔"),
        "required_docs": ["属地渔业或水域管理部门许可/备案材料"],
        "lookup_topic": "钓鱼 捕捞 许可",
    },
]

DOC_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("飞行", ("飞行活动申请", "飞行申请", "空域批准", "空域", "无人机报备", "报备材料")),
    ("空域", ("空域批准", "空域", "报备")),
    ("无人机", ("飞行活动申请", "空域批准", "无人机报备", "报备")),
    ("道路", ("道路占用", "占道", "挖掘许可", "封路", "交通组织")),
    ("占道", ("占道", "道路占用", "挖掘许可")),
    ("封路", ("封路", "交通管制", "交通组织")),
    ("交通", ("交通组织", "交通管制", "封路方案")),
    ("渔", ("渔业", "垂钓许可", "捕捞许可", "水域许可")),
    ("钓", ("垂钓许可", "钓鱼许可", "渔业")),
    ("捕捞", ("捕捞许可", "渔业")),
]

LLM_SYSTEM = (
    "你是企业法务合规助手。立项申报书、工作方案通常只写要做什么、在哪里做、用什么设备，"
    "不会列出需要向当地哪些部门申请哪些文件。你的任务是读正文，根据作业内容、地点、设备、"
    "是否占道或进入管制区域，推断法务审核还缺哪些外部许可、报备或专项材料。"
    "只输出 JSON："
    '{"need_legal_review":false,"activities":[{"name":"","reason":"","required_docs":["完整材料名称"]}]}。'
    "required_docs 必须是字符串数组，每个元素是完整文件名，禁止拆成单字。"
    "规则："
    "1. 不要等正文出现“需提供××许可”才列材料；正文没写材料名称也必须按作业性质推断。"
    "2. required_docs 写当地主管部门通常会要的具体文件名，便于和附件文件名核对。"
    "3. reason 用一句话说明从正文哪类作业推出这些材料。"
    "4. 纯室内办公、常规票据报销、常规货物采购、常规合同审签、请假，没有外业或公共空间作业时，"
    "activities 为空，need_legal_review 为 false。"
    "5. 正文写明不涉及、不使用某项时不要列入。"
    "6. 不要编造与正文作业无关的材料；推断须能从正文的地点或作业描述说得通。"
)


def _mentioned(blob: str, word: str) -> bool:
    if not word or word not in blob:
        return False
    if re.search(rf"(不涉及|不使用|不含|没有|未使用|无需).{{0,12}}{re.escape(word)}", blob):
        return False
    return True


def detect_activities(text: str) -> list[dict]:
    blob = text or ""
    found: list[dict] = []
    for rule in ACTIVITY_RULES:
        if any(_mentioned(blob, w) for w in rule["keywords"]):
            found.append(
                {
                    "name": rule["name"],
                    "reason": "申报正文出现受控作业关键词",
                    "required_docs": list(rule["required_docs"]),
                    "lookup_topic": rule["lookup_topic"],
                    "source": "keyword",
                }
            )
    return found


def _merge_activities(*groups: list[dict]) -> list[dict]:
    by_name: dict[str, dict] = {}
    for group in groups:
        for item in group:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            docs = [str(x).strip() for x in (item.get("required_docs") or []) if str(x).strip()]
            prev = by_name.get(name)
            if prev:
                prev["required_docs"] = list(dict.fromkeys([*prev["required_docs"], *docs]))
                if item.get("reason") and not prev.get("reason"):
                    prev["reason"] = item["reason"]
                if item.get("lookup_topic") and not prev.get("lookup_topic"):
                    prev["lookup_topic"] = item["lookup_topic"]
                if item.get("source") == "llm":
                    prev["source"] = "llm"
                continue
            by_name[name] = {
                "name": name,
                "reason": str(item.get("reason") or ""),
                "required_docs": list(dict.fromkeys(docs)),
                "lookup_topic": str(item.get("lookup_topic") or name),
                "source": str(item.get("source") or "keyword"),
            }
    return list(by_name.values())


def _as_doc_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[、,，;；\n]+", raw)
        return [p.strip() for p in parts if len(p.strip()) >= 2]
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            out.extend(_as_doc_list(item))
        return out
    text = str(raw).strip()
    return [text] if len(text) >= 2 else []


def _parse_llm_activities(data: dict | None) -> list[dict]:
    if not data:
        return []
    rows = data.get("activities") if isinstance(data.get("activities"), list) else []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        docs = [x for x in _as_doc_list(row.get("required_docs")) if len(x) >= 2]
        if not name or not docs:
            continue
        out.append(
            {
                "name": name[:40],
                "reason": str(row.get("reason") or "大模型根据申报正文识别")[:160],
                "required_docs": docs[:8],
                "lookup_topic": name[:40],
                "source": "llm",
            }
        )
    return out


def identify_requirements(text: str, extracted: dict, policy_hits: list[dict] | None = None) -> dict:
    """Keyword rules always apply; LLM adds extra documents when a model key is configured."""
    from app.config import settings

    ruled = detect_activities(text)
    llm_rows: list[dict] = []
    used_llm = False
    if settings.llm_enabled:
        snippets = "\n".join((h.get("text") or "")[:240] for h in (policy_hits or [])[:6])
        city = str((extracted or {}).get("city") or "")
        category = str((extracted or {}).get("category") or "")
        title = str((extracted or {}).get("title") or "")
        try:
            data = chat_json(
                LLM_SYSTEM,
                (
                    f"已抽取字段：类型={category}，城市={city}，标题={title}。\n"
                    "请根据下面的申报正文推断当地审批还缺哪些文件。"
                    "正文里通常不会写材料清单。\n\n"
                    f"申报正文：\n{(text or '')[:8000]}\n\n制度片段：\n{snippets[:3000]}"
                ),
            )
            used_llm = data is not None
            llm_rows = _parse_llm_activities(data)
        except Exception:
            used_llm = False
            llm_rows = []

    activities = _merge_activities(ruled, llm_rows)
    required: list[str] = []
    for item in activities:
        required.extend(item.get("required_docs") or [])
    return {
        "activities": [a["name"] for a in activities],
        "activity_details": activities,
        "required_docs": list(dict.fromkeys(required)),
        "used_llm": used_llm,
    }


def _hints_for(doc: str) -> list[str]:
    hints = [doc]
    for key, extra in DOC_HINTS:
        if key in doc:
            hints.extend(extra)
    return list(dict.fromkeys(h for h in hints if h))


def doc_attached(doc: str, filenames: list[str], body: str = "") -> bool:
    name_blob = " ".join(filenames)
    blob = f"{name_blob}\n{body or ''}"
    hints = _hints_for(doc)
    alt = "|".join(re.escape(h) for h in hints if len(h) >= 2)
    if alt and re.search(rf"(未附|未提交|没有附|尚未[提交附]|缺少|未提供|未一并提交).{{0,24}}({alt})", body or ""):
        # A newly uploaded filename still counts as attached.
        if not any(h in name_blob for h in hints):
            return False
    for h in hints:
        if h and h in name_blob:
            return True
        if h and re.search(rf"(已附|已提交|随附|附件[：:].{{0,40}}){re.escape(h)}", body or ""):
            return True
    return False


def missing_docs(required: list[str], filenames: list[str], body: str = "") -> list[str]:
    return [d for d in required if not doc_attached(d, filenames, body)]


def review_activities(
    extracted: dict,
    filenames: list[str],
    body: str = "",
) -> dict:
    city = extracted.get("city") or ""
    details = list(extracted.get("activity_details") or [])
    required = list(extracted.get("required_docs") or [])
    if not details and not required:
        pack = identify_requirements(body, extracted, extracted.get("policy_hits") or [])
        details = pack["activity_details"]
        required = pack["required_docs"]
        extracted["used_llm"] = pack["used_llm"]

    findings: list[dict] = []
    web_hits: list[dict] = []
    missing: list[str] = []

    extra = ""
    if (city == "北京" or "北京" in city) and extracted.get("inner_ring"):
        extra = "申报写明一环/二环以内或核心城区，属地限制通常更严。"

    if details:
        for item in details:
            look = lookup_restriction(city or "未填写城市", item.get("lookup_topic") or item["name"])
            web_hits.extend(look.get("web_hits") or [])
            docs = list(item.get("required_docs") or look.get("required_docs") or [])
            miss = missing_docs(docs, filenames, body)
            missing.extend(miss)
            summary = " ".join(
                x for x in ((look.get("summary") or ""), item.get("reason") or "", extra) if x
            ).strip()
            findings.append(
                {
                    "topic": item["name"],
                    "city": city,
                    "summary": summary,
                    "required_docs": docs,
                    "missing_docs": miss,
                    "source": item.get("source") or look.get("source"),
                    "query": look.get("query"),
                }
            )
    elif required:
        miss = missing_docs(required, filenames, body)
        missing.extend(miss)
        findings.append(
            {
                "topic": "法务额外材料",
                "city": city,
                "summary": extra,
                "required_docs": required,
                "missing_docs": miss,
                "source": "stored",
                "query": "",
            }
        )

    return {
        "findings": findings,
        "web_hits": web_hits,
        "missing_docs": list(dict.fromkeys(missing)),
        "blocked": bool(missing),
        "activities": [d["name"] for d in details],
        "required_docs": list(dict.fromkeys(required)),
    }
