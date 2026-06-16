from __future__ import annotations

import math
from heapq import heappop, heappush
from collections import Counter, OrderedDict, defaultdict, deque
from typing import Any, Callable

from .agents import AgentState, PartyMovementState, PedestrianAgent
from .fields import DensityField, DynamicField, build_static_field, wall_distance_or_penalty
from .grid import Cell, GridData, cell_to_point, grid_from_layout, neighbors
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
        self.floor_allow_diagonal = bool(getattr(config, "floor_allow_diagonal", False))
        self.floor_static_weight = float(getattr(config, "floor_static_weight", 1.0))
        self.floor_density_weight = float(getattr(config, "floor_density_weight", 1.2))
        self.floor_dynamic_weight = float(getattr(config, "floor_dynamic_weight", 0.35))
        self.floor_wall_weight = float(getattr(config, "floor_wall_weight", 0.6))
        self.floor_inertia_weight = float(getattr(config, "floor_inertia_weight", 0.25))
        self.floor_group_weight = float(getattr(config, "floor_group_weight", 0.8))
        self.floor_randomness = float(getattr(config, "floor_randomness", 0.05))
        self.floor_stuck_wait_penalty = float(getattr(config, "floor_stuck_wait_penalty", 0.15))
        self.congestion_density_threshold = int(getattr(config, "congestion_density_threshold", 3))
        self.congestion_density_threshold_floor = max(0, self.congestion_density_threshold)
        self.queue_lane_avoidance_weight = float(getattr(config, "queue_lane_avoidance_weight", 4.0))
        self.dynamic_route_trigger_threshold = float(getattr(config, "dynamic_route_trigger_threshold", 8.0))
        self.personal_space_radius_cells = int(getattr(config, "personal_space_radius_cells", 1))
        self.floor_borrow_after_stuck_ticks = int(getattr(config, "floor_borrow_after_stuck_ticks", 4))
        self.local_repair_after_stuck_ticks = int(
            getattr(config, "local_repair_after_stuck_ticks", self.floor_borrow_after_stuck_ticks)
        )
        self.local_repair_horizon = max(2, int(getattr(config, "local_repair_horizon", 4)))
        self.local_repair_radius = max(2, int(getattr(config, "local_repair_radius", 5)))
        self.local_repair_max_agents = max(3, int(getattr(config, "local_repair_max_agents", 8)))
        self.local_repair_max_attempts = max(1, int(getattr(config, "local_repair_max_attempts", 2)))
        self.dynamic_route_search_margin = max(
            4,
            int(getattr(config, "dynamic_route_search_margin", self.local_repair_radius * 3)),
        )
        self.dynamic_route_max_fields_per_step = max(
            0,
            int(getattr(config, "dynamic_route_max_fields_per_step", 0)),
        )
        self.static_field_cache_limit = max(16, int(getattr(config, "static_field_cache_limit", 256)))
        self.neighbors4: dict[Cell, list[Cell]] = {
            (col, row): neighbors((col, row), self.grid, allow_diagonal=False)
            for col in range(self.grid.cols)
            for row in range(self.grid.rows)
        }
        self.neighbors8: dict[Cell, list[Cell]] = {
            (col, row): neighbors((col, row), self.grid, allow_diagonal=True)
            for col in range(self.grid.cols)
            for row in range(self.grid.rows)
        }
        self.in_bounds_cells: set[Cell] = {
            (col, row)
            for col in range(self.grid.cols)
            for row in range(self.grid.rows)
        }
        self.wall_penalties: dict[Cell, float] = {
            cell: wall_distance_or_penalty(cell, self.grid)
            for cell in self.in_bounds_cells
            if cell not in self.grid.blocked_cells
        }
        self.dynamic_field = DynamicField(
            decay=float(getattr(config, "dynamic_field_decay", 0.85)),
            diffusion=float(getattr(config, "dynamic_field_diffusion", 0.10)),
        )
        self.agents: dict[int, PedestrianAgent] = {}
        self.party_states: dict[int, PartyMovementState] = {}
        self.has_multi_member_parties = False
        # window_queues is the physical FIFO queue occupying ordered queue slots.
        self.window_queues: dict[int, list[int]] = defaultdict(list)
        # window_walkers have chosen a window and are walking toward the queue tail;
        # they are not service-eligible until promoted into window_queues.
        self.window_walkers: dict[int, list[int]] = defaultdict(list)
        self.queue_slot_lookup: dict[Cell, tuple[int, int]] = {
            cell: (window_index, slot_index)
            for window_index, queue_slots in self.grid.queue_cells_by_window.items()
            for slot_index, cell in enumerate(queue_slots)
        }
        self.queue_lane_distance_lookup: dict[Cell, int] = {}
        self._queue_lane_distance_source: tuple[Cell, ...] = ()
        self._refresh_queue_lane_distance_lookup()
        self.queue_side_constraints: dict[int, tuple[Cell, tuple[int, int]]] = {}
        for window_index, service in self.grid.service_cells.items():
            queue_slots = self.grid.queue_cells_by_window.get(window_index, [])
            if not queue_slots:
                continue
            head_slot = queue_slots[0]
            normal = (
                max(-1, min(1, head_slot[0] - service[0])),
                max(-1, min(1, head_slot[1] - service[1])),
            )
            self.queue_side_constraints[window_index] = (service, normal)
        self.reserved_service_area_by_window: dict[int, set[Cell]] = {
            window_index: self._build_reserved_service_area(window_index)
            for window_index in self.grid.service_cells
        }
        self.reserved_service_cells: set[Cell] = {
            cell
            for reserved_cells in self.reserved_service_area_by_window.values()
            for cell in reserved_cells
        }
        self.service_window_by_cell: dict[Cell, int] = {
            service: window_index
            for window_index, service in self.grid.service_cells.items()
        }
        self.queue_slot_assignments_by_window: dict[int, dict[int, int]] = {}
        self.queue_slot_owner_lookup: dict[Cell, int] = {}
        self.queue_windows_with_assignments: set[int] = set()
        self.window_queue_member_sets: dict[int, set[int]] = {}
        self.table_approach_owner_lookup: dict[Cell, int] = {}
        self._refresh_movement_indexes()
        self.static_fields: OrderedDict[tuple[Cell, ...], dict[Cell, float]] = OrderedDict()
        self.dynamic_cost_fields: dict[tuple[Any, ...], dict[Cell, float]] = {}
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
                if len(party_state.member_agent_ids) > 1:
                    self.has_multi_member_parties = True
        self._refresh_party_centers_if_needed()

    def _next_entry_spawn_cell(self, door_index: int, occupied_cells: set[Cell]) -> Cell:
        candidates = self._entry_spawn_candidates(door_index)
        for cell in candidates:
            if cell not in occupied_cells:
                return cell
        return candidates[0] if candidates else (0, 0)

    def _start_movement_leg(self, agent: PedestrianAgent, key: tuple[Any, ...], force: bool = False) -> None:
        if not force and agent.movement_leg_key == key and agent.movement_leg_start_cell is not None:
            return
        self._complete_movement_leg(agent)
        agent.movement_leg_key = key
        agent.movement_leg_start_cell = agent.cell
        agent.movement_leg_distance_cells = 0.0

    def _complete_movement_leg(self, agent: PedestrianAgent) -> None:
        start = agent.movement_leg_start_cell
        distance = float(agent.movement_leg_distance_cells or 0.0)
        if start is not None and distance > 0:
            straight_distance = math.hypot(agent.cell[0] - start[0], agent.cell[1] - start[1])
            if straight_distance > 0:
                agent.movement_leg_distance_ratios.append(distance / straight_distance)
        agent.movement_leg_key = None
        agent.movement_leg_start_cell = agent.cell
        agent.movement_leg_distance_cells = 0.0

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
            if self._is_walkable_cell(current):
                candidates.append(current)
            if distance >= max_radius:
                continue
            for neighbor in self.neighbors8.get(current, []):
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
        self._remove_from_window_tracking(student_id)
        self.window_walkers[window_index].append(student_id)
        agent.desired_window_index = window_index
        agent.assigned_queue_slot_index = None
        agent.target_type = "window_queue"
        agent.target_id = window_index
        agent.state = AgentState.TO_WINDOW
        self._start_movement_leg(agent, ("window", window_index))
        self._update_queue_targets()

    def set_window_physical_queue(self, window_index: int, student_ids: list[int]) -> None:
        window_index = max(0, int(window_index))
        unique_ids: list[int] = []
        for student_id in student_ids:
            if student_id not in unique_ids:
                unique_ids.append(int(student_id))
        for student_id in unique_ids:
            self._remove_from_window_tracking(student_id)
        self.window_queues[window_index] = unique_ids
        for position, student_id in enumerate(unique_ids):
            agent = self.agents.get(student_id)
            if agent is None:
                continue
            agent.desired_window_index = window_index
            agent.assigned_queue_slot_index = position
            agent.target_type = "window_queue"
            agent.target_id = window_index
        self._update_queue_targets()

    def _remove_from_window_tracking(self, student_id: int) -> None:
        for queues in (self.window_queues, self.window_walkers):
            for queue in queues.values():
                while student_id in queue:
                    queue.remove(student_id)

    def set_party_target_table(self, party: Any, table_index: int) -> None:
        student_ids = self._student_ids_for_party(party)
        targets = set(self.grid.table_approach_cells.get(table_index, set()))
        if not targets and table_index in self.grid.table_cells:
            targets = {
                neighbor
                for cell in self.grid.table_cells[table_index]
                for neighbor in self.neighbors8.get(cell, [])
                if self._is_walkable_cell(neighbor)
            }
        assigned_slots = self._assign_table_approach_slots(student_ids, table_index, targets)
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None:
                continue
            target = assigned_slots.get(student_id)
            agent.state = AgentState.TO_TABLE
            agent.table_index = table_index
            agent.target_type = "table"
            agent.target_id = table_index
            agent.assigned_table_approach_cell = target
            agent.target_cells = {target} if target is not None else set(targets)
            agent.table_repair_failures = 0
            self._start_movement_leg(agent, ("table", table_index))
        if student_ids:
            party_id = self.agents[student_ids[0]].party_id
            party_state = self.party_states.setdefault(party_id, PartyMovementState(party_id=party_id))
            party_state.reserved_table_index = table_index
            party_state.cohesion_enabled = True
        self._refresh_table_approach_owner_index()
        self._refresh_party_centers_if_needed()

    def _assign_table_approach_slots(
        self,
        student_ids: list[int],
        table_index: int,
        targets: set[Cell],
    ) -> dict[int, Cell]:
        open_targets = sorted(targets)
        assigned: dict[int, Cell] = {}
        used: set[Cell] = set()
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None or not open_targets:
                continue
            candidates = [cell for cell in open_targets if cell not in used] or open_targets
            target = min(
                candidates,
                key=lambda cell: (
                    abs(agent.cell[0] - cell[0]) + abs(agent.cell[1] - cell[1]),
                    cell[1],
                    cell[0],
                ),
            )
            assigned[student_id] = target
            used.add(target)
        return assigned

    def set_agent_service(self, student_id: int, window_index: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        service = self.grid.service_cells.get(window_index)
        if service is not None:
            agent.target_cells = {service}
        self._complete_movement_leg(agent)
        agent.state = AgentState.SERVICE
        agent.target_type = "service"
        agent.target_id = window_index
        self._remove_from_window_tracking(student_id)
        agent.assigned_queue_slot_index = None
        self._update_queue_targets()

    def set_agent_waiting_group(self, student_id: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None or agent.state is AgentState.EXITED:
            return
        self._refresh_queue_lane_distance_lookup_if_needed()
        agent.state = AgentState.WAITING_GROUP
        agent.target_type = "group"
        agent.target_id = agent.party_id
        target = self._waiting_group_target_cell(agent)
        agent.target_cells = {target}
        self._start_movement_leg(agent, ("group", agent.party_id, *target), force=True)
        self._refresh_table_approach_owner_index()

    def _waiting_group_target_cell(self, agent: PedestrianAgent) -> Cell:
        occupied = {
            other.cell
            for other in self.agents.values()
            if other.student_id != agent.student_id
            and other.state not in {AgentState.SEATED, AgentState.EXITED}
        }
        density = DensityField.from_occupied_cells(
            occupied,
            self.grid,
            radius=max(2, self.personal_space_radius_cells),
        )
        max_search_distance = max(12, self.local_repair_radius * 4)
        frontier: deque[tuple[Cell, int]] = deque([(agent.cell, 0)])
        seen = {agent.cell}
        best_cell: Cell | None = None
        best_score: tuple[float, int, int, int, int] | None = None
        while frontier:
            current, distance = frontier.popleft()
            if self._is_safe_waiting_group_cell(agent, current, occupied):
                score = self._waiting_group_cell_score(current, distance, density)
                if best_score is None or score < best_score:
                    best_score = score
                    best_cell = current
            if distance >= max_search_distance:
                continue
            for candidate in self.neighbors4.get(current, []):
                if candidate in seen:
                    continue
                seen.add(candidate)
                frontier.append((candidate, distance + 1))
        return best_cell if best_cell is not None else agent.cell

    def _waiting_group_cell_score(
        self,
        cell: Cell,
        distance: int,
        density: DensityField,
    ) -> tuple[float, int, int, int, int]:
        queue_clearance = self._nearest_queue_lane_distance(cell)
        if queue_clearance is None:
            queue_penalty = 0
        else:
            queue_penalty = max(0, 5 - queue_clearance)
        return (
            float(max(0, density.density(cell) - 1)),
            queue_penalty,
            distance,
            cell[1],
            cell[0],
        )

    def _is_safe_waiting_group_cell(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        occupied: set[Cell],
    ) -> bool:
        if not self._is_walkable_cell(cell):
            return False
        if cell in occupied:
            return False
        if self._is_reserved_service_area(cell):
            return False
        if self._is_near_window_service_or_head(cell):
            return False
        if self._is_near_window_queue_lane(cell):
            return False
        if self._is_queue_slot(cell):
            return False
        table_owner = self._table_approach_owner(cell)
        if table_owner is not None and table_owner != agent.student_id:
            return False
        return True

    def _is_near_window_queue_lane(self, cell: Cell) -> bool:
        distance = self._nearest_queue_lane_distance(cell)
        return distance is not None and distance <= 1

    def _nearest_queue_lane_distance(self, cell: Cell) -> int | None:
        return self.queue_lane_distance_lookup.get(cell)

    def _refresh_queue_lane_distance_lookup_if_needed(self) -> None:
        source = self._queue_lane_distance_cells()
        if source != self._queue_lane_distance_source:
            self._refresh_queue_lane_distance_lookup(source)

    def _refresh_queue_lane_distance_lookup(self, source: tuple[Cell, ...] | None = None) -> None:
        source = self._queue_lane_distance_cells() if source is None else source
        self._queue_lane_distance_source = source
        if not source:
            self.queue_lane_distance_lookup = {}
            return
        distances: dict[Cell, int] = {}
        frontier: deque[Cell] = deque()
        for cell in source:
            if cell in distances:
                continue
            distances[cell] = 0
            frontier.append(cell)
        while frontier:
            current = frontier.popleft()
            distance = distances[current] + 1
            col, row = current
            for next_col in range(max(0, col - 1), min(self.grid.cols, col + 2)):
                for next_row in range(max(0, row - 1), min(self.grid.rows, row + 2)):
                    candidate = (next_col, next_row)
                    if candidate == current or candidate in distances:
                        continue
                    distances[candidate] = distance
                    frontier.append(candidate)
        self.queue_lane_distance_lookup = distances

    def _queue_lane_distance_cells(self) -> tuple[Cell, ...]:
        return tuple(
            sorted(
                {
                    cell
                    for queue_slots in self.grid.queue_cells_by_window.values()
                    for cell in queue_slots
                }
            )
        )

    def _is_near_window_service_or_head(self, cell: Cell) -> bool:
        for window_index, service in self.grid.service_cells.items():
            if abs(cell[0] - service[0]) + abs(cell[1] - service[1]) <= 3:
                return True
            queue_slots = self.grid.queue_cells_by_window.get(window_index, [])
            if queue_slots:
                head_slot = queue_slots[0]
                normal = (
                    max(-1, min(1, head_slot[0] - service[0])),
                    max(-1, min(1, head_slot[1] - service[1])),
                )
                side = (normal[1], normal[0])
                forward = (cell[0] - service[0]) * normal[0] + (cell[1] - service[1]) * normal[1]
                lateral = (cell[0] - service[0]) * side[0] + (cell[1] - service[1]) * side[1]
                if 0 <= forward <= 6 and abs(lateral) <= 6:
                    return True
                if forward < 0 and abs(lateral) <= 4:
                    return True
                if abs(cell[0] - head_slot[0]) + abs(cell[1] - head_slot[1]) <= 2:
                    return True
        return False

    def _retarget_waiting_group_agents(self) -> None:
        waiting_agents = [agent for agent in self.agents.values() if agent.state is AgentState.WAITING_GROUP]
        if not waiting_agents:
            return
        self._refresh_queue_lane_distance_lookup_if_needed()
        occupied = {
            other.cell
            for other in self.agents.values()
            if other.state not in {AgentState.SEATED, AgentState.EXITED}
        }
        density_radius = max(2, self.personal_space_radius_cells)
        target_density = DensityField.from_occupied_cells(occupied, self.grid, radius=density_radius)
        for agent in waiting_agents:
            occupied_without_self = set(occupied)
            occupied_without_self.discard(agent.cell)
            targets = agent.target_cells or {agent.cell}
            if targets:
                targets_are_safe = all(
                    self._is_safe_waiting_group_cell(agent, target, occupied_without_self)
                    for target in targets
                )
                if targets_are_safe:
                    target_is_dense = any(
                        target_density.density_without(target, agent.cell, density_radius) > 1
                        for target in targets
                    )
                    if not target_is_dense or agent.stuck_ticks < self.local_repair_after_stuck_ticks:
                        continue
            target = self._waiting_group_target_cell(agent)
            agent.target_cells = {target}
            self._start_movement_leg(agent, ("group", agent.party_id, *target), force=True)
            agent.stuck_ticks = 0

    def set_agent_seated(self, student_id: int, table_index: int, preserve_cell: bool = False) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        self._complete_movement_leg(agent)
        targets = sorted(self.grid.table_approach_cells.get(table_index, set()))
        if targets and not preserve_cell:
            agent.cell = targets[(student_id - 1) % len(targets)]
            agent.path_cells.append(agent.cell)
        agent.state = AgentState.SEATED
        agent.table_index = table_index
        agent.target_type = "table"
        agent.target_id = table_index
        agent.assigned_table_approach_cell = None
        agent.target_cells = set()
        self._refresh_table_approach_owner_index()

    def set_agent_exited(self, student_id: int) -> None:
        agent = self.agents.get(student_id)
        if agent is None:
            return
        self._complete_movement_leg(agent)
        agent.state = AgentState.EXITED
        agent.target_type = None
        agent.target_id = None
        agent.target_cells = set()
        agent.assigned_queue_slot_index = None
        agent.assigned_table_approach_cell = None
        agent.table_index = None
        if not agent.path_cells:
            agent.path_cells.append(agent.cell)
        self._refresh_movement_indexes()
        self._refresh_table_approach_owner_index()

    def tick(self, current_time_sec: int) -> list[dict[str, Any]]:
        self._update_queue_targets()
        self._refresh_table_approach_owner_index()
        self._retarget_waiting_group_agents()
        self._refresh_party_centers_if_needed()
        self._repair_used_this_tick = False
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
        self._refresh_party_centers_if_needed()
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
        queueing_cells_all: set[Cell] = set()
        queueing_cells_by_window: dict[int, set[Cell]] = defaultdict(set)
        for cell, occupant in occupied_by.items():
            if occupant.state is not AgentState.QUEUEING:
                continue
            queueing_cells_all.add(cell)
            if occupant.desired_window_index is not None:
                queueing_cells_by_window[occupant.desired_window_index].add(cell)
        density_radius = self.personal_space_radius_cells
        movement_density = DensityField.from_occupied_cells(occupied_all, self.grid, radius=density_radius)
        self.dynamic_cost_fields = {}
        intents: dict[Cell, list[tuple[PedestrianAgent, float]]] = defaultdict(list)
        intended_by_agent: dict[int, Cell] = {}
        for agent in sorted(movable, key=lambda item: item.student_id):
            occupied = self._occupied_cells_for_agent(
                agent,
                occupied_by,
                occupied_all,
                queueing_cells_all=queueing_cells_all,
                queueing_cells_by_window=queueing_cells_by_window,
            )
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
            queue_passthrough_winners = self._queue_passthrough_winners(target, contenders, occupied_by)
            if queue_passthrough_winners:
                winners.update(queue_passthrough_winners)
                winner_ids = set(queue_passthrough_winners)
                for loser, _cost in contenders:
                    if loser.student_id in winner_ids:
                        continue
                    conflict_losers.add(loser.student_id)
                    self._record_movement_conflict(loser, contenders)
                continue
            ordered = sorted(
                contenders,
                key=lambda item: (self._movement_conflict_priority(item[0]), item[1], self.rng.random(), item[0].student_id),
            )
            winner, _winner_cost = ordered[0]
            winners[winner.student_id] = target
            for loser, _cost in ordered[1:]:
                conflict_losers.add(loser.student_id)
                self._record_movement_conflict(loser, contenders)

        planned_targets = {
            agent.student_id: (
                agent.cell if agent.student_id in conflict_losers else winners.get(agent.student_id, agent.cell)
            )
            for agent in movable
        }
        self._resolve_edge_swaps(movable, planned_targets)
        self._apply_local_repair_moves(movable, planned_targets, occupied_by=occupied_by)
        self._apply_local_borrowing_moves(
            movable,
            planned_targets,
            occupied_by=occupied_by,
            density=movement_density,
            density_radius=density_radius,
        )
        self._resolve_edge_swaps(movable, planned_targets)

        for agent in movable:
            previous = agent.cell
            target = planned_targets.get(agent.student_id, previous)
            if target != previous:
                if not self.can_agent_enter_cell(agent, target):
                    planned_targets[agent.student_id] = previous
                    target = previous
            if target != previous:
                agent.previous_cell = previous
                agent.cell = target
                agent.walking_distance_cells += 1
                if agent.movement_leg_key is not None and agent.movement_leg_start_cell is not None:
                    agent.movement_leg_distance_cells += math.hypot(target[0] - previous[0], target[1] - previous[1])
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
                self._complete_movement_leg(agent)
            if agent.target_cells and agent.cell in agent.target_cells and agent.state is AgentState.WAITING_GROUP:
                self._complete_movement_leg(agent)

        self._refresh_party_centers_if_needed()
        return events, moved_agent_ids, active_ids

    def _occupied_cells_for_agent(
        self,
        agent: PedestrianAgent,
        occupied_by: dict[Cell, PedestrianAgent],
        occupied_all: set[Cell],
        queueing_cells_all: set[Cell] | None = None,
        queueing_cells_by_window: dict[int, set[Cell]] | None = None,
    ) -> set[Cell]:
        occupied = set(occupied_all)
        occupied.discard(agent.cell)
        self._discard_passable_queue_cells(
            agent,
            occupied,
            occupied_by,
            queueing_cells_all=queueing_cells_all,
            queueing_cells_by_window=queueing_cells_by_window,
        )
        self._discard_followable_same_queue_cells(agent, occupied, occupied_by)
        return occupied

    def _discard_passable_queue_cells(
        self,
        agent: PedestrianAgent,
        occupied: set[Cell],
        occupied_by: dict[Cell, PedestrianAgent],
        queueing_cells_all: set[Cell] | None = None,
        queueing_cells_by_window: dict[int, set[Cell]] | None = None,
    ) -> None:
        if queueing_cells_all is not None:
            occupied.difference_update(queueing_cells_all)
        else:
            for cell, occupant in occupied_by.items():
                if occupant.state is AgentState.QUEUEING:
                    occupied.discard(cell)
        if self._agent_can_pass_through_queue(agent):
            return
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING} or agent.desired_window_index is None:
            return
        if queueing_cells_by_window is not None:
            for window_index, cells in queueing_cells_by_window.items():
                if window_index != agent.desired_window_index:
                    occupied.difference_update(cells)
            return
        for window_index, queue_slots in self.grid.queue_cells_by_window.items():
            if window_index == agent.desired_window_index:
                continue
            for cell in queue_slots:
                occupant = occupied_by.get(cell)
                if occupant is not None and occupant.state is AgentState.QUEUEING:
                    occupied.discard(cell)

    def _discard_followable_same_queue_cells(
        self,
        agent: PedestrianAgent,
        occupied: set[Cell],
        occupied_by: dict[Cell, PedestrianAgent],
    ) -> None:
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return
        window_index = agent.desired_window_index
        if window_index is None or agent.assigned_queue_slot_index is None:
            return
        queue_members = self.window_queue_member_sets.get(window_index, set())
        if agent.student_id not in queue_members:
            return
        queue_slots = self.grid.queue_cells_by_window.get(window_index, [])
        for cell in queue_slots[: agent.assigned_queue_slot_index + 1]:
            occupant = occupied_by.get(cell)
            if occupant is None:
                continue
            if occupant.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
                continue
            if occupant.desired_window_index != window_index:
                continue
            if occupant.student_id not in queue_members:
                continue
            if occupant.assigned_queue_slot_index is None:
                continue
            if occupant.assigned_queue_slot_index < agent.assigned_queue_slot_index:
                occupied.discard(cell)

    def _agent_can_pass_through_queue(self, agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.ENTERING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _agent_can_pass_through_queue_cell(self, agent: PedestrianAgent, cell: Cell) -> bool:
        queue_info = self._queue_slot_info(cell)
        if queue_info is None:
            return self._agent_can_pass_through_queue(agent)
        queue_window, _slot_index, _queue_owner = queue_info
        return self._agent_can_pass_through_queue_window(agent, queue_window)

    def _agent_can_pass_through_queue_window(self, agent: PedestrianAgent, window_index: int) -> bool:
        return True

    def _agent_can_follow_same_queue_occupant(
        self,
        agent: PedestrianAgent,
        occupant: PedestrianAgent,
        cell: Cell,
    ) -> bool:
        if agent.student_id == occupant.student_id:
            return False
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return False
        if occupant.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return False
        if agent.desired_window_index is None or agent.desired_window_index != occupant.desired_window_index:
            return False
        queue_members = self.window_queues.get(agent.desired_window_index, [])
        if agent.student_id not in queue_members or occupant.student_id not in queue_members:
            return False
        if agent.assigned_queue_slot_index is None or occupant.assigned_queue_slot_index is None:
            return False
        if occupant.assigned_queue_slot_index >= agent.assigned_queue_slot_index:
            return False
        queue_info = self._queue_slot_info(cell)
        if queue_info is None:
            return False
        queue_window, queue_slot_index, _queue_owner = queue_info
        return queue_window == agent.desired_window_index and queue_slot_index <= agent.assigned_queue_slot_index

    def _queue_passthrough_winners(
        self,
        target: Cell,
        contenders: list[tuple[PedestrianAgent, float]],
        occupied_by: dict[Cell, PedestrianAgent],
    ) -> dict[int, Cell]:
        queue_occupant = occupied_by.get(target)
        if queue_occupant is None or queue_occupant.state is not AgentState.QUEUEING:
            return {}
        queue_contender = next(
            (agent for agent, _cost in contenders if agent.student_id == queue_occupant.student_id),
            queue_occupant,
        )
        passers = [
            (agent, cost)
            for agent, cost in contenders
            if agent.student_id != queue_occupant.student_id and self._agent_can_pass_through_queue_cell(agent, target)
        ]
        if not passers:
            return {}
        passer, _cost = min(passers, key=lambda item: (item[1], item[0].student_id))
        return {
            queue_contender.student_id: target,
            passer.student_id: target,
        }

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
            "avg_walking_distance_ratio": metrics.avg_walking_distance_ratio,
        }

    def ready_to_queue_student_ids(self, candidate_ids: set[int]) -> list[int]:
        ready: list[tuple[int, int, int, int]] = []
        for window_index in sorted(self.window_walkers):
            queue = self.window_walkers[window_index]
            for position, student_id in enumerate(queue):
                if student_id not in candidate_ids:
                    continue
                agent = self.agents.get(student_id)
                if agent is None:
                    continue
                if self._agent_reached_queue_target(agent):
                    slot_index = agent.assigned_queue_slot_index if agent.assigned_queue_slot_index is not None else position
                    ready.append((window_index, slot_index, position, student_id))
        tracked_walkers = {
            student_id
            for queue in self.window_walkers.values()
            for student_id in queue
        }
        ready_ids = {student_id for _window, _slot, _position, student_id in ready}
        for student_id in sorted(candidate_ids - tracked_walkers - ready_ids):
            agent = self.agents.get(student_id)
            if agent is None:
                continue
            if self._agent_reached_queue_target(agent):
                slot_index = agent.assigned_queue_slot_index if agent.assigned_queue_slot_index is not None else 10_000
                window_index = agent.desired_window_index if agent.desired_window_index is not None else 10_000
                ready.append((window_index, slot_index, 10_000, student_id))
        return [student_id for _window, _slot, _position, student_id in sorted(ready)]

    def _agent_reached_queue_target(self, agent: PedestrianAgent) -> bool:
        return bool(agent.target_cells) and self._is_near_target_cells(agent)

    def party_ready_to_seat(self, party: Any) -> bool:
        student_ids = self._student_ids_for_party(party)
        if not student_ids:
            return False
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None or agent.state is not AgentState.TO_TABLE:
                return False
            if agent.assigned_table_approach_cell is not None:
                target = agent.assigned_table_approach_cell
                if abs(agent.cell[0] - target[0]) + abs(agent.cell[1] - target[1]) > 1:
                    return False
                continue
            if not self._is_near_target_cells(agent):
                return False
        return True

    def recover_party_table_targets(self, party: Any) -> bool:
        student_ids = self._student_ids_for_party(party)
        if not student_ids:
            return False
        checked_any = False
        for student_id in student_ids:
            agent = self.agents.get(student_id)
            if agent is None or agent.state is not AgentState.TO_TABLE:
                continue
            if agent.assigned_table_approach_cell is None or agent.table_index is None:
                continue
            checked_any = True
            target = agent.assigned_table_approach_cell
            occupant = next(
                (
                    other.student_id
                    for other in self.agents.values()
                    if other.student_id != agent.student_id
                    and other.cell == target
                    and other.state not in {AgentState.SEATED, AgentState.EXITED}
                ),
                None,
            )
            blocked_by_other = occupant is not None
            if agent.stuck_ticks < self.local_repair_after_stuck_ticks and not blocked_by_other:
                continue
            if blocked_by_other and self._reassign_table_approach_slot(agent):
                continue
            plan = self._plan_local_repair_with_reservations(
                center=target,
                agent_ids=self._local_repair_region(target, self.local_repair_radius),
                horizon=self.local_repair_horizon,
                radius=self.local_repair_radius,
            )
            if plan and student_id in plan:
                continue
            if self._reassign_table_approach_slot(agent):
                continue
            agent.table_repair_failures += 1
            if agent.table_repair_failures < 2:
                continue
            return False
        return checked_any

    def _reassign_table_approach_slot(self, agent: PedestrianAgent) -> bool:
        if agent.table_index is None:
            return False
        candidates = sorted(self.grid.table_approach_cells.get(agent.table_index, set()))
        if not candidates:
            return False
        party_member_ids = {
            other.student_id
            for other in self.agents.values()
            if other.party_id == agent.party_id and other.student_id != agent.student_id and other.state is AgentState.TO_TABLE
        }
        party_slots = {
            self.agents[student_id].assigned_table_approach_cell
            for student_id in party_member_ids
            if student_id in self.agents
        }
        occupied = {
            other.cell
            for other in self.agents.values()
            if other.student_id != agent.student_id
            and other.state not in {AgentState.SEATED, AgentState.EXITED}
        }
        available = [
            cell
            for cell in candidates
            if cell != agent.assigned_table_approach_cell
            and cell not in party_slots
            and cell not in occupied
        ]
        if not available:
            return False
        target = min(
            available,
            key=lambda cell: (
                abs(agent.cell[0] - cell[0]) + abs(agent.cell[1] - cell[1]),
                cell[1],
                cell[0],
            ),
        )
        agent.assigned_table_approach_cell = target
        agent.target_cells = {target}
        agent.table_slot_reassignments += 1
        agent.table_repair_failures = 0
        self._refresh_table_approach_owner_index()
        return True

    def _is_near_target_cells(self, agent: PedestrianAgent, max_distance: int = 1) -> bool:
        if not agent.target_cells:
            return False
        return any(
            abs(agent.cell[0] - target[0]) + abs(agent.cell[1] - target[1]) <= max_distance
            for target in agent.target_cells
        )

    def _is_walkable_cell(self, cell: Cell) -> bool:
        return cell in self.in_bounds_cells and cell not in self.grid.blocked_cells

    def can_agent_enter_cell(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if cell == agent.cell:
            return True
        if not self._is_walkable_cell(cell):
            return False
        if not self._agent_can_use_window_queue_side(agent, cell):
            return False
        if self._is_reserved_service_area(cell) and not self._agent_can_use_service_area(agent, cell):
            return False
        queue_info = self._queue_slot_info(cell)
        if queue_info is not None:
            queue_window, queue_slot_index, queue_owner = queue_info
            if queue_owner is not None and queue_owner != agent.student_id:
                if (
                    not self._agent_can_pass_through_queue_window(agent, queue_window)
                    and not self._agent_can_use_tail_slot(agent, queue_window, queue_slot_index)
                    and not self._agent_can_use_unoccupied_same_queue_slot(
                        agent,
                        queue_window,
                        queue_slot_index,
                        queue_owner,
                        cell,
                    )
                ):
                    return False
            if (
                queue_owner is None
                and self._queue_slot_window_has_assignments(cell)
                and cell not in agent.target_cells
                and not self._agent_can_use_tail_slot(agent, queue_window, queue_slot_index)
                and not self._agent_can_pass_through_queue_window(agent, queue_window)
                and not self._agent_can_use_unowned_queue_slot(agent)
            ):
                return False
        table_owner = self._table_approach_owner(cell)
        if table_owner is not None and table_owner != agent.student_id:
            return False
        return True

    def _can_estimate_forward_step(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if not self._is_walkable_cell(cell):
            return False
        if not self._agent_can_use_window_queue_side(agent, cell):
            return False
        if self._is_reserved_service_area(cell) and not self._agent_can_use_service_area(agent, cell):
            return False
        return True

    def _is_reserved_service_area(self, cell: Cell) -> bool:
        return cell in self.reserved_service_cells

    def _reserved_service_area(self, window_index: int) -> set[Cell]:
        return self.reserved_service_area_by_window.get(window_index, set())

    def _build_reserved_service_area(self, window_index: int) -> set[Cell]:
        service = self.grid.service_cells.get(window_index)
        if service is None:
            return set()
        reserved = {service}
        queue_slots = self.grid.queue_cells_by_window.get(window_index, [])
        if queue_slots:
            reserved.add(queue_slots[0])
        return reserved

    def _agent_can_use_service_area(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if agent.state is AgentState.SERVICE and agent.target_id is not None and self.grid.service_cells.get(agent.target_id) == cell:
            return True
        window_index = self.service_window_by_cell.get(cell)
        if window_index is not None:
            return self._physical_queue_head_id(window_index) == agent.student_id
        queue_owner = self._queue_slot_owner(cell)
        queue_info = self._queue_slot_info(cell)
        if queue_info is not None:
            queue_window, _queue_slot_index, _queue_owner = queue_info
            return (
                queue_owner is None
                or queue_owner == agent.student_id
                or self._agent_can_pass_through_queue_window(agent, queue_window)
            )
        return queue_owner is None or queue_owner == agent.student_id

    def _queue_slot_owner(self, cell: Cell) -> int | None:
        return self.queue_slot_owner_lookup.get(cell)

    def _queue_slot_info(self, cell: Cell) -> tuple[int, int, int | None] | None:
        info = self.queue_slot_lookup.get(cell)
        if info is None:
            return None
        window_index, slot_index = info
        return window_index, slot_index, self.queue_slot_owner_lookup.get(cell)

    def _agent_can_use_tail_slot(self, agent: PedestrianAgent, window_index: int, slot_index: int) -> bool:
        return (
            agent.state in {AgentState.TO_WINDOW, AgentState.QUEUEING}
            and agent.desired_window_index == window_index
            and agent.assigned_queue_slot_index is not None
            and slot_index >= agent.assigned_queue_slot_index
        )

    def _agent_can_use_unoccupied_same_queue_slot(
        self,
        agent: PedestrianAgent,
        window_index: int,
        slot_index: int,
        queue_owner: int,
        cell: Cell,
    ) -> bool:
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return False
        if agent.desired_window_index != window_index:
            return False
        if agent.student_id not in self.window_queues.get(window_index, []):
            return False
        if agent.assigned_queue_slot_index is None or slot_index >= agent.assigned_queue_slot_index:
            return False
        if slot_index <= 0:
            return False
        owner = self.agents.get(queue_owner)
        return owner is None or owner.cell != cell

    def _agent_can_use_unowned_queue_slot(self, agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _is_queue_slot(self, cell: Cell) -> bool:
        return cell in self.queue_slot_lookup

    def _queue_slot_window_has_assignments(self, cell: Cell) -> bool:
        info = self.queue_slot_lookup.get(cell)
        if info is None:
            return False
        window_index, _slot_index = info
        return window_index in self.queue_windows_with_assignments

    def _queue_slot_assignments(self, window_index: int) -> dict[int, int]:
        cached = self.queue_slot_assignments_by_window.get(window_index)
        if cached is not None:
            return dict(cached)
        return self._build_queue_slot_assignments(window_index)

    def _build_queue_slot_assignments(self, window_index: int) -> dict[int, int]:
        assigned: dict[int, int] = {}
        for position, student_id in enumerate(self.window_queues.get(window_index, [])):
            assigned[position] = student_id
        offset = len(self.window_queues.get(window_index, []))
        for position, student_id in enumerate(self.window_walkers.get(window_index, [])):
            assigned[offset + position] = student_id
        return assigned

    def _refresh_movement_indexes(self) -> None:
        self._refresh_queue_assignment_indexes()
        self._refresh_table_approach_owner_index()

    def _refresh_queue_assignment_indexes(self) -> None:
        assignments_by_window: dict[int, dict[int, int]] = {}
        owner_lookup: dict[Cell, int] = {}
        windows_with_assignments: set[int] = set()
        queue_member_sets: dict[int, set[int]] = {}
        for window_index in sorted(set(self.window_queues) | set(self.window_walkers)):
            queue_member_sets[window_index] = set(self.window_queues.get(window_index, []))
            assigned = self._build_queue_slot_assignments(window_index)
            if not assigned:
                continue
            assignments_by_window[window_index] = assigned
            windows_with_assignments.add(window_index)
            queue_cells = self.grid.queue_cells_by_window.get(window_index, [])
            for slot_index, student_id in assigned.items():
                if 0 <= slot_index < len(queue_cells):
                    owner_lookup[queue_cells[slot_index]] = student_id
        self.queue_slot_assignments_by_window = assignments_by_window
        self.queue_slot_owner_lookup = owner_lookup
        self.queue_windows_with_assignments = windows_with_assignments
        self.window_queue_member_sets = queue_member_sets

    def _refresh_table_approach_owner_index(self) -> None:
        owner_lookup: dict[Cell, int] = {}
        for agent in self.agents.values():
            cell = agent.assigned_table_approach_cell
            if cell is None or agent.state is not AgentState.TO_TABLE:
                continue
            owner_lookup[cell] = agent.student_id
        self.table_approach_owner_lookup = owner_lookup

    def _physical_queue_head_id(self, window_index: int) -> int | None:
        queue = self.window_queues.get(window_index, [])
        return queue[0] if queue else None

    def _table_approach_owner(self, cell: Cell) -> int | None:
        owner = self.table_approach_owner_lookup.get(cell)
        if owner is None:
            return None
        agent = self.agents.get(owner)
        if agent is None or agent.assigned_table_approach_cell != cell or agent.state is not AgentState.TO_TABLE:
            self.table_approach_owner_lookup.pop(cell, None)
            return None
        return owner

    def _intended_move(
        self,
        agent: PedestrianAgent,
        occupied_cells: set[Cell],
        density: DensityField | None = None,
        density_radius: int | None = None,
    ) -> tuple[Cell, float]:
        if not agent.target_cells:
            return agent.cell, 0.0
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        resolved_density_radius = max(0, int(
            density_radius if density_radius is not None else self.personal_space_radius_cells
        ))
        if density is None:
            density = DensityField.from_occupied_cells(occupied_cells, self.grid, radius=resolved_density_radius)
        static_field = self._static_field(agent.target_cells)
        movement_field = self._movement_cost_field(agent, density, resolved_density_radius, static_field)
        current_cell = agent.cell
        can_enter = self.can_agent_enter_cell
        candidate_cost = self._candidate_cost

        compaction_move = self._queue_compaction_move(agent, occupied_cells)
        if compaction_move is not None:
            return compaction_move, -100.0

        best_cell: Cell | None = None
        best_cost = float("inf")
        has_candidate = False

        if self._is_walkable_cell(current_cell) and can_enter(agent, current_cell):
            has_candidate = True
            cost = candidate_cost(current_cell, agent, density, resolved_density_radius, movement_field)
            if math.isfinite(cost):
                best_cell = current_cell
                best_cost = cost

        for cell in neighbor_map.get(current_cell, []):
            if cell in occupied_cells or not can_enter(agent, cell):
                continue
            has_candidate = True
            cost = candidate_cost(cell, agent, density, resolved_density_radius, movement_field)
            if not math.isfinite(cost):
                continue
            if best_cell is None or cost < best_cost or (
                math.isclose(cost, best_cost, rel_tol=0.0, abs_tol=1e-9)
                and self._target_alignment_tiebreak(agent, cell)
                < self._target_alignment_tiebreak(agent, best_cell)
            ):
                best_cell = cell
                best_cost = cost

        if not has_candidate:
            return current_cell, 0.0
        if best_cell is None:
            return agent.cell, float("inf")
        if self._should_try_congestion_route(
            agent,
            best_cell,
            density,
            resolved_density_radius,
        ):
            route_move = self._congestion_aware_route_move(
                agent,
                occupied_cells=occupied_cells,
                density=density,
                density_radius=resolved_density_radius,
                static_field=movement_field,
            )
            if route_move is not None:
                route_cell, route_cost = route_move
                if route_cost < best_cost:
                    return route_cell, route_cost
        return best_cell, best_cost

    def _should_try_congestion_route(
        self,
        agent: PedestrianAgent,
        best_cell: Cell,
        density: DensityField,
        density_radius: int,
    ) -> bool:
        if agent.state is not AgentState.TO_WINDOW or agent.desired_window_index is None:
            return False
        return False

    def _queue_compaction_move(self, agent: PedestrianAgent, occupied_cells: set[Cell]) -> Cell | None:
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return None
        window_index = agent.desired_window_index
        assigned_index = agent.assigned_queue_slot_index
        if window_index is None or assigned_index is None:
            return None
        if agent.student_id not in self.window_queues.get(window_index, []):
            return None
        queue_info = self._queue_slot_info(agent.cell)
        if queue_info is None:
            return None
        queue_window, current_slot_index, _queue_owner = queue_info
        if queue_window != window_index or current_slot_index <= assigned_index:
            return None
        queue_slots = self.grid.queue_cells_by_window.get(window_index, [])
        next_slot_index = current_slot_index - 1
        if next_slot_index < 0 or next_slot_index >= len(queue_slots):
            return None
        next_slot = queue_slots[next_slot_index]
        if next_slot in occupied_cells:
            return None
        if any(
            other.student_id != agent.student_id
            and other.cell == next_slot
            and self._occupies_walkable_cell(other)
            for other in self.agents.values()
        ):
            return None
        if not self.can_agent_enter_cell(agent, next_slot):
            return None
        return next_slot

    def _movement_cost_field(
        self,
        agent: PedestrianAgent,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
    ) -> dict[Cell, float]:
        dynamic_field = self._dynamic_cost_field_for_agent(agent, density, density_radius, static_field)
        if dynamic_field is None:
            return static_field
        if agent.cell in dynamic_field:
            return dynamic_field
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        if any(cell in dynamic_field for cell in neighbor_map.get(agent.cell, [])):
            return dynamic_field
        return static_field

    def _dynamic_cost_field_for_agent(
        self,
        agent: PedestrianAgent,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
    ) -> dict[Cell, float] | None:
        if agent.state is not AgentState.TO_WINDOW:
            return None
        if agent.desired_window_index is None or not agent.target_cells:
            return None
        if self.dynamic_route_max_fields_per_step <= 0:
            return None
        if not self._route_has_global_congestion(agent, density, density_radius, static_field):
            return None
        targets = tuple(sorted(
            cell
            for cell in agent.target_cells
            if self._is_walkable_cell(cell) and self.can_agent_enter_cell(agent, cell)
        ))
        if not targets:
            return None
        search_bounds = self._dynamic_route_search_bounds(agent.cell, targets)
        key = (
            "to_window",
            agent.desired_window_index,
            agent.assigned_queue_slot_index,
            targets,
            search_bounds,
            id(density),
            density_radius,
        )
        cached = self.dynamic_cost_fields.get(key)
        if cached is not None:
            return cached
        if len(self.dynamic_cost_fields) >= self.dynamic_route_max_fields_per_step:
            return None

        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        distances: dict[Cell, float] = {cell: 0.0 for cell in targets}
        frontier: list[tuple[float, Cell]] = []
        for target in targets:
            heappush(frontier, (0.0, target))

        while frontier:
            current_cost, current = heappop(frontier)
            if current_cost > distances.get(current, float("inf")):
                continue
            step_cost = self._route_step_cost(agent, current, density, density_radius)
            for neighbor in neighbor_map.get(current, []):
                if not self._cell_in_bounds(neighbor, search_bounds):
                    continue
                if not self._is_walkable_cell(neighbor):
                    continue
                if not self.can_agent_enter_cell(agent, neighbor):
                    continue
                next_cost = current_cost + step_cost
                if next_cost >= distances.get(neighbor, float("inf")):
                    continue
                distances[neighbor] = next_cost
                heappush(frontier, (next_cost, neighbor))

        self.dynamic_cost_fields[key] = distances
        return distances

    def _dynamic_route_search_bounds(
        self,
        start: Cell,
        targets: tuple[Cell, ...],
    ) -> tuple[int, int, int, int]:
        margin = self.dynamic_route_search_margin
        cols = [start[0], *(cell[0] for cell in targets)]
        rows = [start[1], *(cell[1] for cell in targets)]
        min_col = max(0, min(cols) - margin)
        max_col = min(self.grid.cols - 1, max(cols) + margin)
        min_row = max(0, min(rows) - margin)
        max_row = min(self.grid.rows - 1, max(rows) + margin)
        return min_col, max_col, min_row, max_row

    @staticmethod
    def _cell_in_bounds(cell: Cell, bounds: tuple[int, int, int, int]) -> bool:
        min_col, max_col, min_row, max_row = bounds
        return min_col <= cell[0] <= max_col and min_row <= cell[1] <= max_row

    def _route_has_global_congestion(
        self,
        agent: PedestrianAgent,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
    ) -> bool:
        current = agent.cell
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        max_steps = max(self.local_repair_radius * 4, 20)
        congestion_score = 0.0
        for _step in range(max_steps):
            if current in agent.target_cells:
                return False
            current_distance = static_field.get(current, float("inf"))
            if not math.isfinite(current_distance):
                return False
            candidates = [
                neighbor
                for neighbor in neighbor_map.get(current, [])
                if self.can_agent_enter_cell(agent, neighbor)
                and static_field.get(neighbor, float("inf")) < current_distance
            ]
            if not candidates:
                return False
            current = min(
                candidates,
                key=lambda candidate: (
                    static_field.get(candidate, float("inf")),
                    self._target_alignment_tiebreak(agent, candidate),
                ),
            )
            if self._queue_lane_avoidance_penalty(agent, current) > 0:
                congestion_score += 2.0
            congestion_score += float(self._route_cell_density(agent, current, density, density_radius))
            if congestion_score >= self.dynamic_route_trigger_threshold:
                return True
        return False

    def _congestion_aware_route_move(
        self,
        agent: PedestrianAgent,
        occupied_cells: set[Cell],
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
    ) -> tuple[Cell, float] | None:
        if agent.state is not AgentState.TO_WINDOW:
            return None
        if agent.desired_window_index is None:
            return None
        start = agent.cell
        start_distance = static_field.get(start, float("inf"))
        if not math.isfinite(start_distance):
            return None

        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        is_stuck = agent.stuck_ticks >= self.local_repair_after_stuck_ticks
        max_steps = max(6, self.local_repair_horizon * 2) if is_stuck else 3
        radius = max(6, self.local_repair_radius * 2) if is_stuck else 4
        if (
            not is_stuck
            and not self._route_has_local_congestion(
                agent,
                density=density,
                density_radius=density_radius,
                static_field=static_field,
                start_distance=start_distance,
                neighbor_map=neighbor_map,
            )
        ):
            return None

        frontier: list[tuple[float, float, int, Cell, Cell | None]] = []
        heappush(frontier, (start_distance, 0.0, 0, start, None))
        best_seen: dict[Cell, tuple[float, int]] = {start: (0.0, 0)}
        best_move: tuple[Cell, float] | None = None
        best_score: tuple[float, int, float, float, int, int, int, int] | None = None
        min_evaluation_steps = min(max_steps, max(1, int(math.ceil(start_distance))))

        while frontier:
            _priority, route_cost, steps, cell, first_step = heappop(frontier)
            seen_cost, seen_steps = best_seen.get(cell, (float("inf"), 10_000))
            if route_cost > seen_cost and steps >= seen_steps:
                continue

            target_distance = static_field.get(cell, float("inf"))
            if (
                first_step is not None
                and math.isfinite(target_distance)
                and (steps >= min_evaluation_steps or cell in agent.target_cells)
            ):
                total = route_cost + self.floor_static_weight * target_distance
                first_step_density = self._route_cell_density(agent, first_step, density, density_radius)
                score = (
                    total,
                    first_step_density,
                    target_distance,
                    route_cost,
                    *self._target_alignment_tiebreak(agent, cell),
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_move = (first_step, total)

            if steps >= max_steps:
                continue

            for candidate in neighbor_map.get(cell, []):
                if max(abs(candidate[0] - start[0]), abs(candidate[1] - start[1])) > radius:
                    continue
                if first_step is None and self._is_non_progress_backtrack(agent, candidate, static_field, start_distance):
                    continue
                if candidate in occupied_cells:
                    continue
                if not self.can_agent_enter_cell(agent, candidate):
                    continue
                target_distance = static_field.get(candidate, float("inf"))
                if not math.isfinite(target_distance):
                    continue
                step_cost = self._route_step_cost(agent, candidate, density, density_radius)
                step_cost += self._recent_non_progress_penalty(
                    agent,
                    candidate,
                    static_field,
                    current_distance=static_field.get(cell, float("inf")),
                )
                next_cost = route_cost + step_cost
                next_steps = steps + 1
                previous = best_seen.get(candidate)
                if previous is not None and previous <= (next_cost, next_steps):
                    continue
                best_seen[candidate] = (next_cost, next_steps)
                next_first_step = candidate if first_step is None else first_step
                priority = next_cost + self.floor_static_weight * target_distance
                heappush(frontier, (priority, next_cost, next_steps, candidate, next_first_step))

        return best_move

    def _route_has_local_congestion(
        self,
        agent: PedestrianAgent,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
        start_distance: float,
        neighbor_map: dict[Cell, list[Cell]],
    ) -> bool:
        start = agent.cell
        trigger_density = max(2, min(3, self.congestion_density_threshold_floor or 2))
        for first_step in neighbor_map.get(start, []):
            first_distance = static_field.get(first_step, float("inf"))
            if not math.isfinite(first_distance) or first_distance > start_distance:
                continue
            if self._queue_lane_avoidance_penalty(agent, first_step) > 0:
                return True
            if self._route_cell_density(agent, first_step, density, density_radius) >= trigger_density:
                return True
            for second_step in neighbor_map.get(first_step, []):
                second_distance = static_field.get(second_step, float("inf"))
                if not math.isfinite(second_distance) or second_distance > first_distance:
                    continue
                if self._queue_lane_avoidance_penalty(agent, second_step) > 0:
                    return True
                if self._route_cell_density(agent, second_step, density, density_radius) >= trigger_density:
                    return True
        return False

    def _route_step_cost(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        density: DensityField,
        density_radius: int,
    ) -> float:
        local_density = self._route_cell_density(agent, cell, density, density_radius)
        cost = 1.0 + self.floor_density_weight * float(local_density)
        cost += self.floor_wall_weight * self._wall_penalty(cell)
        cost += self._queue_lane_avoidance_penalty(agent, cell)
        cost -= self._queue_lane_entry_bonus(agent, cell)
        return max(0.05, cost)

    def _route_cell_density(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        density: DensityField,
        density_radius: int,
    ) -> int:
        local_density = density.density(cell)
        if max(abs(cell[0] - agent.cell[0]), abs(cell[1] - agent.cell[1])) <= density_radius:
            local_density -= 1
        return max(0, local_density)

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

    def _resolve_edge_swaps(self, movable: list[PedestrianAgent], planned_targets: dict[int, Cell]) -> None:
        by_cell = {agent.cell: agent for agent in movable}
        checked: set[tuple[int, int]] = set()
        for first in movable:
            first_target = planned_targets.get(first.student_id, first.cell)
            if first_target == first.cell:
                continue
            second = by_cell.get(first_target)
            if second is None or second.student_id == first.student_id:
                continue
            pair = tuple(sorted((first.student_id, second.student_id)))
            if pair in checked:
                continue
            checked.add(pair)
            second_target = planned_targets.get(second.student_id, second.cell)
            if second_target != first.cell:
                continue
            loser = max((first, second), key=lambda agent: (self._movement_conflict_priority(agent), agent.student_id))
            planned_targets[loser.student_id] = loser.cell
            self._record_movement_conflict(loser, [(first, 0.0), (second, 0.0)])

    def _apply_local_repair_moves(
        self,
        movable: list[PedestrianAgent],
        planned_targets: dict[int, Cell],
        occupied_by: dict[Cell, PedestrianAgent],
    ) -> None:
        if getattr(self, "_repair_used_this_tick", False):
            return
        triggers = [
            agent
            for agent in movable
            if agent.stuck_ticks >= self.local_repair_after_stuck_ticks
            and agent.state in {
                AgentState.ENTERING,
                AgentState.TO_WINDOW,
                AgentState.QUEUEING,
                AgentState.TO_TABLE,
                AgentState.TO_EXIT,
            }
        ]
        for trigger in sorted(triggers, key=lambda agent: self._agent_repair_priority(agent))[: self.local_repair_max_attempts]:
            center = self._repair_center_for_agent(trigger)
            region_ids = self._local_repair_region(center, radius=self.local_repair_radius)
            if trigger.student_id not in region_ids:
                region_ids.append(trigger.student_id)
            region_ids = self._select_repair_agent_ids(center, region_ids, trigger.student_id)
            plan = self._plan_local_repair_with_reservations(
                center=center,
                agent_ids=region_ids,
                horizon=self.local_repair_horizon,
                radius=self.local_repair_radius,
            )
            if not plan:
                continue
            occupied_after: set[Cell] = set()
            applied = False
            for student_id, path in plan.items():
                agent = self.agents.get(student_id)
                if agent is None or not path:
                    continue
                target = path[0]
                if self._is_recent_non_progress_move(agent, target):
                    continue
                if target in occupied_after:
                    continue
                occupant = occupied_by.get(target)
                if occupant is not None and occupant.student_id not in plan:
                    continue
                if not self.can_agent_enter_cell(agent, target):
                    continue
                planned_targets[student_id] = target
                occupied_after.add(target)
                applied = True
            if applied:
                self._repair_used_this_tick = True
                return
            self._repair_used_this_tick = True

    def _repair_center_for_agent(self, agent: PedestrianAgent) -> Cell:
        if agent.target_cells:
            target = min(
                agent.target_cells,
                key=lambda cell: (abs(agent.cell[0] - cell[0]) + abs(agent.cell[1] - cell[1]), cell[1], cell[0]),
            )
            if abs(agent.cell[0] - target[0]) + abs(agent.cell[1] - target[1]) <= self.local_repair_radius:
                return target
        return agent.cell

    def _select_repair_agent_ids(self, center: Cell, agent_ids: list[int], trigger_id: int) -> list[int]:
        unique_ids = list(dict.fromkeys(agent_ids))
        ordered = sorted(
            unique_ids,
            key=lambda student_id: (
                0 if student_id == trigger_id else 1,
                abs(self.agents[student_id].cell[0] - center[0]) + abs(self.agents[student_id].cell[1] - center[1])
                if student_id in self.agents
                else 10_000,
                self._agent_repair_priority(self.agents[student_id]) if student_id in self.agents else (9, 0, student_id),
                student_id,
            ),
        )
        return ordered[: self.local_repair_max_agents]

    def _local_repair_region(self, center: Cell, radius: int) -> list[int]:
        radius = max(1, int(radius))
        agent_ids = [
            agent.student_id
            for agent in self.agents.values()
            if agent.state in {
                AgentState.ENTERING,
                AgentState.TO_WINDOW,
                AgentState.QUEUEING,
                AgentState.WAITING_GROUP,
                AgentState.TO_TABLE,
                AgentState.TO_EXIT,
            }
            and max(abs(agent.cell[0] - center[0]), abs(agent.cell[1] - center[1])) <= radius
        ]
        return sorted(agent_ids)

    def _plan_local_repair_with_reservations(
        self,
        center: Cell,
        agent_ids: list[int],
        horizon: int = 4,
        radius: int = 5,
    ) -> dict[int, list[Cell]]:
        self._refresh_movement_indexes()
        horizon = max(1, int(horizon))
        radius = max(1, int(radius))
        agents = [
            self.agents[student_id]
            for student_id in dict.fromkeys(agent_ids)
            if student_id in self.agents
            and self.agents[student_id].state
            in {
                AgentState.ENTERING,
                AgentState.TO_WINDOW,
                AgentState.QUEUEING,
                AgentState.WAITING_GROUP,
                AgentState.TO_TABLE,
                AgentState.TO_EXIT,
            }
        ]
        if not agents:
            return {}
        region = {
            (col, row)
            for col in range(center[0] - radius, center[0] + radius + 1)
            for row in range(center[1] - radius, center[1] + radius + 1)
            if max(abs(col - center[0]), abs(row - center[1])) <= radius
            and self._is_walkable_cell((col, row))
        }
        if not region:
            return {}
        reservation: dict[tuple[int, Cell], int] = {
            (0, agent.cell): agent.student_id
            for agent in agents
        }
        reserved_edges: set[tuple[int, Cell, Cell]] = set()
        plan: dict[int, list[Cell]] = {}
        for agent in sorted(agents, key=self._agent_repair_priority):
            path = self._plan_single_agent_with_reservations(
                agent,
                region=region,
                horizon=horizon,
                reservation=reservation,
                reserved_edges=reserved_edges,
            )
            if not path:
                path = self._fallback_repair_path(
                    agent,
                    region=region,
                    horizon=horizon,
                    reservation=reservation,
                    reserved_edges=reserved_edges,
                )
            if not path:
                continue
            plan[agent.student_id] = path
            previous = agent.cell
            for time_index, cell in enumerate(path, start=1):
                reservation[(time_index, cell)] = agent.student_id
                reserved_edges.add((time_index, previous, cell))
                previous = cell
        return plan

    def _plan_single_agent_with_reservations(
        self,
        agent: PedestrianAgent,
        region: set[Cell],
        horizon: int,
        reservation: dict[tuple[int, Cell], int],
        reserved_edges: set[tuple[int, Cell, Cell]],
    ) -> list[Cell] | None:
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        start = agent.cell
        frontier: deque[tuple[Cell, int, list[Cell]]] = deque([(start, 0, [])])
        seen = {(start, 0)}
        best_path: list[Cell] | None = None
        best_score: tuple[float, int, int, int] | None = None
        while frontier:
            current, time_index, path = frontier.popleft()
            score = self._repair_path_score(agent, path)
            if (
                path
                and time_index >= horizon
                and (best_path is None or best_score is None or score < best_score)
            ):
                best_path = path
                best_score = score
            if time_index >= horizon:
                continue
            candidates = [current, *neighbor_map.get(current, [])]
            for candidate in candidates:
                next_time = time_index + 1
                if candidate not in region:
                    continue
                if not self._can_agent_reserve_repair_cell(agent, candidate):
                    continue
                occupant = reservation.get((next_time, candidate))
                if occupant is not None and occupant != agent.student_id:
                    continue
                if (next_time, candidate, current) in reserved_edges:
                    continue
                state = (candidate, next_time)
                if state in seen:
                    continue
                seen.add(state)
                frontier.append((candidate, next_time, [*path, candidate]))
        if best_path is None:
            return None
        return best_path

    def _fallback_repair_path(
        self,
        agent: PedestrianAgent,
        region: set[Cell],
        horizon: int,
        reservation: dict[tuple[int, Cell], int],
        reserved_edges: set[tuple[int, Cell, Cell]],
    ) -> list[Cell] | None:
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        candidates = [agent.cell, *neighbor_map.get(agent.cell, [])]
        ordered = sorted(
            (cell for cell in candidates if cell in region),
            key=lambda cell: self._repair_path_score(agent, [cell]),
        )
        for cell in ordered:
            path = [cell for _ in range(horizon)]
            if self._repair_path_is_reservation_safe(
                agent,
                path,
                region=region,
                reservation=reservation,
                reserved_edges=reserved_edges,
            ):
                return path
        return None

    def _repair_path_is_reservation_safe(
        self,
        agent: PedestrianAgent,
        path: list[Cell],
        region: set[Cell],
        reservation: dict[tuple[int, Cell], int],
        reserved_edges: set[tuple[int, Cell, Cell]],
    ) -> bool:
        previous = agent.cell
        for time_index, cell in enumerate(path, start=1):
            if cell not in region:
                return False
            if not self._can_agent_reserve_repair_cell(agent, cell):
                return False
            occupant = reservation.get((time_index, cell))
            if occupant is not None and occupant != agent.student_id:
                return False
            if (time_index, cell, previous) in reserved_edges:
                return False
            previous = cell
        return True

    def _can_agent_reserve_repair_cell(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if self._agent_should_hold_target_cell(agent) and cell != agent.cell:
            return False
        if not self._is_walkable_cell(cell):
            return False
        if not self._agent_can_use_window_queue_side(agent, cell):
            return False
        if self._is_reserved_service_area(cell) and not self._agent_can_use_service_area(agent, cell):
            return False
        queue_info = self._queue_slot_info(cell)
        if queue_info is not None:
            queue_window, queue_slot_index, queue_owner = queue_info
            if queue_owner is not None and queue_owner != agent.student_id:
                if (
                    not self._agent_can_pass_through_queue_window(agent, queue_window)
                    and not self._agent_can_use_tail_slot(agent, queue_window, queue_slot_index)
                    and not self._agent_can_use_unoccupied_same_queue_slot(
                        agent,
                        queue_window,
                        queue_slot_index,
                        queue_owner,
                        cell,
                    )
                ):
                    return False
            if (
                queue_owner is None
                and self._queue_slot_window_has_assignments(cell)
                and cell not in agent.target_cells
                and not self._agent_can_use_tail_slot(agent, queue_window, queue_slot_index)
                and not self._agent_can_pass_through_queue_window(agent, queue_window)
                and not self._agent_can_use_unowned_queue_slot(agent)
            ):
                return False
        table_owner = self._table_approach_owner(cell)
        if table_owner is not None and table_owner != agent.student_id:
            return False
        return True

    def _agent_can_use_window_queue_side(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return True
        if agent.desired_window_index is None:
            return True
        constraint = self.queue_side_constraints.get(agent.desired_window_index)
        if constraint is None:
            return True
        service, normal = constraint
        forward = (cell[0] - service[0]) * normal[0] + (cell[1] - service[1]) * normal[1]
        return forward >= 0

    def _repair_path_score(self, agent: PedestrianAgent, path: list[Cell]) -> tuple[float, int, int, int, int, int, int, int]:
        cell = path[-1] if path else agent.cell
        target_distance = 0.0
        field: dict[Cell, float] | None = None
        if agent.target_cells:
            field = self._static_field(agent.target_cells)
            target_distance = field.get(cell, 10_000.0)
            if not math.isfinite(target_distance):
                target_distance = 10_000.0
        wait_penalty = sum(1 for step in path if step == agent.cell)
        repeat_penalty = len([agent.cell, *path]) - len(set([agent.cell, *path]))
        recent_penalty = 0.0
        if field is not None:
            previous = agent.cell
            for step in path:
                recent_penalty += self._recent_non_progress_penalty(
                    agent,
                    step,
                    field,
                    current_distance=field.get(previous, float("inf")),
                )
                previous = step
        return (
            target_distance,
            int(round(recent_penalty * 10)),
            repeat_penalty,
            wait_penalty,
            *self._target_alignment_tiebreak(agent, cell),
        )

    def _target_alignment_tiebreak(self, agent: PedestrianAgent, cell: Cell) -> tuple[int, int, int, int]:
        if not agent.target_cells:
            return (0, 0, cell[1], cell[0])
        return min(
            (
                max(abs(cell[0] - target[0]), abs(cell[1] - target[1])),
                abs(cell[0] - target[0]) + abs(cell[1] - target[1]),
                cell[1],
                cell[0],
            )
            for target in agent.target_cells
        )

    def _agent_repair_priority(self, agent: PedestrianAgent) -> tuple[int, int, int]:
        if agent.state is AgentState.QUEUEING and agent.desired_window_index is not None:
            if self._physical_queue_head_id(agent.desired_window_index) == agent.student_id:
                return (0, -agent.stuck_ticks, agent.student_id)
        if agent.state in {AgentState.TO_TABLE, AgentState.TO_EXIT} and agent.stuck_ticks >= self.local_repair_after_stuck_ticks:
            return (1, -agent.stuck_ticks, agent.student_id)
        if agent.state is AgentState.TO_WINDOW:
            return (2, -agent.stuck_ticks, agent.student_id)
        if agent.state is AgentState.QUEUEING:
            return (3, -agent.stuck_ticks, agent.student_id)
        if agent.state is AgentState.WAITING_GROUP:
            return (5, -agent.stuck_ticks, agent.student_id)
        return (4, -agent.stuck_ticks, agent.student_id)

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
        if self._agent_should_hold_target_cell(passer):
            return None
        if passer.stuck_ticks < self.floor_borrow_after_stuck_ticks:
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
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        for cell in neighbor_map.get(passer.cell, []):
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
            if self._is_recent_non_progress_move(blocker, cell):
                continue
            if cell in reserved_targets and cell != passer.cell:
                continue
            occupant = occupied_by.get(cell)
            if occupant is not None and occupant.student_id != passer.student_id:
                continue
            if not self.can_agent_enter_cell(blocker, cell):
                continue
            valid.append((order, self._yield_candidate_cost(cell, blocker, density, density_radius), cell))
        if not valid:
            return None
        return min(valid, key=lambda item: (item[1], item[0], item[2][1], item[2][0]))[2]

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
        for cell in self.neighbors4.get(blocker.cell, []):
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
        return target_distance + density.penalty(
            cell,
            threshold=self.congestion_density_threshold,
            excluded_cell=blocker.cell,
            radius=density_radius,
        )

    def _can_yield_for_borrow(self, agent: PedestrianAgent) -> bool:
        if self._agent_should_hold_target_cell(agent):
            return False
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _movement_conflict_priority(self, agent: PedestrianAgent) -> int:
        if agent.state is AgentState.QUEUEING and agent.desired_window_index is not None:
            if self._physical_queue_head_id(agent.desired_window_index) == agent.student_id:
                return -2
        if agent.state is AgentState.TO_TABLE and agent.stuck_ticks >= self.floor_borrow_after_stuck_ticks:
            return -1
        return 0

    def _record_movement_conflict(
        self,
        loser: PedestrianAgent,
        contenders: list[tuple[PedestrianAgent, float]],
    ) -> None:
        if not self._counts_as_movement_conflict_actor(loser):
            return
        moving_contenders = sum(
            1
            for contender, _cost in contenders
            if self._counts_as_movement_conflict_actor(contender)
        )
        if moving_contenders >= 2:
            loser.conflict_count += 1

    @staticmethod
    def _counts_as_movement_conflict_actor(agent: PedestrianAgent) -> bool:
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _candidate_cost(
        self,
        cell: Cell,
        agent: PedestrianAgent,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float],
    ) -> float:
        static_distance = static_field.get(cell, float("inf"))
        if not math.isfinite(static_distance):
            return float("inf")
        cost = self.floor_static_weight * static_distance
        local_density = density.densities.get(cell, 0)
        if density_radius < 0:
            density_radius = 0
        column_delta = agent.cell[0] - cell[0]
        if column_delta < 0:
            column_delta = -column_delta
        row_delta = agent.cell[1] - cell[1]
        if row_delta < 0:
            row_delta = -row_delta
        if (column_delta if column_delta >= row_delta else row_delta) <= density_radius:
            local_density -= 1
        if local_density > 0:
            density_penalty = local_density - self.congestion_density_threshold_floor + 1
            if density_penalty > 0:
                cost += self.floor_density_weight * float(density_penalty)
        cost += self._forward_congestion_penalty(agent, cell, density, density_radius, static_field)
        cost += self._queue_lane_avoidance_penalty(agent, cell)
        cost -= self._queue_lane_entry_bonus(agent, cell)
        if cell != agent.cell:
            cost -= self.floor_dynamic_weight * self.dynamic_field.values.get(cell, 0.0)
        elif agent.target_cells and not self._is_near_target_cells(agent):
            stuck_penalty = max(0, agent.stuck_ticks - 2) * self.floor_stuck_wait_penalty
            cost += min(4.0, stuck_penalty)
        cost += self.floor_wall_weight * self._wall_penalty(cell)
        if cell != agent.cell and agent.previous_cell is not None:
            incoming = (agent.cell[0] - agent.previous_cell[0], agent.cell[1] - agent.previous_cell[1])
            outgoing = (cell[0] - agent.cell[0], cell[1] - agent.cell[1])
            if incoming == (-outgoing[0], -outgoing[1]):
                cost += self.floor_inertia_weight * 2.0
            elif incoming != outgoing:
                cost += self.floor_inertia_weight
            if self._is_non_progress_backtrack(agent, cell, static_field):
                cost += 8.0
        cost += self._recent_non_progress_penalty(agent, cell, static_field)
        party = self.party_states.get(agent.party_id)
        if party is not None and party.cohesion_enabled and len(party.member_agent_ids) >= 2:
            center = party.group_center
            if center is not None:
                distance = abs(cell[0] - center[0]) + abs(cell[1] - center[1])
                group_penalty = distance - 2.0
                if group_penalty > 0:
                    cost += self.floor_group_weight * group_penalty
        if self.floor_randomness > 0:
            cost += self.rng.random() * self.floor_randomness
        return cost

    def _is_non_progress_backtrack(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        static_field: dict[Cell, float],
        current_distance: float | None = None,
    ) -> bool:
        if agent.previous_cell is None or cell != agent.previous_cell:
            return False
        resolved_current_distance = (
            static_field.get(agent.cell, float("inf"))
            if current_distance is None
            else current_distance
        )
        candidate_distance = static_field.get(cell, float("inf"))
        return (
            math.isfinite(resolved_current_distance)
            and math.isfinite(candidate_distance)
            and candidate_distance >= resolved_current_distance
        )

    def _recent_non_progress_penalty(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        static_field: dict[Cell, float],
        current_distance: float | None = None,
    ) -> float:
        if cell == agent.cell or not agent.path_cells:
            return 0.0
        resolved_current_distance = (
            static_field.get(agent.cell, float("inf"))
            if current_distance is None
            else current_distance
        )
        candidate_distance = static_field.get(cell, float("inf"))
        if (
            not math.isfinite(resolved_current_distance)
            or not math.isfinite(candidate_distance)
            or candidate_distance < resolved_current_distance
        ):
            return 0.0

        recent_cells = agent.path_cells[:-1] if agent.path_cells[-1] == agent.cell else agent.path_cells
        penalty = 0.0
        for recency, recent_cell in enumerate(reversed(recent_cells[-24:]), start=1):
            if recent_cell != cell:
                continue
            penalty += max(1.0, 6.0 / float(recency))
        return min(12.0, penalty)

    def _is_recent_non_progress_move(self, agent: PedestrianAgent, cell: Cell) -> bool:
        if cell == agent.cell or not agent.target_cells:
            return False
        static_field = self._static_field(agent.target_cells)
        return (
            self._is_non_progress_backtrack(agent, cell, static_field)
            or self._recent_non_progress_penalty(agent, cell, static_field) > 0.0
        )

    def _forward_congestion_penalty(
        self,
        agent: PedestrianAgent,
        cell: Cell,
        density: DensityField,
        density_radius: int,
        static_field: dict[Cell, float] | None = None,
    ) -> float:
        if agent.state is not AgentState.TO_WINDOW or agent.desired_window_index is None:
            return 0.0
        if not agent.target_cells:
            return 0.0
        static_field = static_field if static_field is not None else self._static_field(agent.target_cells)
        current = cell
        total = 0.0
        neighbor_map = self.neighbors8 if self.floor_allow_diagonal else self.neighbors4
        queue_side_constraint = self.queue_side_constraints.get(agent.desired_window_index)
        reserved_service_cells = self.reserved_service_cells
        for depth in range(1, max(3, self.local_repair_radius) + 1):
            current_distance = static_field.get(current, float("inf"))
            if not math.isfinite(current_distance):
                break
            best_candidate: Cell | None = None
            best_key: tuple[float, int, int] | None = None
            for neighbor in neighbor_map.get(current, []):
                if neighbor not in self.in_bounds_cells or neighbor in self.grid.blocked_cells:
                    continue
                if queue_side_constraint is not None:
                    service, normal = queue_side_constraint
                    forward = (neighbor[0] - service[0]) * normal[0] + (neighbor[1] - service[1]) * normal[1]
                    if forward < 0:
                        continue
                if neighbor in reserved_service_cells and not self._agent_can_use_service_area(agent, neighbor):
                    continue
                distance = static_field.get(neighbor, float("inf"))
                if distance >= current_distance:
                    continue
                key = (distance, neighbor[1], neighbor[0])
                if best_key is None or key < best_key:
                    best_key = key
                    best_candidate = neighbor
            if best_candidate is None:
                break
            current = best_candidate
            local_density = self._route_cell_density(agent, current, density, density_radius)
            queue_penalty = 1 if self._queue_lane_avoidance_penalty(agent, current) > 0 else 0
            total += float(local_density + queue_penalty) / float(depth)
        return self.floor_density_weight * 0.65 * total

    def _queue_lane_avoidance_penalty(self, agent: PedestrianAgent, cell: Cell) -> float:
        return 0.0

    def _queue_lane_entry_bonus(self, agent: PedestrianAgent, cell: Cell) -> float:
        if agent.state not in {AgentState.TO_WINDOW, AgentState.QUEUEING}:
            return 0.0
        if agent.desired_window_index is None or agent.assigned_queue_slot_index is None:
            return 0.0
        queue_info = self._queue_slot_info(cell)
        if queue_info is None:
            return 0.0
        queue_window, queue_slot_index, _queue_owner = queue_info
        if queue_window != agent.desired_window_index:
            return 0.0
        if agent.student_id in self.window_queues.get(queue_window, []):
            if queue_slot_index > agent.assigned_queue_slot_index:
                return 0.0
        elif queue_slot_index < agent.assigned_queue_slot_index:
            return 0.0
        return 2.5

    def _wall_penalty(self, cell: Cell) -> float:
        penalty = self.wall_penalties.get(cell)
        if penalty is not None:
            return penalty
        if not self._is_walkable_cell(cell):
            return float("inf")
        penalty = wall_distance_or_penalty(cell, self.grid)
        self.wall_penalties[cell] = penalty
        return penalty

    def _static_field(self, target_cells: set[Cell]) -> dict[Cell, float]:
        key = tuple(sorted(target_cells))
        if key in self.static_fields:
            self.static_fields.move_to_end(key)
            return self.static_fields[key]
        self.static_fields[key] = build_static_field(self.grid, set(key))
        if len(self.static_fields) > self.static_field_cache_limit:
            self.static_fields.popitem(last=False)
        return self.static_fields[key]

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

    def _refresh_party_centers_if_needed(self) -> None:
        if self.has_multi_member_parties:
            self._refresh_party_centers()

    def _update_queue_targets(self) -> None:
        for window_index in sorted(set(self.window_queues) | set(self.window_walkers)):
            queue = list(self.window_queues.get(window_index, []))
            walkers = list(self.window_walkers.get(window_index, []))
            queue_cells = build_window_queue_cells(self.grid, window_index)
            if not queue_cells:
                continue
            for position, student_id in enumerate(queue):
                agent = self.agents.get(student_id)
                if agent is None:
                    continue
                target = queue_cells[min(position, len(queue_cells) - 1)]
                agent.desired_window_index = window_index
                agent.assigned_queue_slot_index = min(position, len(queue_cells) - 1)
                agent.target_type = "window_queue"
                agent.target_id = window_index
                agent.target_cells = {target}
                if agent.state is not AgentState.SERVICE:
                    agent.state = AgentState.QUEUEING if self._agent_reached_queue_target(agent) else AgentState.TO_WINDOW
            offset = len(queue)
            for position, student_id in enumerate(walkers):
                agent = self.agents.get(student_id)
                if agent is None:
                    continue
                slot_index = min(offset + position, len(queue_cells) - 1)
                target = queue_cells[slot_index]
                agent.desired_window_index = window_index
                agent.assigned_queue_slot_index = slot_index
                agent.target_type = "window_queue"
                agent.target_id = window_index
                agent.target_cells = {target}
                agent.state = AgentState.QUEUEING if self._agent_reached_queue_target(agent) else AgentState.TO_WINDOW
        self._refresh_queue_assignment_indexes()

    def _update_density_metric(self) -> None:
        occupied = {
            agent.cell
            for agent in self.agents.values()
            if self._occupies_walkable_cell(agent)
        }
        density = DensityField.from_occupied_cells(occupied, self.grid, radius=self.personal_space_radius_cells)
        self.max_density = max(self.max_density, max(density.densities.values(), default=0))

    def _occupies_walkable_cell(self, agent: PedestrianAgent) -> bool:
        return agent.state not in {AgentState.EXITED, AgentState.SEATED, AgentState.QUEUEING}

    def _is_movable(self, agent: PedestrianAgent) -> bool:
        if self._agent_should_hold_target_cell(agent):
            return False
        return agent.state in {
            AgentState.ENTERING,
            AgentState.TO_WINDOW,
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.TO_TABLE,
            AgentState.TO_EXIT,
        }

    def _agent_should_hold_target_cell(self, agent: PedestrianAgent) -> bool:
        if not agent.target_cells or agent.cell not in agent.target_cells:
            return False
        if agent.state is AgentState.QUEUEING:
            return True
        if agent.state is AgentState.TO_WINDOW and agent.assigned_queue_slot_index is not None:
            return True
        return (
            agent.state is AgentState.TO_TABLE
            and agent.assigned_table_approach_cell is not None
            and agent.assigned_table_approach_cell == agent.cell
        )

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
