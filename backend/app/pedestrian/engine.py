from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .agents import AgentState, PartyMovementState, PedestrianAgent
from .fields import DensityField, DynamicField, build_static_field, wall_distance_or_penalty
from .grid import Cell, GridData, cell_to_point, grid_from_layout, is_walkable, neighbors
from .metrics import density_hotspots, movement_metrics
from .queueing import build_window_queue_cells, update_queue_targets


class PedestrianEngine:
    def __init__(self, layout: Any, config: Any, rng: Any):
        self.layout = layout
        self.config = config
        self.rng = rng
        self.grid: GridData = grid_from_layout(
            layout,
            cell_size=float(getattr(config, "floor_cell_size", 12.0)),
            allow_diagonal=bool(getattr(config, "floor_allow_diagonal", False)),
        )
        self.dynamic_field = DynamicField(
            decay=float(getattr(config, "dynamic_field_decay", 0.85)),
            diffusion=float(getattr(config, "dynamic_field_diffusion", 0.10)),
        )
        self.agents: dict[int, PedestrianAgent] = {}
        self.party_states: dict[int, PartyMovementState] = {}
        self.window_queues: dict[int, list[int]] = defaultdict(list)
        self.static_fields: dict[tuple[Cell, ...], dict[Cell, float]] = {}
        self.max_density = 0
        self.tick_seconds = max(1, int(getattr(config, "movement_tick_seconds", 5)))

    def spawn_arrivals(self, students: list[Any], door_index: int = 0) -> None:
        for student in students:
            resolved_door_index = min(
                max(0, int(getattr(student, "door_index", door_index) or door_index)),
                max(0, len(self.grid.door_cells) - 1),
            )
            cell = self.grid.door_cells.get(resolved_door_index) or next(iter(self.grid.door_cells.values()), (0, 0))
            agent = PedestrianAgent(
                agent_id=int(getattr(student, "student_id")),
                student_id=int(getattr(student, "student_id")),
                party_id=int(getattr(student, "party_id")),
                state=AgentState.ENTERING,
                cell=cell,
                previous_cell=None,
                path_cells=[cell],
            )
            self.agents[agent.student_id] = agent
            party_state = self.party_states.setdefault(
                agent.party_id,
                PartyMovementState(party_id=agent.party_id),
            )
            if agent.student_id not in party_state.member_agent_ids:
                party_state.member_agent_ids.append(agent.student_id)
        self._refresh_party_centers()

    def set_agent_target_window(self, student_id: int, window_index: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        window_index = max(0, int(window_index))
        for queue in self.window_queues.values():
            if student_id in queue:
                queue.remove(student_id)
        self.window_queues[window_index].append(student_id)
        agent.desired_window_index = window_index
        agent.target_type = "window_queue"
        agent.target_id = window_index
        agent.state = AgentState.TO_WINDOW
        self._update_queue_targets()

    def set_party_target_table(self, party: Any, table_index: int) -> None:
        student_ids = self._student_ids_for_party(party)
        targets = set(self.grid.table_approach_cells.get(table_index, set()))
        if not targets and table_index in self.grid.table_cells:
            targets = {
                neighbor
                for cell in self.grid.table_cells[table_index]
                for neighbor in neighbors(cell, self.grid, allow_diagonal=True)
                if is_walkable(neighbor, self.grid)
            }
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None:
                continue
            agent.state = AgentState.TO_TABLE
            agent.table_index = table_index
            agent.target_type = "table"
            agent.target_id = table_index
            agent.target_cells = set(targets)
        if student_ids:
            party_id = self.agents[student_ids[0]].party_id
            party_state = self.party_states.setdefault(party_id, PartyMovementState(party_id=party_id))
            party_state.reserved_table_index = table_index
            party_state.cohesion_enabled = True
        self._refresh_party_centers()

    def set_agent_service(self, student_id: int, window_index: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        service = self.grid.service_cells.get(window_index)
        if service is not None:
            agent.cell = service
            agent.path_cells.append(service)
            agent.target_cells = {service}
        agent.state = AgentState.SERVICE
        agent.target_type = "service"
        agent.target_id = window_index
        if student_id in self.window_queues.get(window_index, []):
            self.window_queues[window_index].remove(student_id)
        self._update_queue_targets()

    def set_agent_waiting_group(self, student_id: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None or agent.state is AgentState.EXITED:
            return
        agent.state = AgentState.WAITING_GROUP
        agent.target_type = "group"
        agent.target_id = agent.party_id

    def set_agent_seated(self, student_id: int, table_index: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        targets = sorted(self.grid.table_approach_cells.get(table_index, set()))
        if targets:
            agent.cell = targets[(student_id - 1) % len(targets)]
            agent.path_cells.append(agent.cell)
        agent.state = AgentState.SEATED
        agent.table_index = table_index
        agent.target_type = "table"
        agent.target_id = table_index

    def set_agent_exited(self, student_id: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        agent.state = AgentState.EXITED
        agent.target_type = "exit"
        agent.target_cells = set(self.grid.exit_cells)

    def tick(self, current_time_sec: int) -> list[dict[str, Any]]:
        self._update_queue_targets()
        self._refresh_party_centers()
        movable = [agent for agent in self.agents.values() if self._is_movable(agent)]
        occupied_all = {
            agent.cell
            for agent in self.agents.values()
            if agent.state is not AgentState.EXITED
        }
        intents: dict[Cell, list[tuple[PedestrianAgent, float]]] = defaultdict(list)
        intended_by_agent: dict[int, Cell] = {}
        for agent in sorted(movable, key=lambda item: item.student_id):
            occupied = set(occupied_all)
            occupied.discard(agent.cell)
            intended, cost = self._intended_move(agent, occupied_cells=occupied)
            intents[intended].append((agent, cost))
            intended_by_agent[agent.student_id] = intended

        events: list[dict[str, Any]] = []
        winners: dict[int, Cell] = {}
        conflict_losers: set[int] = set()
        for target, contenders in intents.items():
            if len(contenders) == 1:
                agent, _cost = contenders[0]
                winners[agent.student_id] = target
                continue
            ordered = sorted(contenders, key=lambda item: (item[1], self.rng.random(), item[0].student_id))
            winner, _winner_cost = ordered[0]
            winners[winner.student_id] = target
            for loser, _cost in ordered[1:]:
                conflict_losers.add(loser.student_id)
                loser.conflict_count += 1

        for agent in movable:
            previous = agent.cell
            target = previous if agent.student_id in conflict_losers else winners.get(agent.student_id, previous)
            if target != previous:
                agent.previous_cell = previous
                agent.cell = target
                agent.walking_distance_cells += 1
                agent.path_cells.append(target)
                frame = {"time_sec": current_time_sec, **cell_to_point(target, self.grid)}
                agent.frames.append(frame)
                events.append(self._movement_event(agent, previous, target, current_time_sec))
                agent.stuck_ticks = 0
            else:
                agent.wait_ticks += 1
                agent.stuck_ticks += 1
            if agent.target_cells and agent.cell in agent.target_cells and agent.state is AgentState.TO_WINDOW:
                agent.state = AgentState.QUEUEING

        for agent in self.agents.values():
            if agent.state is not AgentState.EXITED:
                self.dynamic_field.deposit(agent.cell)
        self.dynamic_field.step(self.grid)
        self._update_density_metric()
        self._refresh_party_centers()
        return events

    def run_for_minute(self, start_sec: int, end_sec: int) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        tick_seconds = max(1, int(getattr(self.config, "movement_tick_seconds", self.tick_seconds)))
        max_ticks = max(1, int(getattr(self.config, "max_movement_ticks_per_minute", 12)))
        tick_count = min(max_ticks, max(1, math.ceil((end_sec - start_sec) / tick_seconds)))
        for tick_index in range(tick_count):
            current = start_sec + tick_index * tick_seconds
            if current >= end_sec:
                break
            events.extend(self.tick(current))
        timeline = None
        if events:
            timeline = {
                "start_time_sec": start_sec,
                "end_time_sec": end_sec,
                "playback_ms": 720,
                "events": events,
            }
        return {
            "timeline": timeline,
            "metrics_delta": self.metrics_snapshot(),
        }

    def agent_snapshots(self) -> list[dict[str, Any]]:
        snapshots = []
        for agent in sorted(self.agents.values(), key=lambda item: item.student_id):
            if agent.state is AgentState.EXITED:
                continue
            point = cell_to_point(agent.cell, self.grid)
            snapshots.append({
                "agent_id": agent.agent_id,
                "student_id": agent.student_id,
                "party_id": agent.party_id,
                "state": agent.state.value,
                "cell": [agent.cell[0], agent.cell[1]],
                "x": point["x"],
                "y": point["y"],
                "target_type": agent.target_type,
                "target_id": agent.target_id,
                "desired_window_index": agent.desired_window_index,
                "table_index": agent.table_index,
                "stuck_ticks": agent.stuck_ticks,
                "conflict_count": agent.conflict_count,
                "walking_distance_cells": agent.walking_distance_cells,
            })
        return snapshots

    def density_hotspots(self) -> list[dict[str, float | int]]:
        occupied = [agent.cell for agent in self.agents.values() if agent.state is not AgentState.EXITED]
        counts = Counter(occupied)
        threshold = max(1, int(getattr(self.config, "congestion_density_threshold", 3)))
        hotspots = []
        for cell, count in counts.items():
            if count >= threshold:
                point = cell_to_point(cell, self.grid)
                hotspots.append({"cell": [cell[0], cell[1]], "x": point["x"], "y": point["y"], "density": count})
        if hotspots:
            return sorted(hotspots, key=lambda item: (-int(item["density"]), item["cell"][1], item["cell"][0]))
        local_density = DensityField.from_occupied_cells(set(occupied), self.grid, radius=1)
        dense_cells = {
            cell
            for cell, density in local_density.densities.items()
            if density >= threshold
        }
        return density_hotspots(dense_cells, self.grid, threshold=1)[:24]

    def metrics_snapshot(self) -> dict[str, float | int]:
        metrics = movement_metrics(self.agents, self.tick_seconds, self.max_density)
        return {
            "avg_walking_time": metrics.avg_walking_time,
            "movement_conflict_count": metrics.movement_conflict_count,
            "avg_stuck_ticks": metrics.avg_stuck_ticks,
            "max_density": metrics.max_density,
        }

    def _intended_move(self, agent: PedestrianAgent, occupied_cells: set[Cell]) -> tuple[Cell, float]:
        candidates = [agent.cell, *neighbors(agent.cell, self.grid, bool(getattr(self.config, "floor_allow_diagonal", False)))]
        candidates = [
            cell
            for cell in candidates
            if is_walkable(cell, self.grid) and (cell == agent.cell or cell not in occupied_cells)
        ]
        if not candidates or not agent.target_cells:
            return agent.cell, 0.0
        density = DensityField.from_occupied_cells(occupied_cells, self.grid, radius=int(getattr(self.config, "personal_space_radius_cells", 1)))
        scored = [
            (cell, self._candidate_cost(cell, agent, density))
            for cell in candidates
        ]
        finite = [(cell, cost) for cell, cost in scored if math.isfinite(cost)]
        if not finite:
            return agent.cell, float("inf")
        return min(finite, key=lambda item: (item[1], item[0][1], item[0][0]))

    def _candidate_cost(self, cell: Cell, agent: PedestrianAgent, density: DensityField) -> float:
        static_field = self._static_field(agent.target_cells)
        static_distance = static_field.get(cell, float("inf"))
        if not math.isfinite(static_distance):
            return float("inf")
        threshold = int(getattr(self.config, "congestion_density_threshold", 3))
        cost = float(getattr(self.config, "floor_static_weight", 1.0)) * static_distance
        cost += float(getattr(self.config, "floor_density_weight", 1.2)) * density.penalty(cell, threshold=threshold)
        cost -= float(getattr(self.config, "floor_dynamic_weight", 0.35)) * self.dynamic_field.values.get(cell, 0.0)
        cost += float(getattr(self.config, "floor_wall_weight", 0.6)) * wall_distance_or_penalty(cell, self.grid)
        cost += float(getattr(self.config, "floor_inertia_weight", 0.25)) * self._turn_penalty(agent, cell)
        cost += float(getattr(self.config, "floor_group_weight", 0.8)) * self._group_distance_penalty(agent, cell)
        randomness = float(getattr(self.config, "floor_randomness", 0.05))
        if randomness > 0:
            cost += self.rng.random() * randomness
        return cost

    def _static_field(self, target_cells: set[Cell]) -> dict[Cell, float]:
        key = tuple(sorted(target_cells))
        if key not in self.static_fields:
            self.static_fields[key] = build_static_field(self.grid, set(key))
        return self.static_fields[key]

    def _turn_penalty(self, agent: PedestrianAgent, candidate: Cell) -> float:
        if candidate == agent.cell or agent.previous_cell is None:
            return 0.0
        incoming = (agent.cell[0] - agent.previous_cell[0], agent.cell[1] - agent.previous_cell[1])
        outgoing = (candidate[0] - agent.cell[0], candidate[1] - agent.cell[1])
        if incoming == outgoing:
            return 0.0
        if incoming == (-outgoing[0], -outgoing[1]):
            return 2.0
        return 1.0

    def _group_distance_penalty(self, agent: PedestrianAgent, candidate: Cell) -> float:
        party = self.party_states.get(agent.party_id)
        if party is None or not party.cohesion_enabled or len(party.member_agent_ids) < 2:
            return 0.0
        center = party.group_center
        if center is None:
            return 0.0
        distance = abs(candidate[0] - center[0]) + abs(candidate[1] - center[1])
        return max(0.0, distance - 2.0)

    def _refresh_party_centers(self) -> None:
        for party in self.party_states.values():
            members = [
                self.agents[student_id]
                for student_id in party.member_agent_ids
                if student_id in self.agents and self.agents[student_id].state is not AgentState.EXITED
            ]
            if not members:
                party.group_center = None
                continue
            party.group_center = (
                sum(agent.cell[0] for agent in members) / len(members),
                sum(agent.cell[1] for agent in members) / len(members),
            )

    def _update_queue_targets(self) -> None:
        update_queue_targets(self.agents.values(), self.window_queues, self.grid)
        for window_index, queue in list(self.window_queues.items()):
            queue_cells = build_window_queue_cells(self.grid, window_index)
            if not queue_cells:
                continue
            for position, student_id in enumerate(queue):
                agent = self.agents.get(student_id)
                if agent is None:
                    continue
                agent.target_cells = {queue_cells[min(position, len(queue_cells) - 1)]}

    def _update_density_metric(self) -> None:
        occupied = {
            agent.cell
            for agent in self.agents.values()
            if agent.state is not AgentState.EXITED
        }
        density = DensityField.from_occupied_cells(occupied, self.grid, radius=int(getattr(self.config, "personal_space_radius_cells", 1)))
        self.max_density = max(self.max_density, max(density.densities.values(), default=0))

    def _is_movable(self, agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _movement_event(self, agent: PedestrianAgent, start: Cell, end: Cell, current_time_sec: int) -> dict[str, Any]:
        start_point = cell_to_point(start, self.grid)
        end_point = cell_to_point(end, self.grid)
        return {
            "type": "pedestrian_move",
            "party_id": agent.party_id,
            "student_id": agent.student_id,
            "size": 1,
            "member_count": 1,
            "state": agent.state.value,
            "start_time_sec": current_time_sec,
            "arrive_time_sec": current_time_sec + self.tick_seconds,
            "duration_sec": self.tick_seconds,
            "playback_start_ms": 0,
            "playback_duration_ms": max(120, self.tick_seconds * 40),
            "playback_end_ms": max(120, self.tick_seconds * 40),
            "from": start_point,
            "to": end_point,
            "path": [start_point, end_point],
            "frames": [
                {"time_sec": current_time_sec, **start_point, "progress": 0.0},
                {"time_sec": current_time_sec + self.tick_seconds, **end_point, "progress": 1.0},
            ],
        }

    def _student_ids_for_party(self, party: Any) -> list[int]:
        if isinstance(party, list):
            return [int(getattr(student, "student_id", student)) for student in party]
        if hasattr(party, "student_ids"):
            return [int(student_id) for student_id in getattr(party, "student_ids")]
        if hasattr(party, "student_id"):
            return [int(getattr(party, "student_id"))]
        return []
