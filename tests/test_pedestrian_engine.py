# 文件说明：高级行人引擎测试，覆盖 CA tick、冲突解决、密度成本和可复现性。

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pedestrian.agents import AgentState, PedestrianAgent
import app.pedestrian.engine as engine_module
import app.pedestrian.fields as fields_module
from app.pedestrian.fields import DensityField
from app.pedestrian.engine import PedestrianEngine
from app.pedestrian.metrics import movement_metrics
from app.pedestrian.grid import GridData, _queue_cells_from_service, is_walkable, neighbors
from app.simulation import (
    DiningLayoutData,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
    Student,
    _default_layout,
)


def engine_layout() -> DiningLayoutData:
    return DiningLayoutData(
        doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
        windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
        tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
    )


def movement_config(**overrides) -> SimulationConfigData:
    values = {
        "layout": engine_layout(),
        "num_windows": 1,
        "num_seats": 4,
        "movement_model": "advanced_floor_field",
        "floor_randomness": 0.0,
        "floor_allow_diagonal": False,
    }
    values.update(overrides)
    return SimulationConfigData(**values)


def student(student_id: int, party_id: int | None = None) -> Student:
    return Student(
        student_id=student_id,
        party_id=party_id or student_id,
        arrival_time=0,
        queue_enter_time=0,
        door_index=0,
    )


class PedestrianEngineTests(unittest.TestCase):
    # 验证队列车道距离预先建表，等待区选点不需要对每个候选格反复扫描整条队列。
    def test_queue_lane_distance_lookup_matches_bruteforce_distance(self):
        config = SimulationConfigData(
            num_windows=4,
            num_seats=36,
            layout=_default_layout(SimulationConfigData(num_windows=4, num_seats=36)),
            movement_model="advanced_floor_field",
            floor_randomness=0.0,
        )
        engine = PedestrianEngine(config.layout, config, random.Random(228))
        queue_cells = [
            cell
            for queue_slots in engine.grid.queue_cells_by_window.values()
            for cell in queue_slots
        ]
        sample_cells = [
            (0, 0),
            next(iter(engine.grid.service_cells.values())),
            queue_cells[0],
            (engine.grid.cols // 2, engine.grid.rows // 2),
            (engine.grid.cols - 1, engine.grid.rows - 1),
        ]

        for cell in sample_cells:
            expected = min(max(abs(cell[0] - queue[0]), abs(cell[1] - queue[1])) for queue in queue_cells)
            self.assertEqual(engine.queue_lane_distance_lookup[cell], expected)
            self.assertEqual(engine._nearest_queue_lane_distance(cell), expected)

    # 验证 agent 会从入口向窗口服务/队列目标移动。
    def test_agent_moves_from_entrance_toward_window(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(11))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        engine.set_agent_target_window(person.student_id, 0)
        start = engine.agents[person.student_id].cell

        for tick in range(4):
            engine.tick(tick * 5)

        agent = engine.agents[person.student_id]
        self.assertNotEqual(agent.cell, start)
        self.assertGreater(agent.walking_distance_cells, 0)
        self.assertEqual(agent.path_cells[0], start)

    # 验证默认 advanced CA 速度按 DES 行走速度换算为每 tick 多格微步，而不是 5 秒只走一格。
    def test_default_tick_budget_reaches_nearby_window_within_two_ticks(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(112))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        engine.set_agent_target_window(person.student_id, 0)

        first_tick_events = engine.tick(0)
        second_tick_events = engine.tick(5)

        agent = engine.agents[person.student_id]
        self.assertIn(agent.cell, agent.target_cells)
        self.assertEqual(agent.state, AgentState.QUEUEING)
        self.assertGreaterEqual(agent.walking_distance_cells, 18)
        self.assertGreater(len(first_tick_events) + len(second_tick_events), 2)

    # 验证同一分钟同入口到达的学生不会被注入到同一个 CA cell 里形成非物理堆叠。
    def test_spawn_arrivals_spreads_batch_across_entry_cells(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(111))
        people = [student(student_id) for student_id in range(1, 25)]

        engine.spawn_arrivals(people, door_index=0)

        cells = [agent.cell for agent in engine.agents.values()]
        self.assertEqual(len(cells), len(set(cells)))
        door_cell = engine.grid.door_cells[0]
        self.assertLessEqual(
            max(abs(cell[0] - door_cell[0]) + abs(cell[1] - door_cell[1]) for cell in cells),
            8,
        )

    # 验证并行更新后两个 agent 不能占用同一个目标格。
    def test_two_agents_cannot_enter_same_cell(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(12))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        target = (8, 8)
        engine.agents[1].cell = (7, 8)
        engine.agents[2].cell = (9, 8)
        for agent in engine.agents.values():
            agent.state = AgentState.TO_TABLE
            agent.target_cells = {target}

        engine.tick(0)

        cells = [agent.cell for agent in engine.agents.values()]
        self.assertEqual(len(cells), len(set(cells)))
        self.assertIn(target, cells)

    # 验证去其他窗口的行人可以穿过未占用的队列通道，避免第一个窗口队列把后续窗口隔断。
    def test_to_window_agent_can_cross_unowned_queue_lane_for_another_window(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=70, y=24, wall_side="top"),
                LayoutWindowData(id="W2", x=130, y=24, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        config = movement_config(layout=layout, num_windows=2)
        engine = PedestrianEngine(layout, config, random.Random(1201))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_agent_target_window(people[0].student_id, 0)
        engine.set_agent_target_window(people[1].student_id, 1)
        other_window_open_lane_cell = engine.grid.queue_cells_by_window[0][3]
        agent = engine.agents[people[1].student_id]

        self.assertIsNone(engine._queue_slot_owner(other_window_open_lane_cell))
        self.assertTrue(engine.can_agent_enter_cell(agent, other_window_open_lane_cell))

    # 验证其他窗口的活跃队列槽位仍可横穿，但不会沿着别人的队列线当走廊走。
    def test_to_window_agent_crosses_then_leaves_active_other_queue_lane(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=70, y=24, wall_side="top"),
                LayoutWindowData(id="W2", x=130, y=24, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        config = movement_config(layout=layout, num_windows=2)
        engine = PedestrianEngine(layout, config, random.Random(12011))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_window_physical_queue(0, [people[0].student_id])
        active_queue_head = engine.grid.queue_cells_by_window[0][0]
        empty_queue_lane_cell = engine.grid.queue_cells_by_window[0][4]
        head = engine.agents[people[0].student_id]
        head.cell = active_queue_head
        head.state = AgentState.QUEUEING
        head.target_cells = {active_queue_head}
        engine.set_agent_target_window(people[1].student_id, 1)
        walker = engine.agents[people[1].student_id]
        walker.cell = empty_queue_lane_cell
        occupied_by = {agent.cell: agent for agent in engine.agents.values()}
        occupied_all = set(occupied_by)
        occupied = engine._occupied_cells_for_agent(walker, occupied_by, occupied_all)
        density = DensityField.from_occupied_cells(occupied_all, engine.grid, radius=1)

        intended, _cost = engine._intended_move(walker, occupied, density, density_radius=1)

        self.assertTrue(engine.can_agent_enter_cell(walker, empty_queue_lane_cell))
        self.assertNotIn(intended, {
            engine.grid.queue_cells_by_window[0][3],
            engine.grid.queue_cells_by_window[0][5],
        })
        self.assertEqual(intended, (empty_queue_lane_cell[0] + 1, empty_queue_lane_cell[1]))

    # 验证去其他窗口的行人也能穿过已有人排队的位置，队伍不再形成硬障碍。
    def test_to_window_agent_can_pass_through_occupied_queue_lane_for_another_window(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=70, y=24, wall_side="top"),
                LayoutWindowData(id="W2", x=130, y=24, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        config = movement_config(layout=layout, num_windows=2)
        engine = PedestrianEngine(layout, config, random.Random(1202))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_window_physical_queue(0, [people[0].student_id])
        engine.set_agent_target_window(people[1].student_id, 1)
        occupied_queue_cell = next(iter(engine.agents[people[0].student_id].target_cells))
        engine.agents[people[0].student_id].cell = occupied_queue_cell
        engine._update_queue_targets()
        agent = engine.agents[people[1].student_id]
        occupied_by = {other.cell: other for other in engine.agents.values()}
        occupied = engine._occupied_cells_for_agent(agent, occupied_by, set(occupied_by))

        self.assertEqual(engine._queue_slot_owner(occupied_queue_cell), people[0].student_id)
        self.assertNotIn(occupied_queue_cell, occupied)
        self.assertTrue(engine.can_agent_enter_cell(agent, occupied_queue_cell))

    # 验证微步预计算的队列占用索引可直接用于占用剔除，不再为每个行人扫描全部占用格。
    def test_occupied_cells_uses_precomputed_queueing_indexes(self):
        class NoItemsDict(dict):
            def items(self):
                raise AssertionError("queue pass-through should use precomputed queueing indexes")

        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=70, y=24, wall_side="top"),
                LayoutWindowData(id="W2", x=130, y=24, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        config = movement_config(layout=layout, num_windows=2)
        engine = PedestrianEngine(layout, config, random.Random(12021))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_window_physical_queue(0, [people[0].student_id])
        engine.set_agent_target_window(people[1].student_id, 1)
        occupied_queue_cell = next(iter(engine.agents[people[0].student_id].target_cells))
        engine.agents[people[0].student_id].cell = occupied_queue_cell
        engine._update_queue_targets()
        agent = engine.agents[people[1].student_id]
        occupied_by = NoItemsDict({occupied_queue_cell: engine.agents[people[0].student_id], agent.cell: agent})

        occupied = engine._occupied_cells_for_agent(
            agent,
            occupied_by,
            set(occupied_by),
            queueing_cells_all={occupied_queue_cell},
            queueing_cells_by_window={0: {occupied_queue_cell}},
        )

        self.assertNotIn(occupied_queue_cell, occupied)

    # 验证排队者只参与 FIFO 服务，不再作为行人移动障碍。
    def test_queueing_agents_do_not_block_pedestrian_movement(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=70, y=24, wall_side="top"),
                LayoutWindowData(id="W2", x=130, y=24, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        config = movement_config(layout=layout, num_windows=2)
        engine = PedestrianEngine(layout, config, random.Random(1203))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_window_physical_queue(0, [people[0].student_id])
        engine.set_agent_target_window(people[1].student_id, 0)
        occupied_queue_cell = next(iter(engine.agents[people[0].student_id].target_cells))
        engine.agents[people[0].student_id].cell = occupied_queue_cell
        engine._update_queue_targets()
        agent = engine.agents[people[1].student_id]
        occupied_by = {other.cell: other for other in engine.agents.values()}
        occupied = engine._occupied_cells_for_agent(agent, occupied_by, set(occupied_by))

        self.assertEqual(engine._queue_slot_owner(occupied_queue_cell), people[0].student_id)
        self.assertNotIn(occupied_queue_cell, occupied)
        self.assertFalse(engine._occupies_walkable_cell(engine.agents[people[0].student_id]))
        self.assertTrue(engine.can_agent_enter_cell(agent, occupied_queue_cell))

    # 验证逻辑 FIFO 成员还没走到自己队列槽位前，视觉上仍显示为前往窗口。
    def test_physical_queue_sync_marks_off_slot_fifo_members_as_to_window(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1204))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        first = engine.agents[1]
        second = engine.agents[2]
        first.cell = queue_slots[0]
        second.cell = (queue_slots[1][0] + 4, queue_slots[1][1])

        engine.set_window_physical_queue(0, [1, 2])

        self.assertEqual(first.state, AgentState.QUEUEING)
        self.assertEqual(second.state, AgentState.TO_WINDOW)
        self.assertEqual(second.target_cells, {queue_slots[1]})

    # 验证已站到本窗口队列车道上的学生会显示为排队，而不是仍显示为行走。
    def test_physical_queue_sync_marks_own_lane_agents_as_queueing(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1205))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        second = engine.agents[2]
        second.cell = queue_slots[2]

        engine.set_window_physical_queue(0, [1, 2])

        self.assertEqual(second.target_cells, {queue_slots[1]})
        self.assertEqual(second.state, AgentState.QUEUEING)

    # 验证多个 agent 选择同一格时会记录冲突计数。
    def test_multi_agent_conflict_records_conflict_count(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(13))
        people = [student(1), student(2), student(3)]
        engine.spawn_arrivals(people, door_index=0)
        target = (8, 8)
        for cell, agent in zip([(7, 8), (9, 8), (8, 7)], engine.agents.values()):
            agent.cell = cell
            agent.state = AgentState.TO_WINDOW
            agent.target_cells = {target}

        engine.tick(0)

        self.assertGreaterEqual(sum(agent.conflict_count for agent in engine.agents.values()), 2)

    # 验证等待/排队这类静止状态与行走者抢格时，不计入移动冲突指标。
    def test_stationary_state_conflict_does_not_increment_movement_conflicts(self):
        for stationary_state in (AgentState.WAITING_GROUP, AgentState.QUEUEING):
            with self.subTest(stationary_state=stationary_state):
                engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1301))
                people = [student(1), student(2)]
                engine.spawn_arrivals(people, door_index=0)
                target = (8, 8)
                walker = engine.agents[1]
                stationary = engine.agents[2]
                walker.cell = (7, 8)
                walker.state = AgentState.TO_WINDOW
                walker.target_cells = {target}
                stationary.cell = (9, 8)
                stationary.state = stationary_state
                stationary.target_cells = {target}

                engine.tick(0)

                self.assertEqual(0, sum(agent.conflict_count for agent in engine.agents.values()))
                self.assertEqual(0, engine.metrics_snapshot()["movement_conflict_count"])

    # 验证局部密度惩罚会让 agent 避开高密度候选格。
    def test_density_penalty_changes_intended_move(self):
        config = movement_config(
            floor_density_weight=8.0,
            floor_static_weight=1.0,
            congestion_density_threshold=1,
            personal_space_radius_cells=1,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(14))
        people = [student(index) for index in range(1, 6)]
        engine.spawn_arrivals(people, door_index=0)
        mover = engine.agents[1]
        mover.cell = (5, 5)
        mover.state = AgentState.TO_WINDOW
        mover.target_cells = {(8, 5)}
        for agent, cell in zip([engine.agents[2], engine.agents[3], engine.agents[4], engine.agents[5]], [(6, 4), (6, 6), (7, 5), (7, 4)]):
            agent.cell = cell
            agent.state = AgentState.WAITING_GROUP
            agent.target_cells = {cell}

        intended, _cost = engine._intended_move(mover, occupied_cells={agent.cell for agent in engine.agents.values() if agent.student_id != mover.student_id})

        self.assertNotEqual(intended, (6, 5))
        self.assertIn(intended, [mover.cell, *neighbors(mover.cell, engine.grid)])

    # 验证候选格评分热路径内联密度惩罚公式，避免每个候选格调用 DensityField.penalty。
    def test_candidate_cost_inlines_density_penalty_hot_path(self):
        config = movement_config(
            floor_density_weight=2.5,
            floor_static_weight=1.0,
            floor_dynamic_weight=0.0,
            floor_wall_weight=0.0,
            floor_inertia_weight=0.0,
            floor_group_weight=0.0,
            floor_randomness=0.0,
            congestion_density_threshold=2,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1401))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.cell = (5, 5)
        agent.target_cells = {(9, 5)}
        candidate = (6, 5)
        density = DensityField(densities={candidate: 4})
        static_field = {candidate: 4.0}

        original_penalty = DensityField.penalty

        def forbidden_penalty(*_args, **_kwargs):
            raise AssertionError("candidate scoring should inline density penalty")

        DensityField.penalty = forbidden_penalty
        try:
            cost = engine._candidate_cost(
                candidate,
                agent,
                density,
                density_radius=1,
                static_field=static_field,
            )
        finally:
            DensityField.penalty = original_penalty

        self.assertEqual(cost, 9.0)

    # 验证前方拥堵预判不在候选格热路径里调用完整准入判断。
    def test_forward_congestion_penalty_uses_lightweight_walkability_check(self):
        config = movement_config(
            floor_density_weight=6.0,
            floor_static_weight=1.0,
            floor_wall_weight=0.0,
            floor_dynamic_weight=0.0,
            floor_inertia_weight=0.0,
            floor_group_weight=0.0,
            floor_randomness=0.0,
            congestion_density_threshold=10,
            personal_space_radius_cells=1,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1404))
        engine.spawn_arrivals([student(1)], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_WINDOW
        agent.desired_window_index = 0
        agent.cell = (8, 5)
        agent.target_cells = {(13, 5)}
        density = DensityField(densities={(10, 5): 5, (11, 5): 5})

        original_can_enter = engine.can_agent_enter_cell

        def forbidden_can_enter(*_args, **_kwargs):
            raise AssertionError("forward congestion prediction should not call full enterability checks")

        engine.can_agent_enter_cell = forbidden_can_enter
        try:
            penalty = engine._forward_congestion_penalty(agent, (8, 5), density, density_radius=1)
        finally:
            engine.can_agent_enter_cell = original_can_enter

        self.assertGreater(penalty, 0.0)

    # 验证移动候选热路径使用引擎 walkable lookup，并能感知初始化后的 blocked cell 变更。
    def test_intended_move_uses_walkable_lookup_for_candidate_filtering(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1402))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_TABLE
        agent.cell = (5, 5)
        agent.target_cells = {(8, 5)}
        blocked_neighbor = (6, 5)
        engine.grid.blocked_cells.add(blocked_neighbor)

        original_is_walkable = getattr(engine_module, "is_walkable", None)

        def forbidden_is_walkable(*_args, **_kwargs):
            raise AssertionError("movement hot path should use engine walkable lookup")

        if original_is_walkable is not None:
            engine_module.is_walkable = forbidden_is_walkable
        try:
            intended, _cost = engine._intended_move(agent, occupied_cells=set())
        finally:
            if original_is_walkable is not None:
                engine_module.is_walkable = original_is_walkable

        self.assertNotEqual(intended, blocked_neighbor)

    # 验证初始化时被阻塞的格子运行时释放后，移动准入逻辑不会被旧快照卡住。
    def test_runtime_unblocked_cell_becomes_enterable(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1403))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.WAITING_GROUP

        formerly_blocked = min(engine.grid.table_cells[0])
        self.assertIn(formerly_blocked, engine.grid.blocked_cells)

        engine.grid.blocked_cells.remove(formerly_blocked)

        self.assertTrue(engine.can_agent_enter_cell(agent, formerly_blocked))
        agent.cell = (formerly_blocked[0] - 1, formerly_blocked[1])
        agent.target_cells = {formerly_blocked}

        intended, _cost = engine._intended_move(agent, occupied_cells=set())

        self.assertEqual(intended, formerly_blocked)

    # 验证稀疏占用的密度场按占用格邻域构建，而不是扫描整张网格。
    def test_density_field_sparse_occupancy_uses_local_accumulation(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(141))
        original_is_walkable = fields_module.is_walkable
        calls = {"count": 0}

        def counted_is_walkable(cell, grid):
            calls["count"] += 1
            return original_is_walkable(cell, grid)

        fields_module.is_walkable = counted_is_walkable
        try:
            density = DensityField.from_occupied_cells({(5, 5), (8, 8)}, engine.grid, radius=1)
        finally:
            fields_module.is_walkable = original_is_walkable

        self.assertEqual(density.density((5, 5)), 1)
        self.assertEqual(density.density((6, 6)), 1)
        self.assertEqual(density.density((7, 7)), 1)
        self.assertEqual(density.density((20, 20)), 0)
        self.assertLess(calls["count"], 80)

    # 验证单个 tick 复用密度场，而不是为每个移动 agent 重建一次。
    def test_tick_reuses_density_field_for_all_movable_agents(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(142))
        people = [student(1), student(2), student(3)]
        engine.spawn_arrivals(people, door_index=0)
        for idx, person in enumerate(people):
            agent = engine.agents[person.student_id]
            agent.state = AgentState.TO_WINDOW
            agent.cell = (8 + idx, 8)
            agent.target_cells = {(13, 3)}

        original_from_occupied = DensityField.from_occupied_cells
        calls = {"count": 0}

        def counted_from_occupied(occupied_cells, grid, radius=1):
            calls["count"] += 1
            return original_from_occupied(occupied_cells, grid, radius)

        DensityField.from_occupied_cells = counted_from_occupied
        try:
            engine.tick(0)
        finally:
            DensityField.from_occupied_cells = original_from_occupied

        self.assertLessEqual(calls["count"], engine._movement_budget_cells_per_tick() + 1)

    # 验证墙惩罚预计算与原函数一致，且 static field 缓存按 LRU 上限淘汰。
    def test_wall_penalty_and_static_field_caches_are_bounded(self):
        engine = PedestrianEngine(
            engine_layout(),
            movement_config(static_field_cache_limit=16),
            random.Random(143),
        )
        sample_cell = next(iter(engine.wall_penalties))

        self.assertEqual(
            engine.wall_penalties[sample_cell],
            fields_module.wall_distance_or_penalty(sample_cell, engine.grid),
        )

        walkable = [
            cell
            for cell in engine.wall_penalties
            if cell not in engine.grid.blocked_cells
        ][:40]
        for cell in walkable:
            engine._static_field({cell})

        self.assertLessEqual(len(engine.static_fields), 16)

    # 验证移动热点查询索引会随队列和餐桌入口目标刷新，避免每次候选格判断重复扫描。
    def test_movement_lookup_indexes_refresh_for_queue_and_table_targets(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(144))
        people = [student(1), student(2), student(3)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]

        engine.set_window_physical_queue(0, [1])
        engine.set_agent_target_window(2, 0)
        engine._refresh_movement_indexes()

        self.assertEqual(engine._queue_slot_info(queue_slots[0]), (0, 0, 1))
        self.assertEqual(engine._queue_slot_info(queue_slots[1]), (0, 1, 2))
        self.assertTrue(engine._queue_slot_window_has_assignments(queue_slots[2]))

        engine.set_window_physical_queue(0, [2])
        engine._refresh_movement_indexes()

        self.assertEqual(engine._queue_slot_info(queue_slots[0]), (0, 0, 2))
        self.assertEqual(engine._queue_slot_info(queue_slots[1]), (0, 1, None))

        engine.set_party_target_table([people[2]], table_index=0)
        target = engine.agents[3].assigned_table_approach_cell
        self.assertIsNotNone(target)
        engine._refresh_movement_indexes()

        self.assertEqual(engine._table_approach_owner(target), 3)

        engine.set_agent_seated(3, table_index=0, preserve_cell=True)
        engine._refresh_movement_indexes()

        self.assertIsNone(engine._table_approach_owner(target))

    # 验证同队小组成员启用凝聚后不会持续拉开距离。
    def test_group_cohesion_prevents_unbounded_spread(self):
        engine = PedestrianEngine(engine_layout(), movement_config(floor_group_weight=3.0), random.Random(15))
        people = [student(1, party_id=7), student(2, party_id=7)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_party_target_table(people, table_index=0)

        for tick in range(10):
            engine.tick(tick * 5)

        first = engine.agents[1].cell
        second = engine.agents[2].cell
        self.assertLessEqual(abs(first[0] - second[0]) + abs(first[1] - second[1]), 4)

    # 验证全部为单人 party 时，tick 不刷新无效的小组中心。
    def test_single_member_parties_skip_center_refresh_during_tick(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1501))
        people = [student(1, party_id=1), student(2, party_id=2), student(3, party_id=3)]
        engine.spawn_arrivals(people, door_index=0)
        for person in people:
            engine.set_agent_target_window(person.student_id, 0)

        def forbidden_refresh() -> None:
            raise AssertionError("single-member parties should not refresh group centers during tick")

        engine._refresh_party_centers = forbidden_refresh

        engine.tick(0)

    # 验证固定 seed 下每个 agent 的路径完全可复现。
    def test_fixed_seed_movement_is_reproducible(self):
        def paths_for_seed(seed: int) -> dict[int, list[tuple[int, int]]]:
            engine = PedestrianEngine(engine_layout(), movement_config(floor_randomness=0.1), random.Random(seed))
            people = [student(1, party_id=1), student(2, party_id=1)]
            engine.spawn_arrivals(people, door_index=0)
            for person in people:
                engine.set_agent_target_window(person.student_id, 0)
            for tick in range(8):
                engine.tick(tick * 5)
            return {student_id: list(agent.path_cells) for student_id, agent in engine.agents.items()}

        self.assertEqual(paths_for_seed(2026), paths_for_seed(2026))

    # 验证窗口目标格被占用时，贴近队列目标的 agent 仍可进入离散事件队列。
    def test_ready_to_queue_accepts_agent_adjacent_to_blocked_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(16))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_WINDOW
        agent.cell = (9, 8)
        agent.target_cells = {(10, 8)}

        self.assertEqual(engine.ready_to_queue_student_ids({1}), [1])

    # 验证 window_walkers 中后到达物理槽位的人可以先进入 physical queue，避免 walking 队首阻塞窗口。
    def test_ready_to_queue_accepts_later_walker_that_reached_physical_slot(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1610))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_agent_target_window(1, 0)
        engine.set_agent_target_window(2, 0)
        first = engine.agents[1]
        second = engine.agents[2]
        first.cell = (2, 20)
        first.state = AgentState.TO_WINDOW
        second_slot = engine.grid.queue_cells_by_window[0][1]
        second.cell = second_slot
        second.state = AgentState.QUEUEING

        self.assertEqual(engine.ready_to_queue_student_ids({1, 2}), [2])

    # 验证窗口队列槽位不包含服务格，且物理队列按 FIFO 顺序分配槽位。
    def test_window_queue_slots_exclude_service_cell_and_assign_fifo_targets(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(160))
        people = [student(1), student(2), student(3)]
        engine.spawn_arrivals(people, door_index=0)

        service_cell = engine.grid.service_cells[0]
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1, 2])
        engine.set_agent_target_window(3, 0)

        self.assertNotEqual(queue_slots[0], service_cell)
        self.assertEqual(engine.agents[1].target_cells, {queue_slots[0]})
        self.assertEqual(engine.agents[2].target_cells, {queue_slots[1]})
        self.assertEqual(engine.agents[3].target_cells, {queue_slots[2]})
        self.assertTrue(engine.can_agent_enter_cell(engine.agents[2], queue_slots[0]))
        self.assertTrue(engine.can_agent_enter_cell(engine.agents[3], queue_slots[0]))

    # 验证取餐后找座的人可以借过排队槽离开车道，但不能进入窗口服务格。
    def test_to_table_agent_can_escape_via_queue_slot_but_not_service_cell(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1601))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        service_cell = engine.grid.service_cells[0]
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1])
        agent = engine.agents[2]
        agent.state = AgentState.TO_TABLE
        agent.cell = queue_slots[5]
        agent.target_cells = {(agent.cell[0], agent.cell[1] + 8)}

        self.assertFalse(engine.can_agent_enter_cell(agent, service_cell))
        self.assertFalse(engine._can_agent_reserve_repair_cell(agent, service_cell))
        self.assertTrue(engine.can_agent_enter_cell(agent, queue_slots[0]))
        self.assertTrue(engine._can_agent_reserve_repair_cell(agent, queue_slots[0]))
        self.assertTrue(engine.can_agent_enter_cell(agent, queue_slots[1]))
        self.assertTrue(engine._can_agent_reserve_repair_cell(agent, queue_slots[1]))

    # 验证餐桌目标为每个同组成员分配唯一 approach slot。
    def test_party_table_target_assigns_unique_approach_slots_per_member(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(161))
        people = [student(1, party_id=7), student(2, party_id=7)]
        engine.spawn_arrivals(people, door_index=0)

        engine.set_party_target_table(people, table_index=0)

        assigned = [
            engine.agents[person.student_id].assigned_table_approach_cell
            for person in people
        ]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertTrue(all(engine.agents[person.student_id].target_cells == {assigned[index]} for index, person in enumerate(people)))

    # 验证餐桌边目标格拥挤时，已到餐桌邻近格的小组可正式入座。
    def test_party_ready_to_seat_accepts_agents_adjacent_to_table_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(17))
        people = [student(1, party_id=7)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_party_target_table(people, table_index=0)
        agent = engine.agents[1]
        target = sorted(agent.target_cells)[0]
        agent.cell = (target[0] + 1, target[1])

        self.assertTrue(engine.party_ready_to_seat(people))

    # 验证已入座 agent 不再作为行走碰撞体阻塞通道，也不再输出到 pedestrian_agents。
    def test_seated_agents_do_not_block_walkable_cells_or_render_as_pedestrians(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(20))
        seated = student(1, party_id=1)
        mover = student(2, party_id=2)
        engine.spawn_arrivals([seated, mover], door_index=0)
        engine.agents[seated.student_id].cell = (13, 6)
        engine.agents[mover.student_id].cell = (13, 7)
        engine.set_agent_seated(seated.student_id, table_index=0, preserve_cell=True)
        engine.agents[mover.student_id].state = AgentState.TO_WINDOW
        engine.agents[mover.student_id].target_cells = {(13, 5)}

        engine.tick(0)

        self.assertIn((13, 6), engine.agents[mover.student_id].path_cells)
        self.assertNotEqual(engine.agents[mover.student_id].cell, (13, 7))
        self.assertEqual([item["student_id"] for item in engine.agent_snapshots()], [mover.student_id])

    # 验证服务开始只改状态，不把仍在远处的队首凭空挪到 service cell。
    def test_set_agent_service_does_not_teleport_agent_to_service_cell(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(201))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[person.student_id]
        agent.cell = (3, 13)
        agent.path_cells = [agent.cell]

        engine.set_agent_service(person.student_id, 0)

        self.assertEqual(agent.state, AgentState.SERVICE)
        self.assertEqual(agent.cell, (3, 13))
        self.assertEqual(agent.path_cells, [(3, 13)])

    # 验证队列补位只更新目标，不直接把后续队员瞬移到新的槽位。
    def test_queue_retarget_does_not_teleport_agent_to_new_slot(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(203))
        head = student(1)
        tail = student(2)
        engine.spawn_arrivals([head, tail], door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [head.student_id, tail.student_id])
        tail_agent = engine.agents[tail.student_id]
        tail_agent.cell = queue_slots[1]
        tail_agent.path_cells = [tail_agent.cell]
        tail_agent.walking_distance_cells = 0
        tail_agent.walking_time_seconds = 0

        engine.set_window_physical_queue(0, [tail.student_id])

        self.assertEqual(tail_agent.target_cells, {queue_slots[0]})
        self.assertEqual(tail_agent.cell, queue_slots[1])
        self.assertEqual(tail_agent.path_cells, [queue_slots[1]])
        self.assertEqual(tail_agent.walking_distance_cells, 0)
        self.assertEqual(tail_agent.walking_time_seconds, 0)

    # 验证吃完离场会直接从行人层消失，不再模拟去出口的动画。
    def test_set_agent_exited_marks_exited_without_exit_animation(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(202))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[person.student_id]
        agent.cell = (18, 24)
        agent.path_cells = [agent.cell]
        engine.set_agent_seated(person.student_id, table_index=0, preserve_cell=True)

        engine.set_agent_exited(person.student_id)

        self.assertEqual(agent.state, AgentState.EXITED)
        self.assertEqual(agent.target_cells, set())

        events = []
        for tick in range(10):
            events.extend(engine.tick(tick * 5))

        self.assertEqual(agent.state, AgentState.EXITED)
        self.assertFalse(
            any(event["type"] == "pedestrian_move" and event["student_id"] == person.student_id for event in events)
        )
        self.assertEqual(agent.walking_distance_cells, 0)

    # 验证后端默认布局会按规模留出可达通道，不生成缺少 approach cell 的餐桌。
    def test_default_layout_tables_have_approach_targets_for_advanced_grid(self):
        for seats in [60, 120, 300, 2000]:
            with self.subTest(seats=seats):
                config = SimulationConfigData(
                    num_windows=6,
                    num_seats=seats,
                    movement_model="advanced_floor_field",
                    floor_randomness=0.0,
                )
                engine = PedestrianEngine(_default_layout(config), config, random.Random(171))
                missing = [
                    table_index
                    for table_index, approach in engine.grid.table_approach_cells.items()
                    if not approach
                ]

                self.assertEqual(missing, [])

    # 验证动态场不会因为当前格被反复沉积而奖励 agent 原地停滞。
    def test_dynamic_field_does_not_make_agent_prefer_staying_on_current_cell(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(18))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_TABLE
        agent.cell = (10, 8)
        agent.target_cells = {(10, 21)}
        for _ in range(20):
            engine.dynamic_field.deposit(agent.cell)

        intended, _cost = engine._intended_move(agent, occupied_cells=set())

        self.assertNotEqual(intended, agent.cell)
        self.assertLess(abs(intended[0] - 10) + abs(intended[1] - 21), abs(agent.cell[0] - 10) + abs(agent.cell[1] - 21))

    # 验证静止排队/服务人员不会在动态场中凭空沉积足迹。
    def test_dynamic_field_deposit_only_tracks_agents_that_moved_this_tick(self):
        engine = PedestrianEngine(
            engine_layout(),
            movement_config(dynamic_field_decay=1.0, dynamic_field_diffusion=0.0),
            random.Random(181),
        )
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        service = engine.agents[1]
        queueing = engine.agents[2]
        service.state = AgentState.SERVICE
        service.cell = (10, 10)
        service.target_cells = {service.cell}
        queueing.state = AgentState.QUEUEING
        queueing.cell = (11, 10)
        queueing.target_cells = {queueing.cell}

        engine.tick(0)

        self.assertEqual(engine.dynamic_field.values, {})

    # 验证真实移动者在本 tick 结束后只在移动后的 cell 沉积动态场。
    def test_dynamic_field_deposits_moved_agent_final_cell(self):
        engine = PedestrianEngine(
            engine_layout(),
            movement_config(dynamic_field_decay=1.0, dynamic_field_diffusion=0.0),
            random.Random(182),
        )
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[person.student_id]
        start = (10, 10)
        target = (12, 10)
        agent.state = AgentState.TO_TABLE
        agent.cell = start
        agent.target_cells = {target}
        agent.path_cells = [start]

        engine.tick(0)

        self.assertEqual(agent.cell, target)
        self.assertEqual(engine.dynamic_field.values.get(target), 1.0)
        self.assertNotIn(start, engine.dynamic_field.values)

    # 验证 agent 被前方占用持续阻塞后，会选择侧移而不是无限原地停滞。
    def test_stuck_agent_prefers_sidestep_over_waiting_forever(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(19))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        mover = engine.agents[1]
        blocker = engine.agents[2]
        mover.state = AgentState.TO_WINDOW
        mover.cell = (13, 6)
        mover.target_cells = {(13, 3)}
        mover.stuck_ticks = 20
        blocker.state = AgentState.WAITING_GROUP
        blocker.cell = (13, 5)
        blocker.target_cells = {blocker.cell}

        intended, _cost = engine._intended_move(mover, occupied_cells={blocker.cell})

        self.assertNotEqual(intended, mover.cell)
        self.assertIn(intended, [(12, 6), (14, 6), (13, 7)])

    # 验证卡住后的绕行不会反复选择近期已经证明无效的同距离格。
    def test_stuck_agent_avoids_recent_non_progress_revisit(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1900))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_TABLE
        agent.cell = (5, 5)
        agent.previous_cell = (4, 5)
        agent.target_cells = {(8, 5)}
        agent.stuck_ticks = 20
        agent.path_cells = [(5, 5), (5, 4), (5, 5), (5, 4), (5, 5)]

        intended, _cost = engine._intended_move(agent, occupied_cells={(6, 5)})

        self.assertEqual(intended, (5, 6))

    # 验证局部 repair 评分同样避开近期无效重复格。
    def test_repair_path_score_penalizes_recent_non_progress_revisit(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(19001))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_TABLE
        agent.cell = (5, 5)
        agent.target_cells = {(8, 5)}
        agent.path_cells = [(5, 5), (5, 4), (5, 5), (5, 4), (5, 5)]

        recent_score = engine._repair_path_score(agent, [(5, 4)])
        open_score = engine._repair_path_score(agent, [(5, 6)])

        self.assertLess(open_score, recent_score)

    # 验证等价候选格不会固定向某个方向偏置，而是按目标相对方向选择绕行入口。
    def test_to_window_equal_cost_tie_break_tracks_target_axis(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(1901))
        people = [student(index) for index in range(1, 11)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, list(range(1, 10)))
        for slot_index, student_id in enumerate(range(1, 10)):
            agent = engine.agents[student_id]
            agent.cell = queue_slots[slot_index]
            agent.state = AgentState.QUEUEING
            agent.target_cells = {queue_slots[slot_index]}
            agent.desired_window_index = 0
            agent.assigned_queue_slot_index = slot_index

        engine.set_agent_target_window(10, 0)
        walker = engine.agents[10]
        walker.cell = (8, 5)
        walker.path_cells = [walker.cell]
        occupied = {
            agent.cell
            for agent in engine.agents.values()
            if agent.student_id != walker.student_id
        }
        density = DensityField.from_occupied_cells(occupied, engine.grid, radius=1)

        intended, _cost = engine._intended_move(walker, occupied, density, density_radius=1)

        self.assertEqual(walker.target_cells, {queue_slots[9]})
        self.assertEqual(intended, (8, 6))

        walker.target_cells = {(10, 0)}
        intended, _cost = engine._intended_move(walker, occupied, density, density_radius=1)

        self.assertEqual(intended, (8, 4))

    # 验证窗口行人会看前方几步的拥挤度，选择人少的侧向绕行，而不是继续挤进拥挤走廊。
    def test_to_window_agent_uses_congestion_aware_detour_before_getting_stuck(self):
        config = movement_config(
            floor_density_weight=6.0,
            floor_static_weight=1.0,
            floor_wall_weight=0.0,
            floor_dynamic_weight=0.0,
            floor_inertia_weight=0.0,
            floor_group_weight=0.0,
            floor_randomness=0.0,
            congestion_density_threshold=10,
            personal_space_radius_cells=1,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1902))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_WINDOW
        agent.desired_window_index = 0
        agent.cell = (8, 5)
        agent.target_cells = {(13, 5)}
        agent.stuck_ticks = 0
        density = DensityField(densities={(9, 5): 2, (10, 5): 5, (11, 5): 5, (12, 5): 5})

        intended, _cost = engine._intended_move(agent, occupied_cells=set(), density=density, density_radius=1)

        self.assertIn(intended, {(8, 4), (8, 6)})

    # 验证动态路径场能看到远处拥挤，愿意先多走几步到空地绕行，而不是只看眼前两步继续走近路。
    def test_to_window_dynamic_cost_field_prefers_open_longer_route(self):
        config = movement_config(
            floor_density_weight=6.0,
            floor_static_weight=1.0,
            floor_wall_weight=0.0,
            floor_dynamic_weight=0.0,
            floor_inertia_weight=0.0,
            floor_group_weight=0.0,
            floor_randomness=0.0,
            congestion_density_threshold=10,
            personal_space_radius_cells=1,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1903))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        agent.state = AgentState.TO_WINDOW
        agent.desired_window_index = 0
        agent.cell = (8, 5)
        agent.target_cells = {(18, 5)}
        density = DensityField(densities={
            (8, 4): 5,
            (9, 4): 5,
            (10, 4): 5,
            (12, 5): 5,
            (13, 5): 5,
            (14, 5): 5,
            (15, 5): 5,
            (16, 5): 5,
            (17, 5): 5,
        })

        intended, _cost = engine._intended_move(agent, occupied_cells=set(), density=density, density_radius=1)

        self.assertEqual(intended, (8, 6))

    # 验证走向餐桌的人被通道中站立者挡住时，会通过局部让行借过，而不是无限等待或传送入座。
    def test_to_table_agent_borrows_past_local_blocker(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(21))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        passer = engine.agents[1]
        blocker = engine.agents[2]
        passer.state = AgentState.TO_TABLE
        passer.cell = (10, 10)
        passer.target_cells = {(10, 8)}
        passer.stuck_ticks = 8
        blocker.state = AgentState.WAITING_GROUP
        blocker.cell = (10, 9)
        blocker.target_cells = {blocker.cell}

        engine.tick(0)

        self.assertIn((10, 9), passer.path_cells)
        self.assertEqual(passer.cell, (10, 8))
        self.assertTrue(any(cell in {(9, 9), (11, 9), (10, 10)} for cell in blocker.path_cells))
        self.assertNotEqual(passer.cell, blocker.cell)

    # 验证已经站到自己餐桌入口的人不会被借位逻辑推走，避免到达目标后反复离开再回来。
    def test_local_borrow_does_not_move_table_agent_already_at_own_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(2101))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        passer = engine.agents[1]
        blocker = engine.agents[2]
        target = (10, 9)
        passer.state = AgentState.TO_TABLE
        passer.cell = (10, 10)
        passer.target_cells = {(10, 8)}
        passer.stuck_ticks = 8
        blocker.state = AgentState.TO_TABLE
        blocker.cell = target
        blocker.assigned_table_approach_cell = target
        blocker.target_cells = {target}
        occupied_by = {passer.cell: passer, blocker.cell: blocker}
        density = DensityField.from_occupied_cells(set(occupied_by), engine.grid, radius=1)

        borrow = engine._local_borrow_move(
            passer,
            planned_targets={passer.student_id: passer.cell, blocker.student_id: blocker.cell},
            occupied_by=occupied_by,
            reserved_targets=set(),
            density=density,
            density_radius=1,
        )

        self.assertIsNone(borrow)

    # 验证借位让路不会把阻塞者推回近期已经反复走过的无效格。
    def test_borrow_yield_avoids_recent_non_progress_cell(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(21011))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        passer = engine.agents[1]
        blocker = engine.agents[2]
        passer.state = AgentState.TO_TABLE
        passer.cell = (26, 39)
        passer.target_cells = {(30, 39)}
        blocker.state = AgentState.TO_TABLE
        blocker.cell = (27, 39)
        blocker.target_cells = {(55, 39)}
        blocker.path_cells = [(27, 39), (27, 38), (27, 39), (27, 38), (27, 39)]
        occupied_by = {passer.cell: passer, blocker.cell: blocker}
        density = DensityField.from_occupied_cells(set(occupied_by), engine.grid, radius=1)

        yield_cell = engine._borrow_yield_cell(
            passer,
            blocker,
            occupied_by=occupied_by,
            reserved_targets={(27, 40)},
            density=density,
            density_radius=1,
        )

        self.assertEqual(yield_cell, (28, 39))

    # 验证已锁定目标格的人在局部 repair 规划中也不能被安排离开自己的目标格。
    def test_repair_reservation_keeps_table_agent_on_own_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(2102))
        person = student(1, party_id=1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        target = (10, 9)
        agent.state = AgentState.TO_TABLE
        agent.cell = target
        agent.assigned_table_approach_cell = target
        agent.target_cells = {target}

        self.assertFalse(engine._can_agent_reserve_repair_cell(agent, (9, 9)))
        self.assertTrue(engine._can_agent_reserve_repair_cell(agent, target))

    # 验证 reservation-table 局部修复计划不产生同格冲突或边交换。
    def test_local_repair_plan_avoids_vertex_and_edge_swap_conflicts(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(211))
        people = [student(1, party_id=1), student(2, party_id=2), student(3, party_id=3)]
        engine.spawn_arrivals(people, door_index=0)
        engine.agents[1].state = AgentState.TO_TABLE
        engine.agents[1].cell = (10, 10)
        engine.agents[1].target_cells = {(10, 8)}
        engine.agents[1].stuck_ticks = 12
        engine.agents[2].state = AgentState.WAITING_GROUP
        engine.agents[2].cell = (10, 9)
        engine.agents[2].target_cells = {(10, 9)}
        engine.agents[3].state = AgentState.TO_EXIT
        engine.agents[3].cell = (9, 9)
        engine.agents[3].target_cells = {(8, 9)}

        plan = engine._plan_local_repair_with_reservations(
            center=(10, 9),
            agent_ids=[1, 2, 3],
            horizon=4,
            radius=3,
        )

        self.assertIn(1, plan)
        self.assertLess(abs(plan[1][-1][0] - 10) + abs(plan[1][-1][1] - 8), 2)
        starts = {agent_id: engine.agents[agent_id].cell for agent_id in plan}
        for step in range(1, 5):
            occupied_at_step = [
                path[min(step - 1, len(path) - 1)]
                for path in plan.values()
            ]
            self.assertEqual(len(occupied_at_step), len(set(occupied_at_step)))
            previous_at_step = {
                agent_id: starts[agent_id] if step == 1 else path[min(step - 2, len(path) - 1)]
                for agent_id, path in plan.items()
            }
            current_at_step = {
                agent_id: path[min(step - 1, len(path) - 1)]
                for agent_id, path in plan.items()
            }
            for first_id, first_current in current_at_step.items():
                for second_id, second_current in current_at_step.items():
                    if first_id >= second_id:
                        continue
                    self.assertFalse(
                        first_current == previous_at_step[second_id]
                        and second_current == previous_at_step[first_id]
                    )

    # 验证低优先级 fallback 原地等待不能覆盖高优先级 reservation。
    def test_local_repair_fallback_does_not_overwrite_existing_reservation(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(213))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        head = engine.agents[1]
        blocker = engine.agents[2]
        head.state = AgentState.TO_TABLE
        head.cell = (10, 10)
        head.target_cells = {(10, 9)}
        head.stuck_ticks = 12
        blocker.state = AgentState.WAITING_GROUP
        blocker.cell = (10, 9)
        blocker.target_cells = {blocker.cell}
        for cell in [(9, 9), (11, 9), (10, 8)]:
            engine.grid.blocked_cells.add(cell)

        plan = engine._plan_local_repair_with_reservations(
            center=(10, 9),
            agent_ids=[1, 2],
            horizon=3,
            radius=2,
        )

        self.assertNotIn(2, plan)
        occupied_at_first_tick = [path[0] for path in plan.values()]
        self.assertEqual(len(occupied_at_first_tick), len(set(occupied_at_first_tick)))

    # 验证局部 repair 会把占住别人 table approach slot 的阻塞者让出，而不是把原地等待作为有效计划。
    def test_local_repair_does_not_keep_non_owner_in_table_approach_slot(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(214))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        owner = engine.agents[1]
        blocker = engine.agents[2]
        target = (10, 9)
        owner.state = AgentState.TO_TABLE
        owner.cell = (10, 11)
        owner.table_index = 0
        owner.assigned_table_approach_cell = target
        owner.target_cells = {target}
        owner.stuck_ticks = 12
        blocker.state = AgentState.WAITING_GROUP
        blocker.cell = target
        blocker.target_cells = {target}

        plan = engine._plan_local_repair_with_reservations(
            center=target,
            agent_ids=[1, 2],
            horizon=3,
            radius=2,
        )

        self.assertIn(2, plan)
        self.assertNotEqual(plan[2][0], target)
        for path in plan.values():
            for cell in path:
                if cell == target:
                    self.assertEqual(path, plan[1])

    # 验证非队首不会被 repair plan 推进 service/head 保留区。
    def test_local_repair_does_not_push_non_head_into_service_or_head_slot(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(216))
        people = [student(1), student(2), student(3)]
        engine.spawn_arrivals(people, door_index=0)
        engine.set_window_physical_queue(0, [1, 2])
        service_cell = engine.grid.service_cells[0]
        head_slot = engine.grid.queue_cells_by_window[0][0]
        non_head = engine.agents[2]
        non_head.cell = (service_cell[0], service_cell[1] + 2)
        non_head.state = AgentState.QUEUEING
        non_head.target_cells = {service_cell}
        non_head.stuck_ticks = 12
        walker = engine.agents[3]
        walker.state = AgentState.TO_WINDOW
        walker.desired_window_index = 0
        walker.assigned_queue_slot_index = 2
        walker.cell = (head_slot[0] + 1, head_slot[1])
        walker.target_cells = {head_slot}
        walker.stuck_ticks = 12

        plan = engine._plan_local_repair_with_reservations(
            center=head_slot,
            agent_ids=[2, 3],
            horizon=4,
            radius=4,
        )

        forbidden = {service_cell}
        for agent_id, path in plan.items():
            if agent_id != 1:
                self.assertTrue(forbidden.isdisjoint(path))

    # 验证取餐后等待同伴的 agent 不会把窗口 head slot 当成长期等待点。
    def test_waiting_group_retargets_away_from_window_reserved_area(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(217))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        head_slot = engine.grid.queue_cells_by_window[0][0]
        engine.agents[1].cell = head_slot
        engine.set_agent_target_window(2, 0)

        engine.set_agent_waiting_group(1)

        self.assertEqual(engine.agents[1].state, AgentState.WAITING_GROUP)
        self.assertNotEqual(engine.agents[1].target_cells, {head_slot})
        self.assertNotIn(head_slot, engine.agents[1].target_cells)
        target = next(iter(engine.agents[1].target_cells))
        service_cell = engine.grid.service_cells[0]
        self.assertGreater(abs(target[0] - service_cell[0]) + abs(target[1] - service_cell[1]), 3)
        self.assertGreater(abs(target[0] - head_slot[0]) + abs(target[1] - head_slot[1]), 2)

    # 验证局部安全格都被占住时，等待同伴者会继续向外找安全等待点，而不是退回窗口保留区。
    def test_waiting_group_searches_beyond_local_radius_before_staying_near_window(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(218))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        current = engine.grid.queue_cells_by_window[0][0]
        agent.cell = current
        agent.path_cells = [current]

        local_radius = max(6, engine.local_repair_radius * 2)
        blocker_id = 1000
        for col in range(engine.grid.cols):
            for row in range(engine.grid.rows):
                cell = (col, row)
                if abs(cell[0] - current[0]) + abs(cell[1] - current[1]) > local_radius:
                    continue
                if not engine._is_safe_waiting_group_cell(agent, cell, occupied=set()):
                    continue
                engine.agents[blocker_id] = PedestrianAgent(
                    agent_id=blocker_id,
                    student_id=blocker_id,
                    party_id=blocker_id,
                    state=AgentState.WAITING_GROUP,
                    cell=cell,
                    target_type="group",
                    target_id=blocker_id,
                    target_cells={cell},
                    path_cells=[cell],
                )
                blocker_id += 1

        engine.set_agent_waiting_group(1)

        target = next(iter(engine.agents[1].target_cells))
        occupied = {
            other.cell
            for other in engine.agents.values()
            if other.student_id != 1
        }
        self.assertNotEqual(target, current)
        self.assertGreater(abs(target[0] - current[0]) + abs(target[1] - current[1]), local_radius)
        self.assertTrue(engine._is_safe_waiting_group_cell(engine.agents[1], target, occupied))

    # 验证等待同伴者不会选择贴在窗口前排队车道旁、被已分配 queue slot 包住的目标。
    def test_waiting_group_target_avoids_window_queue_front_band(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(219))
        people = [student(student_id) for student_id in range(1, 13)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [person.student_id for person in people[1:11]])
        agent = engine.agents[1]
        current = queue_slots[5]
        agent.cell = current
        agent.path_cells = [current]

        engine.set_agent_waiting_group(1)

        target = next(iter(engine.agents[1].target_cells))
        service = engine.grid.service_cells[0]
        head_slot = queue_slots[0]
        normal = (
            max(-1, min(1, head_slot[0] - service[0])),
            max(-1, min(1, head_slot[1] - service[1])),
        )
        forward = (target[0] - service[0]) * normal[0] + (target[1] - service[1]) * normal[1]

        self.assertGreater(forward, 6)
        self.assertGreater(abs(target[0] - service[0]) + abs(target[1] - service[1]), 3)

    # 验证等待同伴者也避开整条排队车道旁边，避免站在队伍边上堵住通道。
    def test_waiting_group_safe_cell_rejects_queue_lane_side_area(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(225))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        queue_slots = engine.grid.queue_cells_by_window[0]
        side_cell = (queue_slots[8][0] + 1, queue_slots[8][1])

        self.assertTrue(engine._is_walkable_cell(side_cell))
        self.assertFalse(engine._is_safe_waiting_group_cell(agent, side_cell, occupied=set()))

    # 验证等待同伴/等座学生不会从外部进入窗口服务带，避免停在窗口前阻塞排队者。
    def test_waiting_group_cannot_enter_window_service_buffer_from_outside(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(2261))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        service = engine.grid.service_cells[0]
        buffer_cell = (service[0] - 6, service[1])
        outside_cell = (service[0] - 8, service[1])
        agent.state = AgentState.WAITING_GROUP
        agent.cell = outside_cell

        self.assertTrue(engine._is_walkable_cell(outside_cell))
        self.assertTrue(engine._is_walkable_cell(buffer_cell))
        self.assertFalse(engine._is_near_window_service_or_head(outside_cell))
        self.assertTrue(engine._is_near_window_service_or_head(buffer_cell))
        self.assertFalse(engine.can_agent_enter_cell(agent, buffer_cell))

    # 验证已经在服务带里的等待者仍能向外撤离，防止禁入规则把历史状态卡死。
    def test_waiting_group_can_step_out_of_window_service_buffer(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(2262))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        agent = engine.agents[1]
        service = engine.grid.service_cells[0]
        escape_cell = (service[0] - 1, service[1])
        agent.state = AgentState.WAITING_GROUP
        agent.cell = service

        self.assertTrue(engine._is_near_window_service_or_head(service))
        self.assertTrue(engine._is_near_window_service_or_head(escape_cell))
        self.assertTrue(engine.can_agent_enter_cell(agent, escape_cell))

    # 验证刚取完餐、仍在服务带内撤离的等待者不会挡住下一名队头。
    def test_waiting_group_in_service_buffer_does_not_block_window_queue(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(2263))
        people = [student(1), student(2)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        head_slot = queue_slots[0]
        next_slot = queue_slots[1]
        engine.set_window_physical_queue(0, [1])
        queue_agent = engine.agents[1]
        queue_agent.cell = next_slot
        blocker = engine.agents[2]
        blocker.state = AgentState.WAITING_GROUP
        blocker.cell = head_slot
        blocker.target_cells = {(head_slot[0] - 6, head_slot[1])}

        occupied_by = {
            other.cell: other
            for other in engine.agents.values()
            if engine._occupies_walkable_cell(other)
        }
        occupied = engine._occupied_cells_for_agent(queue_agent, occupied_by, set(occupied_by))

        self.assertTrue(engine._is_near_window_service_or_head(blocker.cell))
        self.assertNotIn(blocker.cell, occupied)
        self.assertLess(
            engine._movement_conflict_priority(queue_agent),
            engine._movement_conflict_priority(blocker),
        )

        engine._movement_micro_step(current_time_sec=0, duration_sec=1)

        self.assertEqual(queue_agent.cell, head_slot)
        self.assertEqual(queue_agent.state, AgentState.QUEUEING)
        self.assertNotEqual(blocker.cell, head_slot)

    # 验证等待同伴者当前位置虽然合法但周围拥挤时，会迁移到更低密度的等待点。
    def test_waiting_group_prefers_lower_density_waiting_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(226))
        people = [student(student_id) for student_id in range(1, 8)]
        engine.spawn_arrivals(people, door_index=0)
        agent = engine.agents[1]
        current = (5, 8)
        agent.cell = current
        agent.path_cells = [current]
        blocker_cells = [(4, 8), (6, 8), (5, 7), (5, 9), (4, 7), (6, 9)]
        for blocker_id, cell in enumerate(blocker_cells, start=1000):
            engine.agents[blocker_id] = PedestrianAgent(
                agent_id=blocker_id,
                student_id=blocker_id,
                party_id=blocker_id,
                state=AgentState.WAITING_GROUP,
                cell=cell,
                target_type="group",
                target_id=blocker_id,
                target_cells={cell},
                path_cells=[cell],
            )

        engine.set_agent_waiting_group(1)

        target = next(iter(agent.target_cells))
        occupied = {
            other.cell
            for other in engine.agents.values()
            if other.student_id != agent.student_id
            and other.state not in {AgentState.SEATED, AgentState.EXITED}
        }
        density = DensityField.from_occupied_cells(occupied, engine.grid, radius=2)
        self.assertNotEqual(target, current)
        self.assertLess(density.density(target), density.density(current))

    # 验证同一窗口的后位学生可以穿过前序队列槽位，FIFO 仍由目标槽维护。
    def test_same_window_agent_can_cross_assigned_queue_slot(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(221))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1, 2, 3])
        owner = engine.agents[2]
        owner.cell = (queue_slots[1][0] + 4, queue_slots[1][1] + 4)
        mover = engine.agents[3]
        mover.cell = (queue_slots[1][0] + 1, queue_slots[1][1])
        mover.target_cells = {queue_slots[2]}
        mover.assigned_queue_slot_index = 2
        mover.desired_window_index = 0
        mover.state = AgentState.TO_WINDOW

        owner.cell = queue_slots[1]
        self.assertTrue(engine.can_agent_enter_cell(mover, queue_slots[1]))
        owner.cell = (queue_slots[1][0] + 4, queue_slots[1][1] + 4)
        self.assertTrue(engine.can_agent_enter_cell(mover, queue_slots[1]))

    # 验证同一队列前移时，后位学生可以跟进前位学生将让出的队列格。
    def test_same_window_queue_agents_can_follow_forward_in_lane(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(222))
        people = [student(student_id) for student_id in range(1, 3)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1, 2])
        head = engine.agents[1]
        tail = engine.agents[2]
        head.cell = queue_slots[1]
        head.target_cells = {queue_slots[0]}
        head.assigned_queue_slot_index = 0
        head.desired_window_index = 0
        head.state = AgentState.TO_WINDOW
        tail.cell = queue_slots[2]
        tail.target_cells = {queue_slots[1]}
        tail.assigned_queue_slot_index = 1
        tail.desired_window_index = 0
        tail.state = AgentState.TO_WINDOW
        occupied_by = {agent.cell: agent for agent in engine.agents.values()}

        occupied = engine._occupied_cells_for_agent(tail, occupied_by, set(occupied_by))

        self.assertNotIn(head.cell, occupied)

    # 验证尚未到达队尾目标的去窗口行人可以借过队列槽位，但目标仍在分配的队尾。
    def test_window_walker_can_cross_front_queue_slot_before_tail_assignment(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(224))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1, 2])
        engine.set_agent_target_window(3, 0)
        owner = engine.agents[2]
        owner.cell = (queue_slots[1][0] + 4, queue_slots[1][1] + 4)
        walker = engine.agents[3]
        walker.cell = (queue_slots[1][0] + 1, queue_slots[1][1])
        walker.state = AgentState.TO_WINDOW

        self.assertTrue(engine.can_agent_enter_cell(walker, queue_slots[1]))
        self.assertTrue(engine.can_agent_enter_cell(walker, queue_slots[2]))
        self.assertEqual(walker.target_cells, {queue_slots[2]})

    # 验证去窗口行人在队列车道尾部附近时优先进入自己的分配槽，而不是横向滞留。
    def test_to_window_agent_prefers_entering_assigned_tail_queue_slot_under_density(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(223))
        person = student(1)
        engine.spawn_arrivals([person], door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        agent = engine.agents[1]
        agent.state = AgentState.TO_WINDOW
        agent.desired_window_index = 0
        agent.assigned_queue_slot_index = 8
        agent.target_cells = {queue_slots[8]}
        agent.cell = (queue_slots[8][0] + 1, queue_slots[8][1])
        agent.path_cells = [agent.cell]
        blockers = [
            (queue_slots[8][0], queue_slots[8][1] - 1),
            (queue_slots[8][0], queue_slots[8][1] + 1),
            (queue_slots[8][0] - 1, queue_slots[8][1]),
            (queue_slots[8][0] + 1, queue_slots[8][1] + 1),
        ]
        for blocker_id, cell in enumerate(blockers, start=1000):
            engine.agents[blocker_id] = PedestrianAgent(
                agent_id=blocker_id,
                student_id=blocker_id,
                party_id=blocker_id,
                state=AgentState.TO_WINDOW,
                cell=cell,
                target_cells={cell},
                path_cells=[cell],
            )
        occupied = {
            other.cell
            for other in engine.agents.values()
            if other.student_id != agent.student_id
        }
        density = DensityField.from_occupied_cells(occupied, engine.grid, radius=1)

        intended, _cost = engine._intended_move(agent, occupied, density, density_radius=1)

        self.assertEqual(intended, queue_slots[8])

    # 验证队列成员已经在本队车道内时，会优先沿车道向前补空槽，避免队伍断裂。
    def test_queueing_agent_compacts_forward_even_when_forward_slot_is_dense(self):
        config = movement_config(
            floor_density_weight=8.0,
            congestion_density_threshold=0,
            floor_static_weight=1.0,
            floor_randomness=0.0,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(227))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [1, 2, 3])
        agent = engine.agents[3]
        agent.cell = queue_slots[5]
        agent.path_cells = [agent.cell]
        agent.state = AgentState.QUEUEING
        agent.desired_window_index = 0
        agent.assigned_queue_slot_index = 2
        agent.target_cells = {queue_slots[2]}
        density = DensityField(densities={queue_slots[4]: 8})

        intended, _cost = engine._intended_move(agent, occupied_cells=set(), density=density, density_radius=1)

        self.assertEqual(intended, queue_slots[4])

    # 验证等待目标本身仍安全时，不会仅因邻域密度偏高就每个 tick 重新全图选点。
    def test_waiting_group_keeps_safe_dense_target_until_stuck(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(229))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        agent = engine.agents[1]
        target = (5, 8)
        self.assertTrue(engine._is_safe_waiting_group_cell(agent, target, occupied=set()))
        agent.state = AgentState.WAITING_GROUP
        agent.cell = target
        agent.target_cells = {target}
        engine.agents[2].state = AgentState.TO_WINDOW
        engine.agents[2].cell = (4, 8)
        engine.agents[3].state = AgentState.TO_WINDOW
        engine.agents[3].cell = (6, 8)
        original = engine._waiting_group_target_cell

        def fail_if_retargeted(_agent):
            raise AssertionError("safe waiting target should not be recomputed")

        engine._waiting_group_target_cell = fail_if_retargeted
        try:
            engine._retarget_waiting_group_agents()
        finally:
            engine._waiting_group_target_cell = original

        self.assertEqual(agent.target_cells, {target})

    # 验证同一 tick 内等待组重定位共享密度场，避免按等待者人数重复建场。
    def test_waiting_group_retarget_builds_density_once_for_stable_targets(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(230))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        targets: list[tuple[int, int]] = []
        probe = engine.agents[1]
        for cell in sorted(engine.in_bounds_cells, key=lambda item: (item[1], item[0])):
            if not engine._is_safe_waiting_group_cell(probe, cell, occupied=set()):
                continue
            if any(max(abs(cell[0] - existing[0]), abs(cell[1] - existing[1])) <= 3 for existing in targets):
                continue
            targets.append(cell)
            if len(targets) == len(people):
                break
        self.assertEqual(len(targets), len(people))
        for person, target in zip(people, targets):
            agent = engine.agents[person.student_id]
            self.assertTrue(engine._is_safe_waiting_group_cell(agent, target, occupied=set()))
            agent.state = AgentState.WAITING_GROUP
            agent.cell = target
            agent.target_cells = {target}
        original = engine_module.DensityField.from_occupied_cells
        calls = 0

        def counted_from_occupied_cells(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        engine_module.DensityField.from_occupied_cells = counted_from_occupied_cells
        try:
            engine._retarget_waiting_group_agents()
        finally:
            engine_module.DensityField.from_occupied_cells = original

        self.assertEqual(calls, 1)

    # 验证等待者重选目标后会清零停滞计数，避免下一 tick 立刻重复全图重算。
    def test_waiting_group_retarget_resets_stuck_ticks(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(231))
        people = [student(student_id) for student_id in range(1, 4)]
        engine.spawn_arrivals(people, door_index=0)
        agent = engine.agents[1]
        target = (5, 8)
        replacement = (8, 8)
        if not engine._is_safe_waiting_group_cell(agent, target, occupied=set()):
            target = next(
                cell
                for cell in sorted(engine.in_bounds_cells, key=lambda item: (item[1], item[0]))
                if engine._is_safe_waiting_group_cell(agent, cell, occupied=set())
            )
            replacement = next(
                cell
                for cell in sorted(engine.in_bounds_cells, key=lambda item: (item[1], item[0]))
                if cell != target
                and engine._is_safe_waiting_group_cell(agent, cell, occupied=set())
                and max(abs(cell[0] - target[0]), abs(cell[1] - target[1])) > 3
            )
        agent.state = AgentState.WAITING_GROUP
        agent.cell = target
        agent.target_cells = {target}
        agent.stuck_ticks = engine.local_repair_after_stuck_ticks
        engine.agents[2].state = AgentState.TO_WINDOW
        engine.agents[2].cell = (target[0] - 1, target[1])
        engine.agents[3].state = AgentState.TO_WINDOW
        engine.agents[3].cell = (target[0] + 1, target[1])
        original = engine._waiting_group_target_cell
        engine._waiting_group_target_cell = lambda _agent: replacement
        try:
            engine._retarget_waiting_group_agents()
        finally:
            engine._waiting_group_target_cell = original

        self.assertEqual(agent.target_cells, {replacement})
        self.assertEqual(agent.stuck_ticks, 0)

    # 验证等待同伴者已停在后来变成不安全的窗口前沿时，会在 tick 前重新选择停靠点。
    def test_waiting_group_retargets_existing_unsafe_queue_front_target(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(220))
        people = [student(student_id) for student_id in range(1, 13)]
        engine.spawn_arrivals(people, door_index=0)
        queue_slots = engine.grid.queue_cells_by_window[0]
        engine.set_window_physical_queue(0, [person.student_id for person in people[1:11]])
        agent = engine.agents[1]
        unsafe = queue_slots[4]
        agent.cell = unsafe
        agent.path_cells = [unsafe]
        agent.state = AgentState.WAITING_GROUP
        agent.target_type = "group"
        agent.target_id = agent.party_id
        agent.target_cells = {unsafe}

        engine._retarget_waiting_group_agents()

        target = next(iter(agent.target_cells))
        occupied = {
            other.cell
            for other in engine.agents.values()
            if other.student_id != agent.student_id
        }
        self.assertNotEqual(target, unsafe)
        self.assertFalse(engine._is_near_window_service_or_head(target))
        self.assertTrue(engine._is_safe_waiting_group_cell(agent, target, occupied))

    # 验证 6 窗口默认布局下 queue_cells 是连续、可走、不跨窗口重叠的物理队列车道。
    def test_default_layout_window_queue_cells_are_continuous_and_disjoint(self):
        config = SimulationConfigData(
            num_windows=6,
            num_seats=160,
            movement_model="advanced_floor_field",
            floor_randomness=0.0,
        )
        engine = PedestrianEngine(_default_layout(config), config, random.Random(215))
        all_slots: set[tuple[int, int]] = set()
        all_service_cells = set(engine.grid.service_cells.values())

        for window_index, queue_cells in engine.grid.queue_cells_by_window.items():
            with self.subTest(window=window_index):
                self.assertGreaterEqual(len(queue_cells), 24)
                service_cell = engine.grid.service_cells[window_index]
                self.assertLessEqual(
                    abs(queue_cells[0][0] - service_cell[0]) + abs(queue_cells[0][1] - service_cell[1]),
                    2,
                )
                head_slot = queue_cells[0]
                normal = (
                    max(-1, min(1, head_slot[0] - service_cell[0])),
                    max(-1, min(1, head_slot[1] - service_cell[1])),
                )
                side = (normal[1], normal[0])
                front_laterals = [
                    (slot[0] - service_cell[0]) * side[0] + (slot[1] - service_cell[1]) * side[1]
                    for slot in queue_cells[: min(8, len(queue_cells))]
                ]
                self.assertLessEqual(len(set(front_laterals)), 2)
                self.assertNotIn(service_cell, queue_cells)
                for slot in queue_cells:
                    self.assertTrue(is_walkable(slot, engine.grid))
                    self.assertNotIn(slot, all_service_cells)
                    self.assertNotIn(slot, all_slots)
                for previous, current in zip(queue_cells, queue_cells[1:]):
                    self.assertLessEqual(
                        abs(previous[0] - current[0]) + abs(previous[1] - current[1]),
                        2,
                    )
                all_slots.update(queue_cells)

    # 验证窄队列 lane 被合法障碍挡住时，会退回到更宽但仍可达的队列 lane。
    def test_queue_cells_fall_back_to_wider_reachable_lane_when_narrow_lane_blocked(self):
        service = (5, 1)
        blocked = {
            (col, row)
            for col in range(service[0] - 2, service[0] + 3)
            for row in range(service[1] + 1, 12)
        }
        grid = GridData(cell_size=1.0, cols=12, rows=12, blocked_cells=blocked)

        queue_cells = _queue_cells_from_service(
            service,
            normal=(0, 1),
            grid=grid,
            forbidden=set(),
            target_count=8,
        )

        self.assertGreaterEqual(len(queue_cells), 8)
        self.assertTrue(any(abs(cell[0] - service[0]) > 2 for cell in queue_cells))
        self.assertNotIn(service, queue_cells)
        for cell in queue_cells:
            self.assertTrue(is_walkable(cell, grid))
        for previous, current in zip(queue_cells, queue_cells[1:]):
            self.assertEqual(abs(previous[0] - current[0]) + abs(previous[1] - current[1]), 1)

    # 验证 avg_stuck_ticks 只统计真正应该移动的状态。
    def test_movement_metrics_avg_stuck_ticks_ignores_stationary_states(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(212))
        people = [student(index) for index in range(1, 6)]
        engine.spawn_arrivals(people, door_index=0)
        stationary_states = [
            AgentState.QUEUEING,
            AgentState.WAITING_GROUP,
            AgentState.SEATED,
            AgentState.EXITED,
        ]
        for agent, state in zip(list(engine.agents.values())[:4], stationary_states):
            agent.state = state
            agent.stuck_ticks = 100
        mover = engine.agents[5]
        mover.state = AgentState.TO_WINDOW
        mover.stuck_ticks = 2

        metrics = movement_metrics(engine.agents, tick_seconds=5, max_density=0)

        self.assertEqual(metrics.avg_stuck_ticks, 2.0)

    # 验证路径绕行比按实际步行格数 / 起终点直线格距统计。
    def test_movement_metrics_reports_walking_distance_ratio(self):
        agent = PedestrianAgent(
            agent_id=1,
            student_id=1,
            party_id=1,
            state=AgentState.TO_TABLE,
            cell=(3, 4),
            path_cells=[(0, 0), (3, 0), (3, 4)],
            walking_distance_cells=7,
            walking_time_seconds=10.0,
        )

        metrics = movement_metrics({1: agent}, tick_seconds=5, max_density=0)

        self.assertEqual(metrics.avg_walking_distance_ratio, 1.4)

    # 验证多目标行程优先按目标段统计绕行比，而不是用整个生命周期首尾直线距离。
    def test_movement_metrics_prefers_segment_distance_ratios(self):
        agent = PedestrianAgent(
            agent_id=1,
            student_id=1,
            party_id=1,
            state=AgentState.TO_TABLE,
            cell=(0, 10),
            path_cells=[(0, 0), (10, 0), (10, 10), (0, 10)],
            walking_distance_cells=30,
            walking_time_seconds=10.0,
            movement_leg_distance_ratios=[1.0, 1.0],
            movement_leg_start_cell=(10, 10),
            movement_leg_distance_cells=10.0,
        )

        metrics = movement_metrics({1: agent}, tick_seconds=5, max_density=0)

        self.assertEqual(metrics.avg_walking_distance_ratio, 1.0)

    # 验证前方堵住时，停滞惩罚不会诱导 agent 退回上一格形成往返振荡。
    def test_intended_move_waits_instead_of_backtracking_when_forward_is_blocked(self):
        config = movement_config(
            floor_density_weight=0.0,
            floor_dynamic_weight=0.0,
            floor_wall_weight=0.0,
            floor_inertia_weight=0.25,
            floor_randomness=0.0,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1402))
        people = [student(1), student(2), student(3), student(4), student(5)]
        engine.spawn_arrivals(people, door_index=0)
        mover = engine.agents[1]
        mover.cell = (5, 5)
        mover.previous_cell = (5, 6)
        mover.state = AgentState.TO_TABLE
        mover.target_cells = {(5, 3)}
        mover.stuck_ticks = 40
        blockers = {
            2: (5, 4),
            3: (4, 5),
            4: (6, 5),
        }
        for student_id, cell in blockers.items():
            blocker = engine.agents[student_id]
            blocker.cell = cell
            blocker.state = AgentState.SERVICE
            blocker.target_cells = {cell}
        occupied = {agent.cell for agent in engine.agents.values() if agent.student_id != mover.student_id}
        density = DensityField.from_occupied_cells(occupied | {mover.cell}, engine.grid, radius=1)

        intended, _cost = engine._intended_move(
            mover,
            occupied_cells=occupied,
            density=density,
            density_radius=1,
        )

        self.assertEqual(intended, mover.cell)

    # 验证拥堵感知路由也不会把上一格当作非进展绕行的第一步。
    def test_congestion_aware_route_does_not_backtrack_when_forward_is_blocked(self):
        config = movement_config(
            floor_density_weight=6.0,
            floor_dynamic_weight=0.0,
            floor_wall_weight=0.0,
            floor_inertia_weight=0.25,
            floor_randomness=0.0,
        )
        engine = PedestrianEngine(engine_layout(), config, random.Random(1403))
        people = [student(1), student(2), student(3), student(4)]
        engine.spawn_arrivals(people, door_index=0)
        mover = engine.agents[1]
        mover.cell = (5, 5)
        mover.previous_cell = (5, 6)
        mover.state = AgentState.TO_WINDOW
        mover.desired_window_index = 0
        mover.target_cells = {(5, 3)}
        mover.stuck_ticks = 40
        blockers = {
            2: (5, 4),
            3: (4, 5),
            4: (6, 5),
        }
        for student_id, cell in blockers.items():
            blocker = engine.agents[student_id]
            blocker.cell = cell
            blocker.state = AgentState.SERVICE
            blocker.target_cells = {cell}
        occupied = {agent.cell for agent in engine.agents.values() if agent.student_id != mover.student_id}
        density = DensityField.from_occupied_cells(occupied | {mover.cell}, engine.grid, radius=1)

        intended, _cost = engine._intended_move(
            mover,
            occupied_cells=occupied,
            density=density,
            density_radius=1,
        )

        self.assertEqual(intended, mover.cell)

    # 验证借过不会挤开正在服务、已入座或已离开的非通道对象。
    def test_to_table_borrow_does_not_displace_service_agent(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(22))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        passer = engine.agents[1]
        service = engine.agents[2]
        passer.state = AgentState.TO_TABLE
        passer.cell = (10, 10)
        passer.target_cells = {(10, 8)}
        passer.stuck_ticks = 8
        service.state = AgentState.SERVICE
        service.cell = (10, 9)
        service.target_cells = {service.cell}

        engine.tick(0)

        self.assertNotEqual(passer.cell, (10, 9))
        self.assertEqual(service.cell, (10, 9))

    # 验证空目标格被多人竞争时，长期停滞的入座行人获得借过优先权。
    def test_stuck_to_table_agent_gets_right_of_way_in_cell_conflict(self):
        engine = PedestrianEngine(engine_layout(), movement_config(), random.Random(23))
        people = [student(1, party_id=1), student(2, party_id=2)]
        engine.spawn_arrivals(people, door_index=0)
        passer = engine.agents[1]
        queueing = engine.agents[2]
        passer.state = AgentState.TO_TABLE
        passer.cell = (10, 10)
        passer.target_cells = {(10, 8)}
        passer.stuck_ticks = 8
        queueing.state = AgentState.QUEUEING
        queueing.cell = (9, 9)
        queueing.target_cells = {(10, 9)}

        engine.tick(0)

        self.assertIn((10, 9), passer.path_cells)
        self.assertEqual(passer.cell, (10, 8))
        self.assertNotEqual(queueing.cell, passer.cell)


if __name__ == "__main__":
    unittest.main()
