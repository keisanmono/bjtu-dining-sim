from __future__ import annotations

# 文件说明：FastAPI 接口模块：串联前端请求、仿真器、推荐模块和 SQLite 存储。

import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .campus import campus_locations as build_campus_locations
from .campus import campus_occupancy as build_campus_occupancy
from .explanation import build_rule_based_explanation
from .optimization import RecommendationRequestData, recommend_config
from .schemas import (
    CampusOccupancyRequest,
    ExplanationRequest,
    ExplanationResponse,
    RecommendationRequest,
    RunResponse,
    SimulationConfig,
    StepRequest,
    StepResponse,
    ValidationResponse,
)
from .simulation import DiningSimulationRunner, dataclass_to_dict, run_simulation, validate_config
from .storage import SimulationStore


# FastAPI 应用入口会用 DATA_DIR 保存 SQLite 和导出文件；相对路径按仓库根目录解析。
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_dir(value: str | None = None) -> Path:
    raw = value if value is not None else os.getenv("DATA_DIR", "data")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


DATA_DIR = _resolve_data_dir()
# STORE 是全局持久化对象，负责保存完整仿真结果、推荐结果、解释结果和 CSV 导出。
STORE = SimulationStore(DATA_DIR / "dining_sim.sqlite")
# ACTIVE_RUNS 保存实时仿真的 runner。/api/sim/step 多次请求靠 run_id 找回同一份状态。
ACTIVE_RUNS: dict[str, DiningSimulationRunner] = {}
ACTIVE_RUN_TTL_SECONDS = int(os.getenv("ACTIVE_RUN_TTL_SECONDS", "1800"))


app = FastAPI(title="北京交通大学就餐仿真系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # 允许 Vite 开发服务访问后端；生产环境可按部署地址收紧。
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 连通性验证：前端右上角状态标签只关心后端是否可连接。
@app.get("/api/health")
# health() 返回后端连通状态。
def health() -> dict[str, str]:
    return {"group": "20 组", "status": "ok", "message": "backend ready"}


# 参数校验：Pydantic 先保证字段范围，simulation.validate_config 再给业务错误和警告。
@app.post("/api/config/validate", response_model=ValidationResponse)
# validate_simulation_config() 校验输入参数并返回错误或提示。
def validate_simulation_config(config: SimulationConfig) -> ValidationResponse:
    errors, warnings = validate_config(config.to_data())
    return ValidationResponse(valid=not errors, errors=errors, warnings=warnings)


@app.get("/api/campus/locations")
# 返回校园位置基础数据，前端用来生成食堂和教学楼选择项。
def campus_locations() -> dict[str, Any]:
    return build_campus_locations()


@app.post("/api/campus/occupancy")
# 根据前端选择的人数来源返回楼层人数，失败时由 campus 模块负责降级。
def campus_occupancy(request: CampusOccupancyRequest) -> dict[str, Any]:
    try:
        buildings = request.buildings or None
        return build_campus_occupancy(request.source_mode, building_ids=buildings, seed=request.seed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# 完整仿真：一次运行到结束，保存所有 StepRecord 和最终 MetricsSummary。
@app.post("/api/sim/run", response_model=RunResponse)
# 接收完整配置并一次性跑完整个仿真，适合“快速完成”按钮。
def run_full_simulation(config: SimulationConfig) -> RunResponse:
    result = run_simulation(config.to_data())
    STORE.save_result(result)
    return _run_response(result)


# 实时单步仿真：先通过 _resolve_runner 找到当前 runner，再推进一分钟。
@app.post("/api/sim/step", response_model=StepResponse)
# 接收单步请求，找到当前仿真器后推进一分钟并返回状态快照。
def step_simulation(request: StepRequest) -> StepResponse:
    runner = _resolve_runner(request)
    record = runner.step()
    metrics = None
    if runner.done:
        # 仿真结束后才汇总指标并落库，前端收到 metrics 后切到结果分析页。
        result = runner.result()
        STORE.save_result(result)
        # 结束的实时 runner 从内存表移除，避免后续误复用已完成状态。
        ACTIVE_RUNS.pop(runner.run_id, None)
        metrics = asdict(result.metrics)
    return StepResponse(
        run_id=runner.run_id,
        done=runner.done,
        record=asdict(record),
        state=record.snapshot,
        metrics=metrics,
    )


@app.get("/api/run/{run_id}/records")
# 从 SQLite 读取指定 run_id 的分钟记录，供导出或回看使用。
def get_run_records(run_id: str) -> list[dict[str, Any]]:
    records = STORE.get_records(run_id)
    if not records:
        raise HTTPException(status_code=404, detail="未找到该运行的过程记录。")
    return records


@app.get("/api/run/{run_id}/metrics")
# 从 SQLite 读取指定 run_id 的最终指标汇总。
def get_run_metrics(run_id: str) -> dict[str, Any]:
    metrics = STORE.get_metrics(run_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="未找到该运行的指标汇总。")
    return metrics


# 优化推荐：后端枚举候选方案并评分，前端只负责传基准配置和候选范围。
@app.post("/api/optimize/recommend")
# 接收基准配置和候选范围，调用推荐模块返回排序后的优化方案。
def recommend(request: RecommendationRequest) -> dict[str, Any]:
    # FastAPI/Pydantic 模型先转成 simulation/optimization 使用的 dataclass。
    data = RecommendationRequestData(
        base_config=request.base_config.to_data(),
        window_options=request.window_options,
        seat_options=request.seat_options,
        stagger_options=request.stagger_options,
        peak_count_options=request.peak_count_options,
        top_k=request.top_k,
    )
    result = recommend_config(data)
    payload = dataclass_to_dict(result)
    opt_id = uuid.uuid4().hex
    # 推荐结果也保存一份，便于展示“推荐方案可以追溯”。
    STORE.save_optimization(
        opt_id=opt_id,
        base_run_id=None,
        payload={
            "candidates": [asdict(item.config) for item in result.ranking],
            "best_config": asdict(result.best.config),
            "ranking": payload["ranking"],
        },
    )
    payload["opt_id"] = opt_id
    return payload


# 规则化解释：不调用外部大模型，只根据指标、瓶颈和推荐策略生成说明文本。
@app.post("/api/explain", response_model=ExplanationResponse)
# 保存并返回本地规则化解释文本，供结果分析页展示。
def explain(request: ExplanationRequest) -> ExplanationResponse:
    exp_id = uuid.uuid4().hex
    response = build_rule_based_explanation(request.model_dump())
    STORE.save_explanation(exp_id, request.run_id, request.model_dump(), response)
    return ExplanationResponse(exp_id=exp_id, **response)


# CSV 导出：把已保存的每分钟 StepRecord 写成文件并返回给浏览器下载。
@app.get("/api/export/{run_id}")
# 触发 storage 导出 CSV，并用 FileResponse 返回给浏览器下载。
def export_records(run_id: str) -> FileResponse:
    output = DATA_DIR / "exports" / f"{run_id}_records.csv"
    try:
        STORE.export_records_csv(run_id, output)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=output, filename=output.name, media_type="text/csv")


# 根据 reset/run_id/config 决定新建 runner、复用 runner，或恢复丢失的实时运行。
def _resolve_runner(request: StepRequest) -> DiningSimulationRunner:
    now = time.monotonic()
    _prune_inactive_runs(now)
    # 首次单步或重置运行必须带 config，用它创建新的 DiningSimulationRunner。
    if request.reset or request.run_id is None:
        if request.config is None:
            raise HTTPException(status_code=422, detail="首次单步运行需要提供 config。")
        runner = DiningSimulationRunner(request.config.to_data())
        # ACTIVE_RUNS 是实时仿真的内存运行表，run_id 是前端后续 step 的定位依据。
        ACTIVE_RUNS[runner.run_id] = runner
        return _touch_runner(runner, now)

    runner = ACTIVE_RUNS.get(request.run_id)
    if runner is None:
        # 如果内存中的实时运行已结束/丢失，允许前端带 config 用同一 run_id 重新建立。
        if request.config is None:
            raise HTTPException(status_code=404, detail="运行已结束或不存在，请重新提供 config 开始单步运行。")
        runner = DiningSimulationRunner(request.config.to_data(), run_id=request.run_id)
        ACTIVE_RUNS[runner.run_id] = runner
    return _touch_runner(runner, now)


def _touch_runner(runner: DiningSimulationRunner, now: float | None = None) -> DiningSimulationRunner:
    runner.last_access_monotonic = time.monotonic() if now is None else now
    return runner


def _prune_inactive_runs(now: float | None = None) -> None:
    if ACTIVE_RUN_TTL_SECONDS <= 0:
        return
    current = time.monotonic() if now is None else now
    expired = [
        run_id
        for run_id, runner in ACTIVE_RUNS.items()
        if current - float(getattr(runner, "last_access_monotonic", current)) > ACTIVE_RUN_TTL_SECONDS
    ]
    for run_id in expired:
        ACTIVE_RUNS.pop(run_id, None)


# 把内部 SimulationResult dataclass 转换成 FastAPI response_model 需要的字典结构。
def _run_response(result: Any) -> RunResponse:
    return RunResponse(
        run_id=result.run_id,
        config=asdict(result.config),
        records=[asdict(record) for record in result.records],
        metrics=asdict(result.metrics),
        final_state=result.final_state,
    )
