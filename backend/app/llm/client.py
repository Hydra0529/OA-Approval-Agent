from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import settings


def get_client() -> OpenAI | None:
    if not settings.llm_enabled:
        return None
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


def chat_json(system: str, user: str) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def chat_text(system: str, user: str) -> str | None:
    client = get_client()
    if client is None:
        return None
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content
