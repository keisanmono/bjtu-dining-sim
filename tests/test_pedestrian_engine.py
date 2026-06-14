# 文件说明：高级行人引擎测试，覆盖 CA tick、冲突解决、密度成本和可复现性。

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pedestrian.agents import AgentState
import app.pedestrian.fields as fields_module
from app.pedestrian.fields import DensityField
from app.pedestrian.engine import PedestrianEngine
from app.pedestrian.grid import neighbors
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
            agent.state = AgentState.TO_WINDOW
            agent.target_cells = {target}

        engine.tick(0)

        cells = [agent.cell for agent in engine.agents.values()]
        self.assertEqual(len(cells), len(set(cells)))
        self.assertIn(target, cells)

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

        self.assertLessEqual(calls["count"], 2)

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

        self.assertEqual(engine.agents[mover.student_id].cell, (13, 6))
        self.assertEqual([item["student_id"] for item in engine.agent_snapshots()], [mover.student_id])

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

        self.assertEqual(passer.cell, (10, 9))
        self.assertIn(blocker.cell, {(9, 9), (11, 9), (10, 10)})
        self.assertNotEqual(passer.cell, blocker.cell)

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

        self.assertEqual(passer.cell, (10, 9))
        self.assertNotEqual(queueing.cell, passer.cell)


if __name__ == "__main__":
    unittest.main()
