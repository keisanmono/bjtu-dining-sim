from __future__ import annotations

# 文件说明：本地存储模块：用 SQLite 保存仿真配置、过程记录、指标、推荐和解释。

import csv
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .simulation import SimulationResult


# SQLite 持久化层：保存配置、每分钟记录、最终指标、推荐结果和解释结果。
# SimulationStore 负责连接数据库、初始化表结构，以及读写仿真相关数据。
class SimulationStore:
    # 保存数据库路径，确保目录存在，并在首次使用时创建表结构。
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # save_result() 保存一次完整仿真的配置、过程记录和最终指标。
    def save_result(self, result: SimulationResult) -> None:
        # 完整仿真结束后落库：先清理同 run_id 旧记录，再写配置、StepRecord 和 MetricsSummary。
        with self._connect() as conn:
            # run_id 可能被重新运行覆盖，先删明细和指标可以避免旧分钟记录残留。
            conn.execute("DELETE FROM step_record WHERE run_id = ?", (result.run_id,))
            conn.execute("DELETE FROM metrics_summary WHERE run_id = ?", (result.run_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO run_config (run_id, created_at, config_json)
                VALUES (?, ?, ?)
                """,
                (result.run_id, _now_iso(), _json(asdict(result.config))),
            )
            conn.executemany(
                """
                INSERT INTO step_record (
                    run_id, t, arrived_count, queue_lengths_json, served_count,
                    seated_count, left_count, empty_seats, reserved_seats, available_seats,
                    waiting_for_seat_count, total_arrived, total_served, total_seated, total_left,
                    avg_wait_so_far, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_record_row(record) for record in result.records],
            )
            # 指标表保存常用字段；不常用于筛选的派生指标统一放入 extra_metrics_json。
            conn.execute(
                """
                INSERT OR REPLACE INTO metrics_summary (
                    run_id, avg_wait, avg_queue_wait, avg_seat_wait, peak_queue,
                    peak_waiting_for_seat, throughput, total_arrived, total_left,
                    seat_utilization, window_utilization, bottleneck_type, chart_data_json,
                    extra_metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.metrics.avg_wait,
                    result.metrics.avg_queue_wait,
                    result.metrics.avg_seat_wait,
                    result.metrics.peak_queue,
                    result.metrics.peak_waiting_for_seat,
                    result.metrics.throughput,
                    result.metrics.total_arrived,
                    result.metrics.total_left,
                    result.metrics.seat_utilization,
                    result.metrics.window_utilization,
                    result.metrics.bottleneck_type,
                    _json(result.metrics.chart_data),
                    _json(
                        {
                            "active_window_utilization": result.metrics.active_window_utilization,
                            "avg_party_gather_wait": result.metrics.avg_party_gather_wait,
                            "avg_party_seat_wait": result.metrics.avg_party_seat_wait,
                            "avg_post_service_to_seat_time": result.metrics.avg_post_service_to_seat_time,
                            "party_window_split_count": result.metrics.party_window_split_count,
                            "party_split_count": result.metrics.party_split_count,
                            "shared_table_count": result.metrics.shared_table_count,
                            "blocked_party_count": result.metrics.blocked_party_count,
                            "fragmented_seats": result.metrics.fragmented_seats,
                            "table_utilization_by_type": result.metrics.table_utilization_by_type,
                            "avg_walking_time": result.metrics.avg_walking_time,
                            "movement_conflict_count": result.metrics.movement_conflict_count,
                            "avg_stuck_ticks": result.metrics.avg_stuck_ticks,
                            "max_density": result.metrics.max_density,
                            "avg_walking_distance_ratio": result.metrics.avg_walking_distance_ratio,
                        }
                    ),
                ),
            )

    # 保存一次优化推荐结果，包括候选方案、最佳配置和排序明细。
    def save_optimization(self, opt_id: str, base_run_id: str | None, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            # 推荐结果按 opt_id 覆盖写入，便于重复请求时保持一条最新记录。
            conn.execute(
                """
                INSERT OR REPLACE INTO optimization_result (
                    opt_id, base_run_id, created_at, candidate_json, best_config_json, ranking_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    opt_id,
                    base_run_id,
                    _now_iso(),
                    _json(payload.get("candidates", [])),
                    _json(payload.get("best_config", {})),
                    _json(payload.get("ranking", [])),
                ),
            )

    # 保存规则化解释请求和响应，便于之后按 exp_id 或 run_id 追溯。
    def save_explanation(self, exp_id: str, run_id: str | None, request: dict[str, Any], response: dict[str, Any]) -> None:
        with self._connect() as conn:
            # request_json 保存原始解释上下文，response_text/risk_notes 保存可直接展示的结果。
            conn.execute(
                """
                INSERT OR REPLACE INTO explanation_result (
                    exp_id, run_id, request_json, response_text, risk_notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    exp_id,
                    run_id,
                    _json(request),
                    response.get("text", ""),
                    _json(response.get("risk_notes", [])),
                    _now_iso(),
                ),
            )

    # 按 run_id 读取所有分钟级过程记录，并恢复 JSON 字段。
    def get_records(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM step_record
                WHERE run_id = ?
                ORDER BY t
                """,
                (run_id,),
            ).fetchall()
        return [_record_dict(row) for row in rows]

    # 按 run_id 读取最终指标汇总，并合并额外指标 JSON。
    def get_metrics(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM metrics_summary WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        # JSON 字段在接口层恢复成普通 dict，调用方不需要了解数据库列名。
        data["chart_data"] = json.loads(data.pop("chart_data_json"))
        # extra_metrics_json 是兼容扩展字段，展开后与基础指标处于同一层。
        data.update(json.loads(data.pop("extra_metrics_json", "{}") or "{}"))
        return data

    # export_records_csv() 把已保存的分钟记录导出为 CSV 文件。
    def export_records_csv(self, run_id: str, output_path: str | Path) -> Path:
        # CSV 导出只包含每分钟过程字段，便于展示后用表格复核仿真过程。
        records = self.get_records(run_id)
        if not records:
            raise KeyError(f"run_id 不存在或没有过程记录: {run_id}")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        # CSV 只导出标量和队列长度摘要，完整前端快照仍保留在 SQLite 的 snapshot_json。
        fieldnames = [
            "run_id",
            "t",
            "arrived_count",
            "queue_lengths",
            "served_count",
            "seated_count",
            "left_count",
            "empty_seats",
            "reserved_seats",
            "available_seats",
            "waiting_for_seat_count",
            "total_arrived",
            "total_served",
            "total_seated",
            "total_left",
            "avg_wait_so_far",
        ]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow({key: record.get(key) for key in fieldnames})
        return output

    # 创建或补齐 SQLite 表结构，兼容已有数据库缺少 extra_metrics_json 的情况。
    def _init_db(self) -> None:
        with self._connect() as conn:
            # 表结构含义：
            # run_config 保存输入配置，step_record 保存分钟级过程，
            # metrics_summary 保存最终指标，optimization/explanation 保存推荐与解释结果。
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS run_config (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    config_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS step_record (
                    run_id TEXT NOT NULL,
                    t INTEGER NOT NULL,
                    arrived_count INTEGER NOT NULL,
                    queue_lengths_json TEXT NOT NULL,
                    served_count INTEGER NOT NULL,
                    seated_count INTEGER NOT NULL,
                    left_count INTEGER NOT NULL,
                    empty_seats INTEGER NOT NULL,
                    reserved_seats INTEGER NOT NULL DEFAULT 0,
                    available_seats INTEGER NOT NULL DEFAULT 0,
                    waiting_for_seat_count INTEGER NOT NULL,
                    total_arrived INTEGER NOT NULL,
                    total_served INTEGER NOT NULL,
                    total_seated INTEGER NOT NULL,
                    total_left INTEGER NOT NULL,
                    avg_wait_so_far REAL NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, t)
                );

                CREATE TABLE IF NOT EXISTS metrics_summary (
                    run_id TEXT PRIMARY KEY,
                    avg_wait REAL NOT NULL,
                    avg_queue_wait REAL NOT NULL,
                    avg_seat_wait REAL NOT NULL,
                    peak_queue INTEGER NOT NULL,
                    peak_waiting_for_seat INTEGER NOT NULL,
                    throughput INTEGER NOT NULL,
                    total_arrived INTEGER NOT NULL,
                    total_left INTEGER NOT NULL,
                    seat_utilization REAL NOT NULL,
                    window_utilization REAL NOT NULL,
                    bottleneck_type TEXT NOT NULL,
                    chart_data_json TEXT NOT NULL,
                    extra_metrics_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS optimization_result (
                    opt_id TEXT PRIMARY KEY,
                    base_run_id TEXT,
                    created_at TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    best_config_json TEXT NOT NULL,
                    ranking_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS explanation_result (
                    exp_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    request_json TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    risk_notes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            _ensure_column(conn, "metrics_summary", "extra_metrics_json", "TEXT NOT NULL DEFAULT '{}'")
            _ensure_column(conn, "step_record", "reserved_seats", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "step_record", "available_seats", "INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                UPDATE step_record
                SET available_seats = empty_seats
                WHERE reserved_seats = 0 AND available_seats = 0 AND empty_seats > 0
                """
            )

    @contextmanager
    # 提供自动 commit/close 的 SQLite 连接上下文。
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        # 使用 Row 后，读取时可以按列名取值，_record_dict/get_metrics 更清晰。
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            # 所有写入函数共用这个上下文，正常退出时统一提交事务。
            conn.commit()
        finally:
            conn.close()


# 把 StepRecord dataclass 压平成 step_record 表的一行。
def _record_row(record: Any) -> tuple[Any, ...]:
    return (
        record.run_id,
        record.t,
        record.arrived_count,
        _json(record.queue_lengths),
        record.served_count,
        record.seated_count,
        record.left_count,
        record.empty_seats,
        record.reserved_seats,
        record.available_seats,
        record.waiting_for_seat_count,
        record.total_arrived,
        record.total_served,
        record.total_seated,
        record.total_left,
        record.avg_wait_so_far,
        _json(record.snapshot),
    )


# 把数据库行恢复成前端接口使用的记录字典。
def _record_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    # 数据库保存紧凑 JSON，接口返回时恢复为前端可直接使用的对象。
    data["queue_lengths"] = json.loads(data.pop("queue_lengths_json"))
    data["snapshot"] = json.loads(data.pop("snapshot_json"))
    if "clock_minute" in data["snapshot"]:
        data["clock_minute"] = data["snapshot"]["clock_minute"]
    return data


# 用紧凑 JSON 保存嵌套配置、快照和指标，保留中文字符。
def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# 如果旧表缺少字段，则用 ALTER TABLE 做一次轻量迁移。
def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    # PRAGMA 读取当前列集合，避免对新数据库重复执行 ALTER TABLE。
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# 生成 UTC ISO 时间戳，供 run/optimization/explanation 记录创建时间。
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
