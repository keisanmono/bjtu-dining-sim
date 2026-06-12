# 文件说明：Floor Field / CA 测试，覆盖网格、静态场、动态场和避障移动。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.floor_field import build_static_floor_field, next_cell_by_floor_field
from app.pedestrian.fields import DynamicField, build_static_field
from app.pedestrian.grid import (
    cell_to_point,
    grid_from_layout,
    is_walkable,
    point_to_cell,
)


class FloorFieldTests(unittest.TestCase):
    # 验证网格粒度必须为正数，避免除零或负网格尺寸。
    def test_grid_from_layout_rejects_non_positive_cell_size(self):
        layout = {"tables": []}

        with self.assertRaises(ValueError):
            grid_from_layout(layout, cell_size=0)
        with self.assertRaises(ValueError):
            grid_from_layout(layout, cell_size=-5)

    # 验证餐桌 footprint 会被标记为不可通行，周围一圈可作为入座接近格。
    def test_grid_from_layout_marks_table_blocked_and_builds_approach_cells(self):
        layout = {
            "tables": [
                {"id": "T1", "x": 120, "y": 180, "capacity": 4},
            ],
            "windows": [],
            "doors": [{"id": "D1", "x": 24, "y": 120, "wall_side": "left"}],
        }

        grid = grid_from_layout(layout, cell_size=12)
        table_cell = point_to_cell({"x": 120, "y": 180}, grid)

        self.assertIn(table_cell, grid.blocked_cells)
        self.assertFalse(is_walkable(table_cell, grid))
        self.assertIn(0, grid.table_approach_cells)
        self.assertTrue(grid.table_approach_cells[0])
        self.assertTrue(all(is_walkable(cell, grid) for cell in grid.table_approach_cells[0]))

    # 验证窗口会生成服务格和物理队列格，入口/目标格不会落在 blocked cell 内。
    def test_grid_from_layout_builds_service_queue_and_reachable_targets(self):
        layout = {
            "doors": [{"id": "D1", "x": 24, "y": 120, "wall_side": "left"}],
            "windows": [{"id": "W1", "x": 160, "y": 24, "wall_side": "top"}],
            "tables": [{"id": "T1", "x": 160, "y": 96, "capacity": 4}],
        }

        grid = grid_from_layout(layout, cell_size=12)
        service_cell = grid.service_cells[0]
        queue_cells = grid.queue_cells_by_window[0]

        self.assertTrue(is_walkable(service_cell, grid))
        self.assertGreaterEqual(len(queue_cells), 2)
        self.assertEqual(queue_cells[0], service_cell)
        self.assertTrue(all(is_walkable(cell, grid) for cell in queue_cells))
        self.assertTrue(all(is_walkable(cell, grid) for cell in grid.door_cells.values()))

    # 验证静态 floor field 能绕过餐桌障碍到达目标。
    def test_static_field_routes_around_blocked_table(self):
        layout = {
            "doors": [{"id": "D1", "x": 24, "y": 180, "wall_side": "left"}],
            "windows": [],
            "tables": [{"id": "T1", "x": 120, "y": 180, "capacity": 6}],
        }
        grid = grid_from_layout(layout, cell_size=12)
        start = point_to_cell({"x": 48, "y": 180}, grid)
        target = point_to_cell({"x": 240, "y": 180}, grid)
        field = build_static_field(grid, {target})

        self.assertIn(start, field)
        self.assertGreater(field[start], 0)
        blocked_between = point_to_cell({"x": 120, "y": 180}, grid)
        self.assertNotIn(blocked_between, field)

    # 验证动态场每 tick 会衰减并向邻域扩散。
    def test_dynamic_field_decay_and_diffusion_update_values(self):
        grid = grid_from_layout({"doors": [], "windows": [], "tables": []}, cell_size=20)
        field = DynamicField(decay=0.5, diffusion=0.25)
        source = (4, 4)

        field.deposit(source, amount=8.0)
        field.step(grid)

        self.assertGreater(field.values[source], 0)
        self.assertLess(field.values[source], 8.0)
        self.assertTrue(any(cell != source and value > 0 for cell, value in field.values.items()))
        self.assertLess(sum(field.values.values()), 8.0)

    # 验证静态场下一步选择不会进入 blocked cell。
    def test_next_cell_by_floor_field_does_not_step_into_blocked_cell(self):
        layout = {
            "doors": [],
            "windows": [],
            "tables": [{"id": "T1", "x": 80, "y": 80, "capacity": 4}],
        }
        grid = grid_from_layout(layout, cell_size=12)
        target_point = cell_to_point((10, 6), grid)
        field = build_static_floor_field(layout, target_point)
        next_cell = next_cell_by_floor_field(agent=point_to_cell({"x": 48, "y": 80}, grid), grid=field, target=target_point)

        self.assertNotIn(next_cell, field["blocked"])

    # 验证目标格即使位于桌面 footprint 内，兼容包装也会改用附近可达格作为终点。
    def test_next_cell_can_enter_blocked_target_cell(self):
        layout = {
            "tables": [
                {"id": "T1", "x": 50, "y": 50, "capacity": 2},
            ]
        }
        target = {"x": 50, "y": 50}
        field = build_static_floor_field(layout, target)

        next_cell = next_cell_by_floor_field(agent=(4, 1), grid=field, target=target)

        self.assertNotIn(field["target_cell"], field["blocked"])
        self.assertEqual(next_cell, field["target_cell"])


if __name__ == "__main__":
    unittest.main()
