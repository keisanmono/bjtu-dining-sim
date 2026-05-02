from __future__ import annotations

from dataclasses import dataclass, replace

from .simulation import MetricsSummary, SimulationConfigData, run_simulation


@dataclass(frozen=True)
class RecommendationRequestData:
    base_config: SimulationConfigData
    window_options: list[int]
    seat_options: list[int]
    stagger_options: list[int]
    top_k: int = 5


@dataclass(frozen=True)
class CandidateResultData:
    config: SimulationConfigData
    metrics: MetricsSummary
    score: float
    strategy: str


@dataclass(frozen=True)
class RecommendationResultData:
    baseline_metrics: MetricsSummary
    best: CandidateResultData
    ranking: list[CandidateResultData]
    explanation_summary: str
    alternatives: list[str]


def recommend_config(request: RecommendationRequestData) -> RecommendationResultData:
    baseline = run_simulation(request.base_config)
    candidates: list[CandidateResultData] = []
    seen: set[tuple[int, int, int]] = set()
    for windows in request.window_options:
        for seats in request.seat_options:
            for stagger in request.stagger_options:
                key = (windows, seats, stagger)
                if key in seen:
                    continue
                seen.add(key)
                config = replace(
                    request.base_config,
                    num_windows=windows,
                    num_seats=seats,
                    stagger_minutes=stagger,
                    layout=None,
                )
                result = run_simulation(config)
                candidates.append(
                    CandidateResultData(
                        config=config,
                        metrics=result.metrics,
                        score=_score_candidate(result.metrics, config, request.base_config),
                        strategy=_strategy_label(config, request.base_config),
                    )
                )
    if not candidates:
        raise ValueError("至少需要提供一组候选方案。")

    ranking = sorted(candidates, key=lambda item: (item.score, item.metrics.avg_wait, item.metrics.peak_queue))
    top_k = max(1, request.top_k)
    best = ranking[0]
    return RecommendationResultData(
        baseline_metrics=baseline.metrics,
        best=best,
        ranking=ranking[:top_k],
        explanation_summary=_build_summary(best, baseline.metrics),
        alternatives=[candidate.strategy for candidate in ranking[1:top_k]],
    )


def _score_candidate(metrics: MetricsSummary, config: SimulationConfigData, base: SimulationConfigData) -> float:
    added_window_cost = max(0, config.num_windows - base.num_windows) * 3.0
    added_seat_cost = max(0, config.num_seats - base.num_seats) * 0.05
    stagger_cost = max(0, config.stagger_minutes) * 0.08
    overload_penalty = 0.0
    if metrics.window_utilization > 0.92:
        overload_penalty += (metrics.window_utilization - 0.92) * 80
    if metrics.seat_utilization > 0.92:
        overload_penalty += (metrics.seat_utilization - 0.92) * 60
    return round(
        metrics.avg_wait * 3.0
        + metrics.peak_queue * 0.35
        + metrics.peak_waiting_for_seat * 0.45
        + added_window_cost
        + added_seat_cost
        + stagger_cost
        + overload_penalty,
        4,
    )


def _strategy_label(config: SimulationConfigData, base: SimulationConfigData) -> str:
    parts: list[str] = []
    if config.num_windows > base.num_windows:
        parts.append(f"窗口 +{config.num_windows - base.num_windows}")
    elif config.num_windows < base.num_windows:
        parts.append(f"窗口 {config.num_windows}")
    if config.num_seats > base.num_seats:
        parts.append(f"座位 +{config.num_seats - base.num_seats}")
    elif config.num_seats < base.num_seats:
        parts.append(f"座位 {config.num_seats}")
    if config.stagger_minutes:
        parts.append(f"错峰 {config.stagger_minutes} 分钟")
    return "，".join(parts) if parts else "保持基准配置"


def _build_summary(best: CandidateResultData, baseline: MetricsSummary) -> str:
    wait_delta = round(baseline.avg_wait - best.metrics.avg_wait, 2)
    queue_delta = baseline.peak_queue - best.metrics.peak_queue
    if wait_delta > 0 or queue_delta > 0:
        return (
            f"推荐采用“{best.strategy}”。相较基准方案，平均等待时间减少约 {wait_delta} 分钟，"
            f"峰值排队长度减少 {queue_delta} 人，主要改善瓶颈为 {best.metrics.bottleneck_type}。"
        )
    return f"推荐采用“{best.strategy}”。该方案在资源成本和等待指标之间综合评分最低。"
