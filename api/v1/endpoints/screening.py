from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.screening import (
    ScreeningCandidateDetailResponse,
    CreateScreeningRunRequest,
    ScreeningNotifyRequest,
    ScreeningCandidateListResponse,
    ScreeningRunListResponse,
    ScreeningRunResponse,
    ScreeningStrategyListResponse,
)
from api.v1.schemas.common import SuccessResponse
from src.services.screening_notification_service import (
    ScreeningNotificationService,
    ScreeningRunNotFoundError,
    ScreeningRunNotReadyError,
)
from src.services.screening_task_service import ScreeningTaskService

router = APIRouter()


def get_screening_strategies() -> list[dict]:
    """Load available strategies from SkillManager."""
    from src.agent.skills.base import SkillManager
    mgr = SkillManager()
    mgr.load_builtin_strategies()
    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "category": s.category,
            "has_screening_rules": s.screening is not None,
        }
        for s in mgr.list_skills()
    ]


@router.get("/strategies", response_model=ScreeningStrategyListResponse, summary="获取可用筛选策略列表")
def list_screening_strategies() -> ScreeningStrategyListResponse:
    strategies = get_screening_strategies()
    return ScreeningStrategyListResponse(strategies=strategies)


@router.post("/runs", response_model=ScreeningRunResponse, summary="执行一次全市场筛选")
def create_screening_run(request: CreateScreeningRunRequest) -> ScreeningRunResponse:
    service = ScreeningTaskService()
    normalized_stock_codes = [
        str(code).strip()
        for code in (request.stock_codes or [])
        if str(code).strip()
    ]
    if request.stock_codes == [] or (request.stock_codes is not None and not normalized_stock_codes):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "stock_codes cannot be empty",
            },
        )
    runtime_config = service.resolve_run_config(
        mode=request.mode,
        candidate_limit=request.candidate_limit,
        ai_top_k=request.ai_top_k,
    )
    if runtime_config.ai_top_k > runtime_config.candidate_limit:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "ai_top_k cannot be greater than candidate_limit",
            },
        )
    try:
        result = service.execute_run(
            trade_date=request.trade_date,
            stock_codes=request.stock_codes,
            mode=request.mode,
            candidate_limit=request.candidate_limit,
            ai_top_k=request.ai_top_k,
            market=request.market,
            rerun_failed=request.rerun_failed,
            resume_from=request.resume_from,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": str(exc),
            },
        ) from exc
    return ScreeningRunResponse(**result)


@router.get("/runs", response_model=ScreeningRunListResponse, summary="查询筛选任务列表")
def list_screening_runs(limit: int = Query(20, ge=1, le=100)) -> ScreeningRunListResponse:
    service = ScreeningTaskService()
    items = [ScreeningRunResponse(**item) for item in service.list_runs(limit=limit)]
    return ScreeningRunListResponse(total=len(items), items=items)


@router.get("/runs/{run_id}", response_model=ScreeningRunResponse, summary="查询单次筛选任务")
def get_screening_run(run_id: str) -> ScreeningRunResponse:
    service = ScreeningTaskService()
    result = service.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "筛选任务不存在"})
    return ScreeningRunResponse(**result)


@router.get(
    "/runs/{run_id}/candidates",
    response_model=ScreeningCandidateListResponse,
    summary="查询筛选候选结果",
)
def list_screening_candidates(
    run_id: str,
    limit: int = Query(100, ge=1, le=500),
    with_ai_only: bool = Query(False),
) -> ScreeningCandidateListResponse:
    service = ScreeningTaskService()
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "筛选任务不存在"})
    if run.get("status") not in {"completed", "completed_with_ai_degraded"}:
        raise HTTPException(
            status_code=409,
            detail={"error": "run_not_ready", "message": "筛选任务尚未完成，候选结果不可用", "run_id": run_id},
        )
    items = service.list_candidates(run_id=run_id, limit=limit, with_ai_only=with_ai_only)
    return ScreeningCandidateListResponse(total=len(items), items=items)


@router.get(
    "/runs/{run_id}/candidates/{code}",
    response_model=ScreeningCandidateDetailResponse,
    summary="查询单只筛选候选详情",
)
def get_screening_candidate_detail(run_id: str, code: str) -> ScreeningCandidateDetailResponse:
    service = ScreeningTaskService()
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "筛选任务不存在"})
    if run.get("status") not in {"completed", "completed_with_ai_degraded"}:
        raise HTTPException(
            status_code=409,
            detail={"error": "run_not_ready", "message": "筛选任务尚未完成，候选详情不可用", "run_id": run_id},
        )

    result = service.get_candidate_detail(run_id=run_id, code=code)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "候选不存在", "run_id": run_id, "code": code},
        )
    return ScreeningCandidateDetailResponse(**result)


@router.post(
    "/runs/{run_id}/notify",
    response_model=SuccessResponse,
    summary="推送筛选推荐名单（幂等，支持 force 补发）",
)
def notify_screening_run(run_id: str, request: ScreeningNotifyRequest) -> SuccessResponse:
    service = ScreeningNotificationService()
    try:
        result = service.notify_run(
            run_id=run_id,
            force=request.force,
        )
    except ScreeningRunNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(exc), "run_id": run_id},
        ) from exc
    except ScreeningRunNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "conflict", "message": str(exc), "run_id": run_id},
        ) from exc

    success = bool(result.get("success")) and not result.get("skipped")
    message = result.get("reason") or result.get("notification_status") or "ok"
    return SuccessResponse(success=success, message=message, data=result)
