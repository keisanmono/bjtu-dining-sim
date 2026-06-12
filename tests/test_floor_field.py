# 文件说明：Floor Field / CA 骨架测试，覆盖网格参数和目标可达性边界。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.floor_field import build_static_floor_field, grid_from_layout, next_cell_by_floor_field


class FloorFieldTests(unittest.TestCase):
    # 验证网格粒度必须为正数，避免除零或负网格尺寸。
    def test_grid_from_layout_rejects_non_positive_cell_size(self):
        layout = {"tables": []}

        with self.assertRaises(ValueError):
            grid_from_layout(layout, cell_size=0)
        with self.assertRaises(ValueError):
            grid_from_layout(layout, cell_size=-5)

    # 验证目标格即使位于桌面 footprint 内，也可作为终点被 agent 走入。
    def test_next_cell_can_enter_blocked_target_cell(self):
        layout = {
            "tables": [
                {"id": "T1", "x": 50, "y": 50, "capacity": 2},
            ]
        }
        target = {"x": 50, "y": 50}
        field = build_static_floor_field(layout, target)

        next_cell = next_cell_by_floor_field(agent=(2, 1), grid=field, target=target)

        self.assertEqual(next_cell, field["target_cell"])
        self.assertNotIn(field["target_cell"], field["blocked"])


if __name__ == "__main__":
    unittest.main()
