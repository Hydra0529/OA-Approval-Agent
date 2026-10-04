"""Look up city / equipment legal constraints. Live search first, then local fallback."""

from __future__ import annotations

import re

import httpx

BUILTIN: dict[tuple[str, str], dict] = {
    ("北京", "无人机"): {
        "summary": "北京市中心城区、一环及周边多为民用无人机禁飞或严格管控区域，作业前须向民航、公安等部门申请空域并备案。",
        "required_docs": ["民用无人驾驶航空器飞行活动申请", "空域批准/报备材料"],
        "source": "本地合规知识（北京无人机管控）",
    },
    ("上海", "无人机"): {
        "summary": "上海核心城区及机场净空区对无人机有报备/禁飞要求，作业需按当地规定申请。",
        "required_docs": ["无人机飞行活动申请", "当地主管部门备案材料"],
        "source": "本地合规知识（上海无人机管控）",
    },
    ("北京", "封路"): {
        "summary": "在城市道路实施封路、占道或挖掘作业，一般须向交通或城管部门申请道路占用/挖掘许可，并提交交通组织方案。",
        "required_docs": ["道路占用/挖掘许可", "交通组织或封路方案"],
        "source": "本地合规知识（北京占道施工）",
    },
    ("上海", "封路"): {
        "summary": "上海占道施工、道路封闭作业通常需要道路占用许可及交通组织方案，未经批准不得擅自封路。",
        "required_docs": ["道路占用/挖掘许可", "交通组织或封路方案"],
        "source": "本地合规知识（上海占道施工）",
    },
    ("北京", "钓鱼"): {
        "summary": "在城市水域、公园或天然河道垂钓、捕捞，可能受禁渔期、水域管理和属地许可约束。",
        "required_docs": ["属地渔业或水域管理部门许可/备案材料"],
        "source": "本地合规知识（北京水域作业）",
    },
    ("上海", "钓鱼"): {
        "summary": "上海部分水域禁止或限制垂钓、捕捞，作业前应向属地渔业或园林管理部门确认许可要求。",
        "required_docs": ["属地渔业或水域管理部门许可/备案材料"],
        "source": "本地合规知识（上海水域作业）",
    },
}


def search_web(query: str, limit: int = 4) -> list[dict]:
    hits: list[dict] = []
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": "OA-Agent/1.0"}) as client:
            r = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            r.raise_for_status()
            html = r.text
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', html, flags=re.I | re.S)
        urls = re.findall(r'class="result__url"[^>]*>(.*?)</', html, flags=re.I | re.S)
        n = min(limit, max(len(titles), len(snippets)))
        for i in range(n):
            title = re.sub(r"<[^>]+>", "", titles[i] if i < len(titles) else "").strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i] if i < len(snippets) else "").strip()
            url = re.sub(r"<[^>]+>", "", urls[i] if i < len(urls) else "").strip()
            if title or snippet:
                hits.append({"title": title, "snippet": snippet, "url": url, "query": query})
    except Exception:
        return []
    return hits


def lookup_restriction(city: str, topic: str) -> dict:
    city = (city or "").strip()
    topic = topic or "作业限制"
    query = f"{city} {topic} 许可 报备 规定 审批"
    web = search_web(query) if city else []
    builtin = None
    for c, t in BUILTIN:
        if c in city and t in topic:
            builtin = BUILTIN[(c, t)]
            break
    if not builtin and "无人机" in topic:
        builtin = {
            "summary": f"{city or '作业地'}开展无人机作业可能涉及禁飞区与报备。未附当地飞行活动申请/备案材料时，审批应卡住。",
            "required_docs": ["当地无人机飞行活动申请或报备材料"],
            "source": "通用合规规则",
        }
    elif not builtin and any(k in topic for k in ("封路", "占道")):
        builtin = {
            "summary": f"{city or '作业地'}实施封路或占道施工，一般需要道路占用/挖掘许可及交通组织方案。未附许可材料时，审批应卡住。",
            "required_docs": ["道路占用/挖掘许可", "交通组织或封路方案"],
            "source": "通用合规规则",
        }
    elif not builtin and any(k in topic for k in ("钓鱼", "垂钓", "捕捞")):
        builtin = {
            "summary": f"{city or '作业地'}开展垂钓或捕捞，可能涉及禁渔期与属地水域许可。未附许可/备案材料时，审批应卡住。",
            "required_docs": ["属地渔业或水域管理部门许可/备案材料"],
            "source": "通用合规规则",
        }
    summary = builtin["summary"] if builtin else ""
    if web:
        summary = (summary + " 联网检索到相关公开信息，见页面「联网查询」。").strip()
    elif city:
        summary = (summary + " 本次联网未返回可用条目，已用本地合规规则继续审查。").strip()
    return {
        "city": city,
        "topic": topic,
        "query": query,
        "web_hits": web,
        "summary": summary,
        "required_docs": list(builtin["required_docs"]) if builtin else [],
        "source": builtin["source"] if builtin else "web",
    }
