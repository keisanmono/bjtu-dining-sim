# 文件说明：校园步行数据测试：验证内置教学楼和食堂步行时间数据完整性。

import json
import unittest
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "campus_walk_times.json"


# 校园步行时间数据测试，确保展示使用的数据只覆盖主校区且无敏感字段。
class CampusWalkTimesTest(unittest.TestCase):
    # 验证内置教学楼、食堂和步行时间表完整，并且不包含东区或密钥字段。
    def test_campus_walk_times_cover_main_campus_without_secrets(self):
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))

        buildings = payload["locations"]["teaching_buildings"]
        cafeterias = payload["locations"]["cafeterias"]
        walk_times = payload["walk_times"]

        building_ids = {item["id"] for item in buildings}
        cafeteria_ids = {item["id"] for item in cafeterias}

        self.assertEqual(payload["campus_scope"], "main_campus_only")
        self.assertEqual(
            building_ids,
            {
                "siyuan",
                "siyuan_west",
                "siyuan_east",
                "no9",
                "no8",
                "no5",
                "yifu",
                "mechanical",
                "no17",
            },
        )
        self.assertEqual(cafeteria_ids, {"xuehuo", "minghu", "xuesi", "xueyuan"})
        payload_text = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("东区", payload_text)
        self.assertNotIn("api_key", payload_text)

        for building_id in building_ids:
            self.assertEqual(set(walk_times[building_id]), cafeteria_ids)
            for route in walk_times[building_id].values():
                self.assertGreater(route["distance_m"], 0)
                self.assertGreater(route["duration_s"], 0)
                self.assertGreater(route["duration_min"], 0)
