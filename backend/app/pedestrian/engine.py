from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from typing import Any, Callable

from .agents import AgentState, PartyMovementState, PedestrianAgent
from .fields import DensityField, DynamicField, build_static_field, wall_distance_or_penalty
from .grid import Cell, GridData, cell_to_point, grid_from_layout, is_walkable, neighbors
from .metrics import density_hotspots as build_density_hotspots
from .metrics import movement_metrics
from .queueing import build_window_queue_cells


DES_WALKING_SPEED_UNITS_PER_SEC = 38.0


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
        self.entry_spawn_cells: dict[int, list[Cell]] = {}
        self.max_density = 0
        self.tick_seconds = max(1, int(getattr(config, "movement_tick_seconds", 5)))
        speed = float(getattr(config, "walking_speed_units_per_sec", DES_WALKING_SPEED_UNITS_PER_SEC))
        self.walking_speed_units_per_sec = speed if math.isfinite(speed) and speed > 0 else DES_WALKING_SPEED_UNITS_PER_SEC

    def spawn_arrivals(self, students: list[Any], door_index: int = 0) -> None:
        occupied_cells = {
            agent.cell
            for agent in self.agents.values()
            if self._occupies_walkable_cell(agent)
        }
        for student in students:
            resolved_door_index = min(
                max(0, int(getattr(student, "door_index", door_index) or door_index)),
                max(0, len(self.grid.door_cells) - 1),
            )
            cell = self._next_entry_spawn_cell(resolved_door_index, occupied_cells)
            occupied_cells.add(cell)
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

    def _next_entry_spawn_cell(self, door_index: int, occupied_cells: set[Cell]) -> Cell:
        candidates = self._entry_spawn_candidates(door_index)
        for cell in candidates:
            if cell not in occupied_cells:
                return cell
        return candidates[0] if candidates else (0, 0)

    def available_entry_cells(self, door_index: int, limit: int | None = None) -> list[Cell]:
        occupied_cells = {
            agent.cell
            for agent in self.agents.values()
            if self._occupies_walkable_cell(agent)
        }
        cells = [cell for cell in self._entry_spawn_candidates(door_index) if cell not in occupied_cells]
        if limit is None:
            return cells
        return cells[: max(0, int(limit))]

    def _entry_spawn_candidates(self, door_index: int) -> list[Cell]:
        if door_index in self.entry_spawn_cells:
            return self.entry_spawn_cells[door_index]
        start = self.grid.door_cells.get(door_index) or next(iter(self.grid.door_cells.values()), (0, 0))
        max_radius = max(1, int(getattr(self.config, "entry_spawn_radius_cells", 3)))
        frontier: deque[tuple[Cell, int]] = deque([(start, 0)])
        seen = {start}
        candidates: list[Cell] = []
        while frontier:
            current, distance = frontier.popleft()
            if is_walkable(current, self.grid):
                candidates.append(current)
            if distance >= max_radius:
                continue
            for neighbor in neighbors(current, self.grid, allow_diagonal=True):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                frontier.append((neighbor, distance + 1))
        self.entry_spawn_cells[door_index] = candidates or [start]
        return self.entry_spawn_cells[door_index]

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
        agent.target_cells = {agent.cell}

    def set_agent_seated(self, student_id: int, table_index: int, preserve_cell: bool = False) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        targets = sorted(self.grid.table_approach_cells.get(table_index, set()))
        if targets and not preserve_cell:
            agent.cell = targets[(student_id - 1) % len(targets)]
            agent.path_cells.append(agent.cell)
        agent.state = AgentState.SEATED
        agent.table_index = table_index
        agent.target_type = "table"
        agent.target_id = table_index
        agent.target_cells = set()

    def set_agent_exited(self, student_id: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        agent.target_type = "exit"
        agent.target_cells = set(self.grid.exit_cells)
        if not agent.path_cells:
            agent.path_cells.append(agent.cell)
        if not agent.target_cells or agent.cell in agent.target_cells:
            agent.state = AgentState.EXITED
            return
        agent.state = AgentState.TO_EXIT

    def tick(self, current_time_sec: int) -> list[dict[str, Any]]:
        self._update_queue_targets()
        self._refresh_party_centers()
        budget = self._movement_budget_cells_per_tick()
        step_duration = self.tick_seconds / budget
        events: list[dict[str, Any]] = []
        moved_agent_ids: set[int] = set()
        active_agent_ids: set[int] = set()
        for step_index in range(budget):
            step_time = current_time_sec + step_index * step_duration
            step_events, step_moved_ids, step_active_ids = self._movement_micro_step(step_time, step_duration)
            events.extend(step_events)
            moved_agent_ids.update(step_moved_ids)
            active_agent_ids.update(step_active_ids)

        for student_id in active_agent_ids:
            agent = self.agents.get(student_id)
            if agent is None or not self._is_movable(agent):
                continue
            if student_id in moved_agent_ids:
                agent.stuck_ticks = 0
                continue
            agent.wait_ticks += 1
            agent.stuck_ticks += 1

        for student_id in moved_agent_ids:
            agent = self.agents.get(student_id)
            if agent is not None and self._occupies_walkable_cell(agent):
                self.dynamic_field.deposit(agent.cell)
        self.dynamic_field.step(self.grid)
        self._update_density_metric()
        self._refresh_party_centers()
        return events

    def _movement_budget_cells_per_tick(self) -> int:
        cells = self.walking_speed_units_per_sec * self.tick_seconds / max(self.grid.cell_size, 1e-9)
        return max(1, int(round(cells)))

    def _movement_micro_step(
        self,
        current_time_sec: float,
        duration_sec: float,
    ) -> tuple[list[dict[str, Any]], set[int], set[int]]:
        movable = [agent for agent in self.agents.values() if self._is_movable(agent)]
        active_ids = {agent.student_id for agent in movable}
        occupied_by = {
            agent.cell: agent
            for agent in self.agents.values()
            if self._occupies_walkable_cell(agent)
        }
        occupied_all = set(occupied_by)
        density_radius = int(getattr(self.config, "personal_space_radius_cells", 1))
        movement_density = DensityField.from_occupied_cells(occupied_all, self.grid, radius=density_radius)
        intents: dict[Cell, list[tuple[PedestrianAgent, float]]] = defaultdict(list)
        intended_by_agent: dict[int, Cell] = {}
        for agent in sorted(movable, key=lambda item: item.student_id):
            occupied = set(occupied_all)
            occupied.discard(agent.cell)
            intended, cost = self._intended_move(
                agent,
                occupied_cells=occupied,
                density=movement_density,
                density_radius=density_radius,
            )
            intents[intended].append((agent, cost))
            intended_by_agent[agent.student_id] = intended

        events: list[dict[str, Any]] = []
        moved_agent_ids: set[int] = set()
        winners: dict[int, Cell] = {}
        conflict_losers: set[int] = set()
        for target, contenders in intents.items():
            if len(contenders) == 1:
                agent, _cost = contenders[0]
                winners[agent.student_id] = target
                continue
            ordered = sorted(
                contenders,
                key=lambda item: (self._movement_conflict_priority(item[0]), item[1], self.rng.random(), item[0].student_id),
            )
            winner, _winner_cost = ordered[0]
            winners[winner.student_id] = target
            for loser, _cost in ordered[1:]:
                conflict_losers.add(loser.student_id)
                loser.conflict_count += 1

        planned_targets = {
            agent.student_id: (
                agent.cell if agent.student_id in conflict_losers else winners.get(agent.student_id, agent.cell)
            )
            for agent in movable
        }
        self._apply_local_borrowing_moves(
            movable,
            planned_targets,
            occupied_by=occupied_by,
            density=movement_density,
            density_radius=density_radius,
        )

        for agent in movable:
            previous = agent.cell
            target = planned_targets.get(agent.student_id, previous)
            if target != previous:
                agent.previous_cell = previous
                agent.cell = target
                agent.walking_distance_cells += 1
                agent.walking_time_seconds += duration_sec
                agent.path_cells.append(target)
                frame = {"time_sec": current_time_sec + duration_sec, **cell_to_point(target, self.grid)}
                agent.frames.append(frame)
                events.append(self._movement_event(agent, previous, target, current_time_sec, duration_sec))
                moved_agent_ids.add(agent.student_id)
                agent.stuck_ticks = 0
            if agent.target_cells and agent.cell in agent.target_cells and agent.state is AgentState.TO_WINDOW:
                agent.state = AgentState.QUEUEING
            if agent.target_cells and agent.cell in agent.target_cells and agent.state is AgentState.TO_EXIT:
                agent.state = AgentState.EXITED

        self._refresh_party_centers()
        return events, moved_agent_ids, active_ids

    def run_for_minute(
        self,
        start_sec: int,
        end_sec: int,
        before_tick: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        tick_seconds = max(1, int(getattr(self.config, "movement_tick_seconds", self.tick_seconds)))
        max_ticks = max(1, int(getattr(self.config, "max_movement_ticks_per_minute", 12)))
        tick_count = min(max_ticks, max(1, math.ceil((end_sec - start_sec) / tick_seconds)))
        for tick_index in range(tick_count):
            current = start_sec + tick_index * tick_seconds
            if current >= end_sec:
                break
            if before_tick is not None:
                before_tick(current)
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
            if agent.state in {AgentState.EXITED, AgentState.SEATED}:
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
        occupied = [agent.cell for agent in self.agents.values() if self._occupies_walkable_cell(agent)]
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
        return build_density_hotspots(dense_cells, self.grid, threshold=1)[:24]

    def metrics_snapshot(self) -> dict[str, float | int]:
        metrics = movement_metrics(self.agents, self.tick_seconds, self.max_density)
        return {
            "avg_walking_time": metrics.avg_walking_time,
            "movement_conflict_count": metrics.movement_conflict_count,
            "avg_stuck_ticks": metrics.avg_stuck_ticks,
            "max_density": metrics.max_density,
        }

    def ready_to_queue_student_ids(self, candidate_ids: set[int]) -> list[int]:
        return sorted(
            student_id
            for student_id in candidate_ids
            if (agent := self.agents.get(student_id)) is not None
            and (
                agent.state is AgentState.QUEUEING
                or (agent.state is AgentState.TO_WINDOW and self._is_near_target_cells(agent))
            )
        )

    def party_ready_to_seat(self, party: Any) -> bool:
        student_ids = self._student_ids_for_party(party)
        if not student_ids:
            return False
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None or agent.state is not AgentState.TO_TABLE:
                return False
            if not self._is_near_target_cells(agent):
                return False
        return True

    def _is_near_target_cells(self, agent: PedestrianAgent, max_distance: int = 1) -> bool:
        if not agent.target_cells:
            return False
        return any(
            abs(agent.cell[0] - target[0]) + abs(agent.cell[1] - target[1]) <= max_distance
            for target in agent.target_cells
        )

    def _intended_move(
        self,
        agent: PedestrianAgent,
        occupied_cells: set[Cell],
        density: DensityField | None = None,
        density_radius: int | None = None,
    ) -> tuple[Cell, float]:
        candidates = [agent.cell, *neighbors(agent.cell, self.grid, bool(getattr(self.config, "floor_allow_diagonal", False)))]
        candidates = [
            cell
            for cell in candidates
            if is_walkable(cell, self.grid) and (cell == agent.cell or cell not in occupied_cells)
        ]
        if not candidates or not agent.target_cells:
            return agent.cell, 0.0
        resolved_density_radius = int(
            density_radius if density_radius is not None else getattr(self.config, "personal_space_radius_cells", 1)
        )
        if density is None:
            density = DensityField.from_occupied_cells(occupied_cells, self.grid, radius=resolved_density_radius)
        scored = [
            (cell, self._candidate_cost(cell, agent, density, resolved_density_radius))
            for cell in candidates
        ]
        finite = [(cell, cost) for cell, cost in scored if math.isfinite(cost)]
        if not finite:
            return agent.cell, float("inf")
        return min(finite, key=lambda item: (item[1], item[0][1], item[0][0]))

    def _apply_local_borrowing_moves(
        self,
        movable: list[PedestrianAgent],
        planned_targets: dict[int, Cell],
        occupied_by: dict[Cell, PedestrianAgent],
        density: DensityField,
        density_radius: int,
    ) -> None:
        borrowed_ids: set[int] = set()
        reserved_targets: set[Cell] = {
            target
            for agent in movable
            if (target := planned_targets.get(agent.student_id, agent.cell)) != agent.cell
        }
        for passer in sorted(movable, key=lambda item: (-item.stuck_ticks, item.student_id)):
            if passer.student_id in borrowed_ids:
                continue
            borrow = self._local_borrow_move(
                passer,
                planned_targets,
                occupied_by=occupied_by,
                reserved_targets=reserved_targets,
                density=density,
                density_radius=density_radius,
            )
            if borrow is None:
                continue
            blocker, blocker_cell, yield_cell = borrow
            if blocker.student_id in borrowed_ids:
                continue
            old_passer_target = planned_targets.get(passer.student_id, passer.cell)
            old_blocker_target = planned_targets.get(blocker.student_id, blocker.cell)
            reserved_targets.discard(old_passer_target)
            reserved_targets.discard(old_blocker_target)
            planned_targets[passer.student_id] = blocker_cell
            planned_targets[blocker.student_id] = yield_cell
            reserved_targets.update({blocker_cell, yield_cell})
            borrowed_ids.update({passer.student_id, blocker.student_id})

    def _local_borrow_move(
        self,
        passer: PedestrianAgent,
        planned_targets: dict[int, Cell],
        occupied_by: dict[Cell, PedestrianAgent],
        reserved_targets: set[Cell],
        density: DensityField,
        density_radius: int,
    ) -> tuple[PedestrianAgent, Cell, Cell] | None:
        if passer.state is not AgentState.TO_TABLE:
            return None
        if passer.stuck_ticks < int(getattr(self.config, "floor_borrow_after_stuck_ticks", 4)):
            return None
        if not passer.target_cells:
            return None
        blocker_cell = self._borrow_blocking_cell(passer, planned_targets, occupied_by)
        if blocker_cell is None:
            return None
        blocker = occupied_by.get(blocker_cell)
        if blocker is None or not self._can_yield_for_borrow(blocker):
            return None
        if planned_targets.get(blocker.student_id, blocker.cell) != blocker.cell:
            return None
        yield_cell = self._borrow_yield_cell(
            passer,
            blocker,
            occupied_by=occupied_by,
            reserved_targets=reserved_targets,
            density=density,
            density_radius=density_radius,
        )
        if yield_cell is None:
            return None
        return blocker, blocker_cell, yield_cell

    def _borrow_blocking_cell(
        self,
        passer: PedestrianAgent,
        planned_targets: dict[int, Cell],
        occupied_by: dict[Cell, PedestrianAgent],
    ) -> Cell | None:
        static_field = self._static_field(passer.target_cells)
        current_distance = static_field.get(passer.cell, float("inf"))
        planned = planned_targets.get(passer.student_id, passer.cell)
        planned_distance = static_field.get(planned, current_distance)
        best_open_distance = min(current_distance, planned_distance)
        candidates: list[tuple[float, Cell]] = []
        for cell in neighbors(passer.cell, self.grid, bool(getattr(self.config, "floor_allow_diagonal", False))):
            blocker = occupied_by.get(cell)
            if blocker is None or blocker.student_id == passer.student_id:
                continue
            distance = static_field.get(cell, float("inf"))
            if math.isfinite(distance) and distance < best_open_distance:
                candidates.append((distance, cell))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1][1], item[1][0]))[1]

    def _borrow_yield_cell(
        self,
        passer: PedestrianAgent,
        blocker: PedestrianAgent,
        occupied_by: dict[Cell, PedestrianAgent],
        reserved_targets: set[Cell],
        density: DensityField,
        density_radius: int,
    ) -> Cell | None:
        candidates = self._borrow_yield_candidates(passer, blocker)
        valid: list[tuple[int, float, Cell]] = []
        for order, cell in enumerate(candidates):
            if cell == blocker.cell:
                continue
            if cell in passer.target_cells:
                continue
            if cell in reserved_targets and cell != passer.cell:
                continue
            occupant = occupied_by.get(cell)
            if occupant is not None and occupant.student_id != passer.student_id:
                continue
            if not is_walkable(cell, self.grid):
                continue
            valid.append((order, self._yield_candidate_cost(cell, blocker, density, density_radius), cell))
        if not valid:
            return None
        return min(valid, key=lambda item: (item[0], item[1], item[2][1], item[2][0]))[2]

    def _borrow_yield_candidates(self, passer: PedestrianAgent, blocker: PedestrianAgent) -> list[Cell]:
        dx = blocker.cell[0] - passer.cell[0]
        dy = blocker.cell[1] - passer.cell[1]
        lateral: list[Cell] = []
        if abs(dx) + abs(dy) == 1:
            lateral = [
                (blocker.cell[0] - dy, blocker.cell[1] + dx),
                (blocker.cell[0] + dy, blocker.cell[1] - dx),
            ]
        candidates: list[Cell] = [*lateral, passer.cell]
        for cell in neighbors(blocker.cell, self.grid, allow_diagonal=False):
            if cell not in candidates:
                candidates.append(cell)
        return candidates

    def _yield_candidate_cost(
        self,
        cell: Cell,
        blocker: PedestrianAgent,
        density: DensityField,
        density_radius: int,
    ) -> float:
        target_distance = 0.0
        if blocker.target_cells:
            field = self._static_field(blocker.target_cells)
            target_distance = field.get(cell, 0.0)
            if not math.isfinite(target_distance):
                target_distance = 10_000.0
        threshold = int(getattr(self.config, "congestion_density_threshold", 3))
        return target_distance + density.penalty(
            cell,
            threshold=threshold,
            excluded_cell=blocker.cell,
            radius=density_radius,
        )

    def _can_yield_for_borrow(self, agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _movement_conflict_priority(self, agent: PedestrianAgent) -> int:
        borrow_threshold = int(getattr(self.config, "floor_borrow_after_stuck_ticks", 4))
        if agent.state is AgentState.TO_TABLE and agent.stuck_ticks >= borrow_threshold:
            return -1
        return 0

    def _candidate_cost(self, cell: Cell, agent: PedestrianAgent, density: DensityField, density_radius: int) -> float:
        static_field = self._static_field(agent.target_cells)
        static_distance = static_field.get(cell, float("inf"))
        if not math.isfinite(static_distance):
            return float("inf")
        threshold = int(getattr(self.config, "congestion_density_threshold", 3))
        cost = float(getattr(self.config, "floor_static_weight", 1.0)) * static_distance
        cost += float(getattr(self.config, "floor_density_weight", 1.2)) * density.penalty(
            cell,
            threshold=threshold,
            excluded_cell=agent.cell,
            radius=density_radius,
        )
        if cell != agent.cell:
            cost -= float(getattr(self.config, "floor_dynamic_weight", 0.35)) * self.dynamic_field.values.get(cell, 0.0)
        elif agent.target_cells and not self._is_near_target_cells(agent):
            stuck_penalty = max(0, agent.stuck_ticks - 2) * float(getattr(self.config, "floor_stuck_wait_penalty", 0.15))
            cost += min(4.0, stuck_penalty)
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
                if student_id in self.agents and self._occupies_walkable_cell(self.agents[student_id])
            ]
            if not members:
                party.group_center = None
                continue
            party.group_center = (
                sum(agent.cell[0] for agent in members) / len(members),
                sum(agent.cell[1] for agent in members) / len(members),
            )

    def _update_queue_targets(self) -> None:
        for window_index, queue in list(self.window_queues.items()):
            queue_cells = build_window_queue_cells(self.grid, window_index)
            if not queue_cells:
                continue
            for position, student_id in enumerate(queue):
                agent = self.agents.get(student_id)
                if agent is None:
                    continue
                target = queue_cells[min(position, len(queue_cells) - 1)]
                agent.desired_window_index = window_index
                agent.target_type = "window_queue"
                agent.target_id = window_index
                agent.target_cells = {target}
                if agent.cell == target:
                    agent.state = AgentState.QUEUEING

    def _update_density_metric(self) -> None:
        occupied = {
            agent.cell
            for agent in self.agents.values()
            if self._occupies_walkable_cell(agent)
        }
        density = DensityField.from_occupied_cells(occupied, self.grid, radius=int(getattr(self.config, "personal_space_radius_cells", 1)))
        self.max_density = max(self.max_density, max(density.densities.values(), default=0))

    def _occupies_walkable_cell(self, agent: PedestrianAgent) -> bool:
        return agent.state not in {AgentState.EXITED, AgentState.SEATED}

    def _is_movable(self, agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _movement_event(
        self,
        agent: PedestrianAgent,
        start: Cell,
        end: Cell,
        current_time_sec: float,
        duration_sec: float | None = None,
    ) -> dict[str, Any]:
        start_point = cell_to_point(start, self.grid)
        end_point = cell_to_point(end, self.grid)
        duration = float(duration_sec if duration_sec is not None else self.tick_seconds)
        arrive_time_sec = current_time_sec + duration
        playback_duration_ms = max(24, int(round(duration * 40)))
        return {
            "type": "pedestrian_move",
            "party_id": agent.party_id,
            "student_id": agent.student_id,
            "size": 1,
            "member_count": 1,
            "state": agent.state.value,
            "start_time_sec": current_time_sec,
            "arrive_time_sec": arrive_time_sec,
            "duration_sec": duration,
            "playback_start_ms": 0,
            "playback_duration_ms": playback_duration_ms,
            "playback_end_ms": playback_duration_ms,
            "from": start_point,
            "to": end_point,
            "path": [start_point, end_point],
            "frames": [
                {"time_sec": current_time_sec, **start_point, "progress": 0.0},
                {"time_sec": arrive_time_sec, **end_point, "progress": 1.0},
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
