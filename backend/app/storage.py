from __future__ import annotations

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
class SimulationStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save_result(self, result: SimulationResult) -> None:
        # 完整仿真结束后落库：先清理同 run_id 旧记录，再写配置、StepRecord 和 MetricsSummary。
        with self._connect() as conn:
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
                    seated_count, left_count, empty_seats, waiting_for_seat_count,
                    total_arrived, total_served, total_seated, total_left,
                    avg_wait_so_far, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_record_row(record) for record in result.records],
            )
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
                            "avg_party_gather_wait": result.metrics.avg_party_gather_wait,
                            "party_split_count": result.metrics.party_split_count,
                            "shared_table_count": result.metrics.shared_table_count,
                            "blocked_party_count": result.metrics.blocked_party_count,
                            "fragmented_seats": result.metrics.fragmented_seats,
                            "table_utilization_by_type": result.metrics.table_utilization_by_type,
                        }
                    ),
                ),
            )

    def save_optimization(self, opt_id: str, base_run_id: str | None, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
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

    def save_explanation(self, exp_id: str, run_id: str | None, request: dict[str, Any], response: dict[str, Any]) -> None:
        with self._connect() as conn:
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

    def get_metrics(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM metrics_summary WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["chart_data"] = json.loads(data.pop("chart_data_json"))
        data.update(json.loads(data.pop("extra_metrics_json", "{}") or "{}"))
        return data

    def export_records_csv(self, run_id: str, output_path: str | Path) -> Path:
        # CSV 导出只包含每分钟过程字段，便于检查后用表格复核仿真过程。
        records = self.get_records(run_id)
        if not records:
            raise KeyError(f"run_id 不存在或没有过程记录: {run_id}")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "run_id",
            "t",
            "arrived_count",
            "queue_lengths",
            "served_count",
            "seated_count",
            "left_count",
            "empty_seats",
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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


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
        record.waiting_for_seat_count,
        record.total_arrived,
        record.total_served,
        record.total_seated,
        record.total_left,
        record.avg_wait_so_far,
        _json(record.snapshot),
    )


def _record_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["queue_lengths"] = json.loads(data.pop("queue_lengths_json"))
    data["snapshot"] = json.loads(data.pop("snapshot_json"))
    return data


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
