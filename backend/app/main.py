from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.storage import ensure_data_dirs

ensure_data_dirs()

app = FastAPI(
    title="OA Approval AI Agent",
    description="制度学习 → 流程模板 → 项目群清单 / 时间线 / BPMN / 报告",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"service": "oa-approval-ai-agent", "docs": "/docs", "api": "/api/health"}
