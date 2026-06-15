# 文件说明：Floor Field / CA 测试，覆盖网格、静态场、动态场和避障移动。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.pedestrian.fields as fields_module
from app.floor_field import build_static_floor_field, next_cell_by_floor_field
from app.pedestrian.fields import DynamicField, build_static_field
from app.pedestrian.grid import (
    cell_to_point,
    grid_from_layout,
    is_walkable,
    neighbors,
    point_to_cell,
)


def _large_service_corridor_layout() -> dict:
    capacities = [2, 4, 4, 6]
    return {
        "floor": {"x": 24, "y": 24, "width": 312, "height": 760},
        "doors": [{"id": "D1", "x": 24, "y": 100, "wall_side": "left"}],
        "windows": [
            {"id": "W1", "x": 70, "y": 24, "wall_side": "top"},
            {"id": "W2", "x": 130, "y": 24, "wall_side": "top"},
            {"id": "W3", "x": 190, "y": 24, "wall_side": "top"},
            {"id": "W4", "x": 250, "y": 24, "wall_side": "top"},
        ],
        "tables": [
            {
                "id": f"T{index + 1}",
                "x": 100 + (index % 3) * 80,
                "y": 184 + (index // 3) * 50,
                "capacity": capacities[index % len(capacities)],
            }
            for index in range(31)
        ],
    }


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
        self.assertNotIn(service_cell, queue_cells)
        self.assertLessEqual(
            abs(queue_cells[0][0] - service_cell[0]) + abs(queue_cells[0][1] - service_cell[1]),
            1,
        )
        self.assertTrue(all(is_walkable(cell, grid) for cell in queue_cells))
        self.assertTrue(all(is_walkable(cell, grid) for cell in grid.door_cells.values()))

    # 验证密集默认布局下，窗口队列不能占用入口通道，否则室内排队会被错误挤到门外。
    def test_window_queue_targets_do_not_block_ingress_cells(self):
        layout = {
            "floor": {"x": 0, "y": 0, "width": 360, "height": 640},
            "doors": [{"id": "D1", "x": 20, "y": 80, "wall_side": "left"}],
            "windows": [
                {"id": "W1", "x": 50, "y": 20, "wall_side": "top"},
                {"id": "W2", "x": 110, "y": 20, "wall_side": "top"},
                {"id": "W3", "x": 170, "y": 20, "wall_side": "top"},
                {"id": "W4", "x": 230, "y": 20, "wall_side": "top"},
            ],
            "tables": [
                {"id": f"T{idx + 1}", "x": x, "y": y, "capacity": capacity}
                for idx, (capacity, x, y) in enumerate(
                    [
                        (2, 80, 80), (4, 160, 80), (4, 240, 80),
                        (6, 80, 130), (2, 160, 130), (4, 240, 130),
                        (4, 80, 180), (6, 160, 180), (2, 240, 180),
                        (4, 80, 230), (4, 160, 230), (6, 240, 230),
                    ]
                )
            ],
        }

        grid = grid_from_layout(layout, cell_size=12)
        ingress = set(grid.door_cells.values())
        for door_cell in grid.door_cells.values():
            ingress.update(neighbors(door_cell, grid, allow_diagonal=True))
        queue_cells = {
            cell
            for cells in grid.queue_cells_by_window.values()
            for cell in cells
        }

        self.assertTrue(queue_cells.isdisjoint(ingress))

    # 验证密集布局下队列是有限的连续物理队伍；容量不足由入口等待/离开策略承接。
    def test_window_queue_targets_extend_for_large_dining_layouts(self):
        layout = {
            "floor": {"x": 0, "y": 0, "width": 360, "height": 640},
            "doors": [{"id": "D1", "x": 20, "y": 80, "wall_side": "left"}],
            "windows": [
                {"id": "W1", "x": 50, "y": 20, "wall_side": "top"},
                {"id": "W2", "x": 110, "y": 20, "wall_side": "top"},
                {"id": "W3", "x": 170, "y": 20, "wall_side": "top"},
                {"id": "W4", "x": 230, "y": 20, "wall_side": "top"},
            ],
            "tables": [
                {"id": f"T{idx + 1}", "x": x, "y": y, "capacity": capacity}
                for idx, (capacity, x, y) in enumerate(
                    [
                        (2, 80, 80), (4, 160, 80), (4, 240, 80),
                        (6, 80, 130), (2, 160, 130), (4, 240, 130),
                        (4, 80, 180), (6, 160, 180), (2, 240, 180),
                        (4, 80, 230), (4, 160, 230), (6, 240, 230),
                    ]
                )
            ],
        }

        grid = grid_from_layout(layout, cell_size=12)

        reserved: set[tuple[int, int]] = set()
        for queue_cells in grid.queue_cells_by_window.values():
            self.assertTrue(queue_cells)
            self.assertTrue(set(queue_cells).isdisjoint(reserved))
            for cell in queue_cells:
                self.assertTrue(is_walkable(cell, grid))
            for previous, current in zip(queue_cells, queue_cells[1:]):
                self.assertEqual(abs(previous[0] - current[0]) + abs(previous[1] - current[1]), 1)
            reserved.update(queue_cells)

    # 验证大布局下队伍沿可走通道连续延展，遇到其他队伍或墙会停止，而不是抢占门口缓冲区。
    def test_high_capacity_window_queues_fold_through_service_corridor(self):
        grid = grid_from_layout(_large_service_corridor_layout(), cell_size=8)
        ingress = set(grid.door_cells.values())
        for door_cell in grid.door_cells.values():
            ingress.update(neighbors(door_cell, grid, allow_diagonal=True))

        reserved: set[tuple[int, int]] = set()
        for queue_cells in grid.queue_cells_by_window.values():
            queue_set = set(queue_cells)

            self.assertTrue(queue_cells)
            self.assertTrue(queue_set.isdisjoint(ingress))
            self.assertTrue(queue_set.isdisjoint(reserved))
            for previous, current in zip(queue_cells, queue_cells[1:]):
                self.assertEqual(abs(previous[0] - current[0]) + abs(previous[1] - current[1]), 1)
            reserved.update(queue_set)

    # 验证相邻窗口不会抢占彼此队首区域，否则队首补位会被迫从远处跳到窗口。
    def test_window_queue_heads_stay_near_their_own_service_cells(self):
        grid = grid_from_layout(_large_service_corridor_layout(), cell_size=8)

        for window_index, service in grid.service_cells.items():
            queue_cells = grid.queue_cells_by_window[window_index]
            front_cells = queue_cells[1:6]

            self.assertTrue(front_cells)
            self.assertLessEqual(
                min(abs(cell[0] - service[0]) + abs(cell[1] - service[1]) for cell in front_cells),
                2,
            )

    # 验证队列前段不能跨越大空洞，否则队首补位会穿过相邻窗口队列。
    def test_window_queue_front_cells_are_contiguous(self):
        grid = grid_from_layout(_large_service_corridor_layout(), cell_size=8)

        for queue_cells in grid.queue_cells_by_window.values():
            for current, following in zip(queue_cells[:12], queue_cells[1:12]):
                self.assertLessEqual(
                    abs(current[0] - following[0]) + abs(current[1] - following[1]),
                    3,
                )

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

    # 验证动态场 step 使用内联网格检查，避免在热点路径反复调用通用 neighbors/is_walkable。
    def test_dynamic_field_step_avoids_generic_grid_helpers(self):
        grid = grid_from_layout({"doors": [], "windows": [], "tables": []}, cell_size=20)
        blocked_neighbor = (5, 4)
        grid.blocked_cells.add(blocked_neighbor)
        field = DynamicField(decay=0.5, diffusion=0.25)
        source = (4, 4)
        calls = {"neighbors": 0, "is_walkable": 0}

        original_neighbors = fields_module.neighbors
        original_is_walkable = fields_module.is_walkable

        def counted_neighbors(*args, **kwargs):
            calls["neighbors"] += 1
            return original_neighbors(*args, **kwargs)

        def counted_is_walkable(*args, **kwargs):
            calls["is_walkable"] += 1
            return original_is_walkable(*args, **kwargs)

        fields_module.neighbors = counted_neighbors
        fields_module.is_walkable = counted_is_walkable
        try:
            field.deposit(source, amount=8.0)
            field.step(grid)
        finally:
            fields_module.neighbors = original_neighbors
            fields_module.is_walkable = original_is_walkable

        self.assertEqual(calls, {"neighbors": 0, "is_walkable": 0})
        self.assertGreater(field.values[source], 0)
        self.assertNotIn(blocked_neighbor, field.values)

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

    # 验证 legacy floor-field 包装保留 floor origin，避免带偏移布局下点坐标被映射到错误格。
    def test_next_cell_by_floor_field_preserves_grid_origin_for_point_agents(self):
        layout = {
            "floor": {"x": 24, "y": 24, "width": 312, "height": 240},
            "doors": [],
            "windows": [],
            "tables": [],
        }
        grid = grid_from_layout(layout, cell_size=20)
        target = {"x": 120, "y": 72}
        field = build_static_floor_field(layout, target)

        next_cell = next_cell_by_floor_field(agent={"x": 48, "y": 72}, grid=field, target=target)

        self.assertEqual(field["origin_x"], grid.origin_x)
        self.assertEqual(field["origin_y"], grid.origin_y)
        self.assertEqual(next_cell, (2, 2))

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
