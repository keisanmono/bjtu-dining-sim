from __future__ import annotations

# 文件说明：FastAPI 接口模块：串联前端请求、仿真器、推荐模块和 SQLite 存储。

import os
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


# FastAPI 应用入口会用 DATA_DIR 保存 SQLite 和导出文件；课程检查时从这里讲接口总览。
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
# STORE 是全局持久化对象，负责保存完整仿真结果、推荐结果、解释结果和 CSV 导出。
STORE = SimulationStore(DATA_DIR / "dining_sim.sqlite")
# ACTIVE_RUNS 保存实时仿真的 runner。/api/sim/step 多次请求靠 run_id 找回同一份状态。
ACTIVE_RUNS: dict[str, DiningSimulationRunner] = {}


app = FastAPI(title="北京交通大学就餐仿真系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # 允许 Vite 开发服务访问后端；生产环境可按部署地址收紧。
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查：前端右上角状态标签只关心后端是否可连接。
@app.get("/api/health")
# 讲解注释：health() 返回后端连通状态。
def health() -> dict[str, str]:
    return {"group": "20 组", "status": "ok", "message": "backend ready"}


# 参数校验：Pydantic 先保证字段范围，simulation.validate_config 再给业务错误和警告。
@app.post("/api/config/validate", response_model=ValidationResponse)
# 讲解注释：validate_simulation_config() 校验输入参数并返回错误或提示。
def validate_simulation_config(config: SimulationConfig) -> ValidationResponse:
    errors, warnings = validate_config(config.to_data())
    return ValidationResponse(valid=not errors, errors=errors, warnings=warnings)


@app.get("/api/campus/locations")
# 讲解注释：campus_locations() 处理校园教学楼、食堂或到达数据。
def campus_locations() -> dict[str, Any]:
    return build_campus_locations()


@app.post("/api/campus/occupancy")
# 讲解注释：campus_occupancy() 处理校园教学楼、食堂或到达数据。
def campus_occupancy(request: CampusOccupancyRequest) -> dict[str, Any]:
    try:
        buildings = request.buildings or None
        return build_campus_occupancy(request.source_mode, building_ids=buildings, seed=request.seed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# 完整仿真：一次运行到结束，保存所有 StepRecord 和最终 MetricsSummary。
@app.post("/api/sim/run", response_model=RunResponse)
# 讲解注释：run_full_simulation() 封装本文件中的一个独立处理步骤。
def run_full_simulation(config: SimulationConfig) -> RunResponse:
    result = run_simulation(config.to_data())
    STORE.save_result(result)
    return _run_response(result)


# 实时单步仿真：先通过 _resolve_runner 找到当前 runner，再推进一分钟。
@app.post("/api/sim/step", response_model=StepResponse)
# 讲解注释：step_simulation() 封装本文件中的一个独立处理步骤。
def step_simulation(request: StepRequest) -> StepResponse:
    runner = _resolve_runner(request)
    record = runner.step()
    metrics = None
    if runner.done:
        # 仿真结束后才汇总指标并落库，前端收到 metrics 后切到结果分析页。
        result = runner.result()
        STORE.save_result(result)
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
# 讲解注释：get_run_records() 读写或展示分钟级过程记录。
def get_run_records(run_id: str) -> list[dict[str, Any]]:
    records = STORE.get_records(run_id)
    if not records:
        raise HTTPException(status_code=404, detail="未找到该运行的过程记录。")
    return records


@app.get("/api/run/{run_id}/metrics")
# 讲解注释：get_run_metrics() 读取或计算指标汇总。
def get_run_metrics(run_id: str) -> dict[str, Any]:
    metrics = STORE.get_metrics(run_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="未找到该运行的指标汇总。")
    return metrics


# 优化推荐：后端枚举候选方案并评分，前端只负责传基准配置和候选范围。
@app.post("/api/optimize/recommend")
# 讲解注释：recommend() 处理优化推荐相关流程。
def recommend(request: RecommendationRequest) -> dict[str, Any]:
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
# 讲解注释：explain() 处理规则化解释相关流程。
def explain(request: ExplanationRequest) -> ExplanationResponse:
    exp_id = uuid.uuid4().hex
    response = build_rule_based_explanation(request.model_dump())
    STORE.save_explanation(exp_id, request.run_id, request.model_dump(), response)
    return ExplanationResponse(exp_id=exp_id, **response)


# CSV 导出：把已保存的每分钟 StepRecord 写成文件并返回给浏览器下载。
@app.get("/api/export/{run_id}")
# 讲解注释：export_records() 读写或展示分钟级过程记录。
def export_records(run_id: str) -> FileResponse:
    output = DATA_DIR / "exports" / f"{run_id}_records.csv"
    try:
        STORE.export_records_csv(run_id, output)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=output, filename=output.name, media_type="text/csv")


# 讲解注释：_resolve_runner() 封装本文件中的一个独立处理步骤。
def _resolve_runner(request: StepRequest) -> DiningSimulationRunner:
    # 首次单步或重置运行必须带 config，用它创建新的 DiningSimulationRunner。
    if request.reset or request.run_id is None:
        if request.config is None:
            raise HTTPException(status_code=422, detail="首次单步运行需要提供 config。")
        runner = DiningSimulationRunner(request.config.to_data())
        ACTIVE_RUNS[runner.run_id] = runner
        return runner

    runner = ACTIVE_RUNS.get(request.run_id)
    if runner is None:
        # 如果内存中的实时运行已结束/丢失，允许前端带 config 用同一 run_id 重新建立。
        if request.config is None:
            raise HTTPException(status_code=404, detail="运行已结束或不存在，请重新提供 config 开始单步运行。")
        runner = DiningSimulationRunner(request.config.to_data(), run_id=request.run_id)
        ACTIVE_RUNS[runner.run_id] = runner
    return runner


# 讲解注释：_run_response() 封装本文件中的一个独立处理步骤。
def _run_response(result: Any) -> RunResponse:
    return RunResponse(
        run_id=result.run_id,
        config=asdict(result.config),
        records=[asdict(record) for record in result.records],
        metrics=asdict(result.metrics),
        final_state=result.final_state,
    )
