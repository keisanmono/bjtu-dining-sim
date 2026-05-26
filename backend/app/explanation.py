from __future__ import annotations

# 文件说明：规则化解释模块：把推荐指标和瓶颈判断转换成检查时可读的说明文字。

from typing import Any


# 本文件只做本地规则化解释：根据瓶颈、基准指标和推荐指标拼接说明文本，
# 不调用外部大模型，核心仿真和推荐逻辑也不依赖 LLM。
# 生成推荐说明正文，并在调用方未提供风险说明时补默认风险提示。
def build_rule_based_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    # payload 来自解释接口，允许前端只传部分字段，所以这里全部使用默认值兜底。
    baseline_metrics = payload.get("baseline_metrics") or {}
    best_metrics = payload.get("best_metrics") or {}
    strategy = payload.get("recommended_strategy") or "当前推荐方案"
    root_cause = payload.get("root_cause_summary") or _infer_root_cause(baseline_metrics)
    risk_notes = list(payload.get("risk_notes") or [])

    # 正数表示推荐方案比基准更低，便于讲解“下降了多少”。
    wait_delta = _metric_delta(baseline_metrics, best_metrics, "avg_wait")
    queue_delta = _metric_delta(baseline_metrics, best_metrics, "peak_queue")
    if not risk_notes:
        # 前端没有传风险说明时，后端补充课程检查中最常见的两类约束。
        risk_notes = [
            "若学生到达分布与设定参数偏差较大，推荐结果需要重新仿真校准。",
            "窗口和座位扩容会带来人力或空间成本，课程演示中应结合资源约束解释。",
        ]

    text = (
        f"瓶颈判断：{root_cause}。建议采用“{strategy}”。"
        f"与基准方案相比，平均等待时间变化约 {wait_delta} 分钟，峰值排队长度变化 {queue_delta} 人。"
        "该推荐优先降低高峰排队和入座等待，同时保留错峰策略作为低成本备选。"
    )
    return {"text": text, "risk_notes": risk_notes}


# 从指标字段推断瓶颈原因，优先使用后端已给出的 bottleneck_type。
def _infer_root_cause(metrics: dict[str, Any]) -> str:
    bottleneck = metrics.get("bottleneck_type")
    if bottleneck:
        # 仿真指标已经判断出瓶颈时直接复用，避免解释层重新定义判断口径。
        return str(bottleneck)
    if metrics.get("peak_waiting_for_seat", 0) > 0:
        return "座位容量不足"
    if metrics.get("peak_queue", 0) > 20:
        return "窗口服务能力不足"
    return "整体运行较均衡"


# 计算基准指标减推荐指标的差值，缺字段时返回 0 便于解释接口容错。
def _metric_delta(base: dict[str, Any], best: dict[str, Any], key: str) -> float:
    if key not in base or key not in best:
        # 解释接口应尽量返回可读结果，缺少某项指标时用 0 表示无法比较。
        return 0.0
    return round(float(base[key]) - float(best[key]), 2)
