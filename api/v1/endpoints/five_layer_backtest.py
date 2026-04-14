# -*- coding: utf-8 -*-
"""Five-layer backtest API endpoints.

Run-based endpoints indexed by ``backtest_run_id``.
Replaces legacy advice-based backtest endpoints.

Routes:
  POST /run             – trigger a full pipeline backtest
  GET  /runs/{id}       – run detail
  GET  /runs/{id}/evaluations   – candidate-level evaluations
  GET  /runs/{id}/summaries     – group summaries
  GET  /runs/{id}/calibration   – calibration outputs
  GET  /runs/{id}/recommendations – graded recommendations
  POST /calibration     – compare two runs
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.five_layer_backtest import (
    FiveLayerBacktestRunRequest,
    FiveLayerCalibrationItem,
    FiveLayerCalibrationRequest,
    FiveLayerCalibrationResponse,
    FiveLayerEvaluationItem,
    FiveLayerEvaluationsResponse,
    FiveLayerFullPipelineResponse,
    FiveLayerGroupSummaryItem,
    FiveLayerRecommendationItem,
    FiveLayerRecommendationsResponse,
    FiveLayerRunResponse,
    FiveLayerSummariesResponse,
)
from src.backtest.services.backtest_service import FiveLayerBacktestService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


def _internal_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": message},
    )


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": f"无效日期格式 {field_name}: {value}，需要 YYYY-MM-DD"},
        )


def _run_to_response(run) -> FiveLayerRunResponse:
    d = run.to_dict()
    return FiveLayerRunResponse(**d)


# ── POST /run ──────────────────────────────────────────────────────────────

@router.post(
    "/run",
    response_model=FiveLayerFullPipelineResponse,
    responses={
        200: {"description": "回测完成"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="触发五层回测全流程",
    description="运行完整流程: 候选选择 → 分类 → 执行 → 评估 → 汇总 → 建议",
)
def run_five_layer_backtest(
    request: FiveLayerBacktestRunRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerFullPipelineResponse:
    date_from = _parse_date(request.trade_date_from, "trade_date_from")
    date_to = _parse_date(request.trade_date_to, "trade_date_to")

    if date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": "trade_date_from 不能晚于 trade_date_to"},
        )

    try:
        service = FiveLayerBacktestService(db_manager)
        result = service.run_full_pipeline(
            evaluation_mode=request.evaluation_mode,
            execution_model=request.execution_model,
            trade_date_from=date_from,
            trade_date_to=date_to,
            market=request.market,
            eval_window_days=request.eval_window_days,
            generate_recommendations=request.generate_recommendations,
        )

        run_resp = _run_to_response(result["run"])
        summaries = [
            FiveLayerGroupSummaryItem(**s.to_dict()) for s in (result.get("summaries") or [])
        ]
        recs = [
            FiveLayerRecommendationItem(**r.to_dict()) for r in (result.get("recommendations") or [])
        ]

        return FiveLayerFullPipelineResponse(run=run_resp, summaries=summaries, recommendations=recs)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("五层回测执行失败: %s", exc, exc_info=True)
        raise _internal_error("五层回测执行失败")


# ── GET /runs/{backtest_run_id} ────────────────────────────────────────────

@router.get(
    "/runs/{backtest_run_id}",
    response_model=FiveLayerRunResponse,
    responses={
        200: {"description": "运行详情"},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取回测运行详情",
)
def get_run_detail(
    backtest_run_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerRunResponse:
    try:
        service = FiveLayerBacktestService(db_manager)
        run = service.get_run(backtest_run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到运行 {backtest_run_id}"},
            )
        return _run_to_response(run)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询运行详情失败: %s", exc, exc_info=True)
        raise _internal_error("查询运行详情失败")


# ── GET /runs/{backtest_run_id}/evaluations ────────────────────────────────

@router.get(
    "/runs/{backtest_run_id}/evaluations",
    response_model=FiveLayerEvaluationsResponse,
    responses={
        200: {"description": "候选级评估列表"},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取候选级评估结果",
)
def get_evaluations(
    backtest_run_id: str,
    signal_family: str | None = Query(None, description="按信号类型过滤: entry / exit / observation"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerEvaluationsResponse:
    try:
        service = FiveLayerBacktestService(db_manager)
        run = service.get_run(backtest_run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到运行 {backtest_run_id}"},
            )

        evaluations = service.eval_repo.get_by_run(
            backtest_run_id, signal_family=signal_family,
        )
        total = len(evaluations)
        start = (page - 1) * limit
        page_items = evaluations[start : start + limit]
        items = [FiveLayerEvaluationItem(**e.to_dict()) for e in page_items]

        return FiveLayerEvaluationsResponse(
            backtest_run_id=backtest_run_id,
            total=total,
            page=page,
            limit=limit,
            items=items,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询评估结果失败: %s", exc, exc_info=True)
        raise _internal_error("查询评估结果失败")


# ── GET /runs/{backtest_run_id}/summaries ──────────────────────────────────

@router.get(
    "/runs/{backtest_run_id}/summaries",
    response_model=FiveLayerSummariesResponse,
    responses={
        200: {"description": "分组汇总列表"},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取分组汇总",
)
def get_summaries(
    backtest_run_id: str,
    group_type: str | None = Query(None, description="过滤分组类型: overall / signal_family / setup_type / ..."),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerSummariesResponse:
    try:
        service = FiveLayerBacktestService(db_manager)
        run = service.get_run(backtest_run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到运行 {backtest_run_id}"},
            )

        summaries = service.summary_repo.get_by_run(backtest_run_id, group_type=group_type)
        items = [FiveLayerGroupSummaryItem(**s.to_dict()) for s in summaries]

        return FiveLayerSummariesResponse(backtest_run_id=backtest_run_id, items=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询汇总失败: %s", exc, exc_info=True)
        raise _internal_error("查询汇总失败")


# ── GET /runs/{backtest_run_id}/calibration ────────────────────────────────

@router.get(
    "/runs/{backtest_run_id}/calibration",
    response_model=FiveLayerCalibrationResponse,
    responses={
        200: {"description": "校准对比结果"},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取校准对比结果",
)
def get_calibration(
    backtest_run_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerCalibrationResponse:
    try:
        service = FiveLayerBacktestService(db_manager)
        run = service.get_run(backtest_run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到运行 {backtest_run_id}"},
            )

        outputs = service.calibration_repo.get_by_run(backtest_run_id)
        items = [FiveLayerCalibrationItem(**o.to_dict()) for o in outputs]

        return FiveLayerCalibrationResponse(backtest_run_id=backtest_run_id, items=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询校准结果失败: %s", exc, exc_info=True)
        raise _internal_error("查询校准结果失败")


# ── GET /runs/{backtest_run_id}/recommendations ───────────────────────────

@router.get(
    "/runs/{backtest_run_id}/recommendations",
    response_model=FiveLayerRecommendationsResponse,
    responses={
        200: {"description": "分级建议列表"},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取分级建议",
)
def get_recommendations(
    backtest_run_id: str,
    recommendation_level: str | None = Query(None, description="过滤级别: observation / hypothesis / actionable"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerRecommendationsResponse:
    try:
        service = FiveLayerBacktestService(db_manager)
        run = service.get_run(backtest_run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"未找到运行 {backtest_run_id}"},
            )

        recs = service.recommendation_repo.get_by_run(
            backtest_run_id, recommendation_level=recommendation_level,
        )
        items = [FiveLayerRecommendationItem(**r.to_dict()) for r in recs]

        return FiveLayerRecommendationsResponse(backtest_run_id=backtest_run_id, items=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("查询建议失败: %s", exc, exc_info=True)
        raise _internal_error("查询建议失败")


# ── POST /calibration ─────────────────────────────────────────────────────

@router.post(
    "/calibration",
    response_model=FiveLayerCalibrationItem,
    responses={
        200: {"description": "校准对比完成"},
        400: {"description": "参数错误", "model": ErrorResponse},
        404: {"description": "运行不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="触发校准对比",
    description="比较两个已完成的回测运行，生成校准输出",
)
def run_calibration(
    request: FiveLayerCalibrationRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> FiveLayerCalibrationItem:
    try:
        service = FiveLayerBacktestService(db_manager)

        for run_id in (request.baseline_run_id, request.candidate_run_id):
            run = service.get_run(run_id)
            if run is None:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "not_found", "message": f"未找到运行 {run_id}"},
                )

        output = service.run_calibration_comparison(
            baseline_run_id=request.baseline_run_id,
            candidate_run_id=request.candidate_run_id,
            calibration_name=request.calibration_name,
            baseline_config=request.baseline_config,
            candidate_config=request.candidate_config,
        )

        if output is None:
            raise HTTPException(
                status_code=400,
                detail={"error": "calibration_failed", "message": "校准对比失败，请确保两个运行都已完成汇总计算"},
            )

        return FiveLayerCalibrationItem(**output.to_dict())
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("校准对比失败: %s", exc, exc_info=True)
        raise _internal_error("校准对比失败")
