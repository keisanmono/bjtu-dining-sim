from __future__ import annotations

from collections.abc import Iterable

from .agents import AgentState, PedestrianAgent
from .grid import Cell, GridData


def build_window_queue_cells(grid: GridData, window_index: int) -> list[Cell]:
    return list(grid.queue_cells_by_window.get(window_index, []))


def assign_agent_to_queue(agent: PedestrianAgent, window_index: int, queue_cells: list[Cell]) -> None:
    agent.desired_window_index = window_index
    agent.target_type = "window"
    agent.target_id = window_index
    agent.state = AgentState.TO_WINDOW if agent.cell not in set(queue_cells) else AgentState.QUEUEING
    if queue_cells:
        agent.target_cells = {queue_cells[-1]}


def update_queue_targets(agents: Iterable[PedestrianAgent], queues: dict[int, list[int]], grid: GridData) -> None:
    by_student = {agent.student_id: agent for agent in agents}
    for window_index, student_ids in queues.items():
        queue_cells = build_window_queue_cells(grid, window_index)
        if not queue_cells:
            continue
        for position, student_id in enumerate(student_ids):
            agent = by_student.get(student_id)
            if agent is None:
                continue
            target = queue_cells[min(position, len(queue_cells) - 1)]
            agent.desired_window_index = window_index
            agent.target_type = "window_queue"
            agent.target_id = window_index
            agent.target_cells = {target}
            if agent.cell == target:
                agent.state = AgentState.QUEUEING
