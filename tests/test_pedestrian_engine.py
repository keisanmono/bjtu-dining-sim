# 文件说明：高级行人引擎测试，覆盖 CA tick、冲突解决、密度成本和可复现性。

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pedestrian.agents import AgentState
from app.pedestrian.engine import PedestrianEngine
from app.pedestrian.grid import neighbors
from app.simulation import (
    DiningLayoutData,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
    Student,
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


if __name__ == "__main__":
    unittest.main()
