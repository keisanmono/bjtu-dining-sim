from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .grid import Cell


class AgentState(str, Enum):
    ENTERING = "ENTERING"
    TO_WINDOW = "TO_WINDOW"
    QUEUEING = "QUEUEING"
    SERVICE = "SERVICE"
    WAITING_GROUP = "WAITING_GROUP"
    TO_TABLE = "TO_TABLE"
    SEATED = "SEATED"
    TO_EXIT = "TO_EXIT"
    EXITED = "EXITED"


@dataclass
class PedestrianAgent:
    agent_id: int
    student_id: int
    party_id: int
    state: AgentState
    cell: Cell
    target_type: str | None = None
    target_id: int | None = None
    target_cells: set[Cell] = field(default_factory=set)
    previous_cell: Cell | None = None
    desired_window_index: int | None = None
    assigned_queue_slot_index: int | None = None
    table_index: int | None = None
    assigned_table_approach_cell: Cell | None = None
    table_repair_failures: int = 0
    table_slot_reassignments: int = 0
    stuck_ticks: int = 0
    walking_distance_cells: int = 0
    walking_time_seconds: float = 0.0
    conflict_count: int = 0
    wait_ticks: int = 0
    path_cells: list[Cell] = field(default_factory=list)
    frames: list[dict[str, float | int]] = field(default_factory=list)


@dataclass
class PartyMovementState:
    party_id: int
    member_agent_ids: list[int] = field(default_factory=list)
    group_center: tuple[float, float] | None = None
    reserved_table_index: int | None = None
    gathering_cell: Cell | None = None
    cohesion_enabled: bool = True
