"""Observability metrics API: aggregated summary and paginated raw traces."""

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import get_db
from app.schemas import MetricsSummaryResponse, MetricsTracesResponse, RequestMetricItem
from app.services.database import DatabaseManager

router = APIRouter(prefix="/api/metrics", tags=["Observability"])


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregated observability metrics dashboard",
)
async def metrics_summary(
    db: DatabaseManager = Depends(get_db),
) -> MetricsSummaryResponse:
    """Return aggregated request metrics: counts, error rate, latency percentiles, token usage, and cost."""
    summary = db.get_metrics_summary()
    traces = db.get_recent_traces(limit=20)
    recent = [RequestMetricItem(**t) for t in traces]
    return MetricsSummaryResponse(**summary, recent_traces=recent)


@router.get(
    "/traces",
    response_model=MetricsTracesResponse,
    status_code=status.HTTP_200_OK,
    summary="Paginated raw request trace records",
)
async def metrics_traces(
    limit: int = Query(default=100, ge=1, le=500, description="Max number of traces to return"),
    db: DatabaseManager = Depends(get_db),
) -> MetricsTracesResponse:
    """Return raw request traces ordered by most recent, up to the requested limit."""
    traces = db.get_recent_traces(limit=limit)
    items = [RequestMetricItem(**t) for t in traces]
    return MetricsTracesResponse(total=len(items), traces=items)
