from __future__ import annotations

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


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
STORE = SimulationStore(DATA_DIR / "dining_sim.sqlite")
ACTIVE_RUNS: dict[str, DiningSimulationRunner] = {}


app = FastAPI(title="北京交通大学就餐仿真系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"group": "20 组", "status": "ok", "message": "backend ready"}


@app.post("/api/config/validate", response_model=ValidationResponse)
def validate_simulation_config(config: SimulationConfig) -> ValidationResponse:
    errors, warnings = validate_config(config.to_data())
    return ValidationResponse(valid=not errors, errors=errors, warnings=warnings)


@app.get("/api/campus/locations")
def campus_locations() -> dict[str, Any]:
    return build_campus_locations()


@app.post("/api/campus/occupancy")
def campus_occupancy(request: CampusOccupancyRequest) -> dict[str, Any]:
    try:
        buildings = request.buildings or None
        return build_campus_occupancy(request.source_mode, building_ids=buildings, seed=request.seed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sim/run", response_model=RunResponse)
def run_full_simulation(config: SimulationConfig) -> RunResponse:
    result = run_simulation(config.to_data())
    STORE.save_result(result)
    return _run_response(result)


@app.post("/api/sim/step", response_model=StepResponse)
def step_simulation(request: StepRequest) -> StepResponse:
    runner = _resolve_runner(request)
    record = runner.step()
    metrics = None
    if runner.done:
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
def get_run_records(run_id: str) -> list[dict[str, Any]]:
    records = STORE.get_records(run_id)
    if not records:
        raise HTTPException(status_code=404, detail="未找到该运行的过程记录。")
    return records


@app.get("/api/run/{run_id}/metrics")
def get_run_metrics(run_id: str) -> dict[str, Any]:
    metrics = STORE.get_metrics(run_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="未找到该运行的指标汇总。")
    return metrics


@app.post("/api/optimize/recommend")
def recommend(request: RecommendationRequest) -> dict[str, Any]:
    data = RecommendationRequestData(
        base_config=request.base_config.to_data(),
        window_options=request.window_options,
        seat_options=request.seat_options,
        stagger_options=request.stagger_options,
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


@app.post("/api/explain", response_model=ExplanationResponse)
def explain(request: ExplanationRequest) -> ExplanationResponse:
    exp_id = uuid.uuid4().hex
    response = build_rule_based_explanation(request.model_dump())
    STORE.save_explanation(exp_id, request.run_id, request.model_dump(), response)
    return ExplanationResponse(exp_id=exp_id, **response)


@app.get("/api/export/{run_id}")
def export_records(run_id: str) -> FileResponse:
    output = DATA_DIR / "exports" / f"{run_id}_records.csv"
    try:
        STORE.export_records_csv(run_id, output)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=output, filename=output.name, media_type="text/csv")


def _resolve_runner(request: StepRequest) -> DiningSimulationRunner:
    if request.reset or request.run_id is None:
        if request.config is None:
            raise HTTPException(status_code=422, detail="首次单步运行需要提供 config。")
        runner = DiningSimulationRunner(request.config.to_data())
        ACTIVE_RUNS[runner.run_id] = runner
        return runner

    runner = ACTIVE_RUNS.get(request.run_id)
    if runner is None:
        if request.config is None:
            raise HTTPException(status_code=404, detail="运行已结束或不存在，请重新提供 config 开始单步运行。")
        runner = DiningSimulationRunner(request.config.to_data(), run_id=request.run_id)
        ACTIVE_RUNS[runner.run_id] = runner
    return runner


def _run_response(result: Any) -> RunResponse:
    return RunResponse(
        run_id=result.run_id,
        config=asdict(result.config),
        records=[asdict(record) for record in result.records],
        metrics=asdict(result.metrics),
        final_state=result.final_state,
    )
