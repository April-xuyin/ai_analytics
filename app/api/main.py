"""FastAPI application exposing the natural-language analytics service."""

from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.audit import AuditLogger
from app.auth import AuthorizationError, authenticate
from app.intent.deepseek import DeepSeekIntentParser
from app.metadata.loader import MetadataCatalog
from app.metrics import metrics
from app.query.local_runner import LocalQueryRunner
from app.query.maxcompute_runner import MaxComputeQueryRunner
from app.questions.models import AnalyticsAnswer
from app.questions.service import QuestionService

PROJECT_DIR = Path(__file__).resolve().parents[2]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    previous_question: str | None = Field(default=None, max_length=500)


class AskResponse(BaseModel):
    question: str
    status: str
    message: str
    datasets: list[str]
    metrics: list[str]
    metric_definition: str | None = None
    data_start_date: Any | None = None
    data_end_date: Any | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class MeResponse(BaseModel):
    name: str
    role: str
    shops: list[str]


def load_env_file(path: Path) -> None:
    """Load local KEY=VALUE settings without logging secrets."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_service() -> tuple[QuestionService, DeepSeekIntentParser]:
    load_env_file(PROJECT_DIR / ".env")
    catalog = MetadataCatalog(PROJECT_DIR / "metadata")
    if os.getenv("QUERY_ENGINE", "local").lower() == "maxcompute":
        runner = MaxComputeQueryRunner(PROJECT_DIR / "metadata" / "datasets.yaml")
    else:
        runner = LocalQueryRunner(
            PROJECT_DIR / "data" / "parquet",
            PROJECT_DIR / "metadata" / "datasets.yaml",
        )
    audit = AuditLogger(PROJECT_DIR / "logs" / "audit.jsonl")
    return QuestionService(runner, catalog, audit=audit), DeepSeekIntentParser(catalog)


app = FastAPI(title="VG AI Analytics", version="0.1.0")


@app.middleware("http")
async def observe_http(request: Request, call_next):
    started = monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/metrics":
            metrics.record_http(
                request.method,
                request.url.path,
                status_code,
                monotonic() - started,
            )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(x_api_key: str | None = Header(default=None)) -> PlainTextResponse:
    principal = authenticate(x_api_key)
    if os.getenv("API_AUTH_TOKEN"):
        if principal is None:
            raise HTTPException(status_code=401, detail="无效的 API 访问令牌")
        if not principal.is_admin:
            raise HTTPException(status_code=403, detail="只有管理员可以查看监控指标")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


@app.get("/me", response_model=MeResponse)
def current_user(x_api_key: str | None = Header(default=None)) -> MeResponse:
    principal = authenticate(x_api_key)
    if (os.getenv("API_AUTH_TOKEN") or os.getenv("OPERATOR_API_TOKEN")) and principal is None:
        raise HTTPException(status_code=401, detail="无效的 API 访问令牌")
    if principal is None:
        return MeResponse(name="anonymous", role="unconfigured", shops=[])
    return MeResponse(name=principal.name, role=principal.role, shops=list(principal.shops))


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, x_api_key: str | None = Header(default=None)) -> AskResponse:
    try:
        principal = authenticate(x_api_key)
        if (os.getenv("API_AUTH_TOKEN") or os.getenv("OPERATOR_API_TOKEN")) and principal is None:
            metrics.record_question_outcome("unauthorized")
            raise HTTPException(status_code=401, detail="无效的 API 访问令牌")
        service, parser = build_service()
        parsing_question = request.question
        if request.previous_question:
            parsing_question = (
                f"上一轮问题：{request.previous_question}\n"
                f"当前追问：{request.question}\n"
                "请沿用上一轮中未被当前追问修改的指标、时间和筛选条件。"
            )
        intent = parser.parse(parsing_question)
        if intent.needs_clarification:
            answer = AnalyticsAnswer(
                question=request.question,
                status="clarification_needed",
                message=intent.clarification_question or "请补充问题信息。",
            )
        else:
            try:
                answer = service.ask_with_intent(request.question, intent, principal=principal)
            except AuthorizationError as exc:
                metrics.record_question_outcome("denied")
                raise HTTPException(status_code=403, detail=str(exc)) from exc
        metrics.record_question_outcome(answer.status)
        return AskResponse(**answer.to_dict())
    except HTTPException:
        raise
    except Exception as exc:
        metrics.record_question_outcome("error")
        raise HTTPException(status_code=500, detail="问数服务暂时不可用") from exc


# API 路由定义后再挂载根路径，避免静态页面覆盖 /health 和 /ask。
app.mount("/", StaticFiles(directory=PROJECT_DIR / "web", html=True), name="web")
