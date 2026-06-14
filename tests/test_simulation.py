# 文件说明：仿真核心测试：验证排队、座位、推荐、结伴和实时地图快照行为。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.optimization as optimization_module
from app.campus import CampusPopulationPoolData, ResidentialReleaseProfile
from app.optimization import RecommendationRequestData, recommend_config
from app.pedestrian.agents import AgentState
from app.pedestrian.grid import grid_from_layout, point_to_cell
from app.simulation import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    DiningLayoutData,
    DiningSeat,
    DiningSimulationRunner,
    LayoutDoorData,
    LayoutFloorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
    WindowService,
    apply_movement_quality_preset,
    run_layout_ablation_snapshot,
    run_simulation,
    validate_config,
)


# 仿真核心测试，覆盖到达、排队、入座、推荐估算和实时地图快照。
class DiningSimulationTests(unittest.TestCase):
    # 验证行人移动模型配置的默认值和业务校验边界。
    def test_movement_model_config_validation(self):
        valid_errors, _ = validate_config(SimulationConfigData(movement_model="advanced_floor_field"))
        invalid_model_errors, _ = validate_config(SimulationConfigData(movement_model="invalid"))
        invalid_tick_errors, _ = validate_config(SimulationConfigData(movement_tick_seconds=0))
        invalid_decay_errors, _ = validate_config(SimulationConfigData(dynamic_field_decay=1.2))

        self.assertEqual(valid_errors, [])
        self.assertTrue(any("movement_model" in error for error in invalid_model_errors))
        self.assertTrue(any("movement_tick_seconds" in error for error in invalid_tick_errors))
        self.assertTrue(any("dynamic_field_decay" in error for error in invalid_decay_errors))

    # 验证默认 movement_model 仍使用原有路径模型。
    def test_default_movement_model_is_path(self):
        config = SimulationConfigData()

        self.assertEqual(config.movement_model, "path")
        self.assertIsNone(getattr(DiningSimulationRunner(config), "pedestrian_engine", None))

    # 验证三档质量预设会展开为对应的底层 movement_model 和关键参数。
    def test_movement_quality_presets_expand_to_model_configs(self):
        fast = apply_movement_quality_preset(SimulationConfigData(movement_quality_preset="fast"))
        balanced = apply_movement_quality_preset(SimulationConfigData(movement_quality_preset="balanced"))
        quality = apply_movement_quality_preset(SimulationConfigData(movement_quality_preset="quality"))

        self.assertEqual(fast.movement_model, "path")
        self.assertFalse(fast.advanced_movement_coupling)
        self.assertEqual(fast.window_choice_temperature, 0.0)
        self.assertEqual(balanced.movement_model, "static_floor_field")
        self.assertFalse(balanced.advanced_movement_coupling)
        self.assertGreater(balanced.window_choice_temperature, 0.0)
        self.assertEqual(quality.movement_model, "advanced_floor_field")
        self.assertTrue(quality.advanced_movement_coupling)
        self.assertGreater(quality.window_choice_temperature, 0.0)
        self.assertGreater(quality.window_switch_cooldown_min, 0)

    # 验证旧 payload 不传 preset 时仍尊重原 movement_model。
    def test_no_quality_preset_keeps_legacy_movement_model(self):
        config = apply_movement_quality_preset(SimulationConfigData(movement_model="static_floor_field"))

        self.assertEqual(config.movement_model, "static_floor_field")
        self.assertIsNone(config.movement_quality_preset)

    # 验证接口层允许 preset 默认被用户显式 movement 字段覆盖。
    def test_schema_quality_preset_allows_explicit_movement_override(self):
        try:
            from app.schemas import SimulationConfig
        except ModuleNotFoundError as exc:
            if exc.name == "pydantic":
                self.skipTest("pydantic is not installed in this unittest environment")
            raise

        config = SimulationConfig(
            movement_quality_preset="quality",
            movement_model="static_floor_field",
            max_movement_ticks_per_minute=2,
        ).to_data()

        self.assertEqual(config.movement_quality_preset, "quality")
        self.assertEqual(config.movement_model, "static_floor_field")
        self.assertEqual(config.max_movement_ticks_per_minute, 2)

    # 验证 runner 不会二次展开 preset，从而保留接口层已经处理过的显式 movement 覆盖。
    def test_runner_keeps_schema_movement_overrides_after_quality_preset(self):
        config = apply_movement_quality_preset(
            SimulationConfigData(
                movement_quality_preset="quality",
                floor_cell_size=20.0,
                max_movement_ticks_per_minute=2,
            ),
            explicit_fields={"floor_cell_size", "max_movement_ticks_per_minute"},
        )
        runner = DiningSimulationRunner(config)

        self.assertEqual(runner.config.movement_quality_preset, "quality")
        self.assertEqual(runner.config.movement_model, "advanced_floor_field")
        self.assertEqual(runner.config.floor_cell_size, 20.0)
        self.assertEqual(runner.config.max_movement_ticks_per_minute, 2)

    # 验证无效质量预设会在业务校验中报错。
    def test_invalid_movement_quality_preset_is_rejected(self):
        errors, _warnings = validate_config(SimulationConfigData(movement_quality_preset="slow"))

        self.assertTrue(any("movement_quality_preset" in error for error in errors))

    # 验证 static_floor_field 模型会生成不穿越 blocked cell 的路径。
    def test_static_floor_field_walking_path_is_not_empty_and_avoids_blocked_cells(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=64, y=160, wall_side="left")],
            tables=[
                LayoutTableData(id="BLOCK", x=140, y=160, table_type="six_seat", capacity=6),
                LayoutTableData(id="TARGET", x=240, y=160, table_type="four_seat", capacity=4),
            ],
        )
        config = SimulationConfigData(
            layout=layout,
            num_windows=1,
            num_seats=10,
            movement_model="static_floor_field",
            floor_cell_size=12.0,
        )
        runner = DiningSimulationRunner(config)

        path = runner._walking_path({"x": 48, "y": 160}, {"x": 240, "y": 160}, target_table_index=1)
        grid = grid_from_layout(layout, config.floor_cell_size)
        path_cells = [point_to_cell(point, grid) for point in path]

        self.assertGreater(len(path), 1)
        self.assertTrue(all(cell not in grid.blocked_cells for cell in path_cells))

    # 验证高级模式的 step 快照暴露微观行人状态。
    def test_advanced_floor_field_snapshot_contains_pedestrian_agents(self):
        config = SimulationConfigData(
            num_windows=1,
            num_seats=4,
            arrival_rate=4.0,
            service_time_mean=1.0,
            dining_time_mean=2.0,
            duration_min=5,
            seed=20260612,
            movement_model="advanced_floor_field",
        )
        runner = DiningSimulationRunner(config)

        record = runner.step()

        self.assertIn("pedestrian_agents", record.snapshot)
        self.assertGreater(len(record.snapshot["pedestrian_agents"]), 0)
        self.assertIn("density_hotspots", record.snapshot)
        self.assertIn("movement_metrics", record.snapshot)

    # 消融测试：只替换布局，真实 advanced 仿真结果应体现优化布局的入口堆积改善。
    def test_layout_ablation_uses_simulation_results_to_compare_optimized_layout(self):
        baseline_layout = self._cafeteria_layout_for_flow_ablation(optimized=False)
        optimized_layout = self._cafeteria_layout_for_flow_ablation(optimized=True)
        config = SimulationConfigData(
            num_windows=4,
            num_seats=120,
            arrival_rate=12.0,
            service_time_mean=0.5,
            dining_time_mean=20,
            duration_min=24,
            movement_model="advanced_floor_field",
            advanced_movement_coupling=True,
            floor_cell_size=8,
            movement_tick_seconds=5,
            party_size_distribution={1: 1.0},
            seed=20260613,
        )

        comparison = run_layout_ablation_snapshot(
            config,
            baseline_layout=baseline_layout,
            optimized_layout=optimized_layout,
            steps=20,
        )

        self.assertGreater(comparison["baseline"]["entry_waiting_count"], comparison["optimized"]["entry_waiting_count"])
        self.assertGreater(comparison["optimized"]["indoor_agents"], comparison["baseline"]["indoor_agents"])
        self.assertLess(comparison["delta"]["entry_waiting_count"], 0)

    def _cafeteria_layout_for_flow_ablation(self, optimized: bool) -> DiningLayoutData:
        capacities = []
        pattern = [2, 4, 4, 6]
        remaining = 120
        index = 0
        while remaining > 0:
            capacity = min(pattern[index % len(pattern)], remaining)
            capacities.append(capacity)
            remaining -= capacity
            index += 1
        table_start_y = 184 if optimized else 110
        row_step = 50 if optimized else 42
        floor_height = 700 if optimized else 560
        return DiningLayoutData(
            floor=LayoutFloorData(x=24, y=24, width=312, height=floor_height),
            doors=[LayoutDoorData(id="D1", x=24, y=100, wall_side="left")],
            windows=[
                LayoutWindowData(id=f"W{idx + 1}", x=x, y=24, wall_side="top")
                for idx, x in enumerate([70, 130, 190, 250])
            ],
            tables=[
                LayoutTableData(
                    id=f"T{idx + 1}",
                    x=100 + (idx % 3) * 80,
                    y=table_start_y + (idx // 3) * row_step,
                    capacity=capacity,
                )
                for idx, capacity in enumerate(capacities)
            ],
        )

    # 验证高级移动耦合下，学生走到窗口排队点之前不能开始窗口服务。
    def test_advanced_movement_coupling_delays_service_until_window_reached(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=320, y=60, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=240, y=320, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                max_movement_ticks_per_minute=1,
            )
        )
        students = runner._create_party_students(minute=0, person_count=1)

        runner._enqueue_arrivals(students)
        runner._start_window_services(minute=0)

        self.assertEqual(runner.queues[0], [])
        self.assertIsNone(runner.windows[0])
        self.assertIsNone(students[0].service_start_time)

    # 验证高级模式下，入场者先走向窗口槽位，到达后才进入物理 FIFO 队列。
    def test_advanced_walkers_enter_physical_queue_only_after_slot_reached(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=320, y=60, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=240, y=320, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                max_movement_ticks_per_minute=1,
                party_size_distribution={1: 1.0},
                seed=20260613,
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]

        runner._enqueue_arrivals([student])
        runner._admit_due_entry_students(current_time_sec=60)

        self.assertEqual(runner.queues[0], [])
        self.assertEqual(runner.waiting_to_queue_student_ids, {student.student_id})
        agent = runner.pedestrian_engine.agents[student.student_id]
        slot = next(iter(agent.target_cells))
        agent.cell = slot

        admitted = runner._admit_students_who_reached_window_queue(minute=1)

        self.assertEqual(admitted, 1)
        self.assertEqual(runner.queues[0], [student])
        self.assertEqual(runner.waiting_to_queue_student_ids, set())

    # 验证高级模式下，物理队首不到窗口不能开始服务。
    def test_advanced_physical_queue_waits_for_head_to_reach_service(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=320, y=60, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=240, y=320, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                max_movement_ticks_per_minute=1,
                party_size_distribution={1: 1.0},
                seed=20260613,
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]

        runner._enqueue_arrivals([student])
        runner._admit_due_entry_students(current_time_sec=60)

        agent = runner.pedestrian_engine.agents[student.student_id]
        agent.cell = next(iter(agent.target_cells))
        runner._admit_students_who_reached_window_queue(minute=1)
        self.assertEqual(runner.queues[0], [student])

        agent.cell = runner.pedestrian_engine.grid.queue_cells_by_window[0][15]
        runner._start_window_services(minute=0)

        self.assertIsNone(runner.windows[0])

        agent.cell = runner.pedestrian_engine.grid.service_cells[0]
        runner._start_window_services(minute=0)

        self.assertIsNotNone(runner.windows[0])
        self.assertEqual(student.service_start_time, 0)

    # 验证靠近服务区的后位学生不能越过物理队首开始服务。
    def test_advanced_service_uses_physical_head_not_nearby_tail(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=320, y=60, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=240, y=320, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        head, tail = runner._create_party_students(minute=0, person_count=2)
        runner.pedestrian_engine.spawn_arrivals([head, tail], door_index=0)
        runner._move_student_to_window_queue(head, 0)
        runner._move_student_to_window_queue(tail, 0)
        runner.queues[0] = [head, tail]
        runner.pedestrian_engine.set_window_physical_queue(0, [head.student_id, tail.student_id])
        service_cell = runner.pedestrian_engine.grid.service_cells[0]
        runner.pedestrian_engine.agents[head.student_id].cell = (service_cell[0], service_cell[1] + 8)
        runner.pedestrian_engine.agents[tail.student_id].cell = service_cell

        self.assertFalse(runner._start_single_window_service(0, start_time_minute=0.0))
        self.assertIsNone(tail.service_start_time)

        runner.pedestrian_engine.agents[head.student_id].cell = service_cell
        self.assertTrue(runner._start_single_window_service(0, start_time_minute=1.0))
        self.assertEqual(runner.windows[0].student, head)
        self.assertIsNone(tail.service_start_time)

    # 验证 advanced 模式下，同一分钟到达者被拆成秒级边界入场事件，而不是用人为门口限流。
    def test_advanced_arrivals_are_scheduled_over_subminute_entry_times(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=4,
                num_seats=120,
                duration_min=5,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
                seed=42,
            )
        )
        students = runner._create_party_students(minute=10, person_count=24)

        runner._enqueue_arrivals(students)
        entry_times = [item[0] for item in runner.pending_entry_students]

        self.assertEqual(len(entry_times), len(students))
        self.assertTrue(all(600 <= second < 660 for second in entry_times))
        self.assertGreater(len(set(entry_times)), 1)

    # 验证高级移动耦合下，长期卡在窗口走廊的学生可重选最近窗口，避免尾部死锁。
    def test_advanced_coupling_retargets_stuck_student_to_nearby_window(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=96, y=60, wall_side="top"),
                LayoutWindowData(id="W2", x=260, y=60, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=180, y=320, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=2,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        runner._enqueue_arrivals([student])
        runner._admit_due_entry_students(current_time_sec=60)
        runner._move_student_to_window_queue(student, 1)
        runner.waiting_to_queue_student_ids.add(student.student_id)
        agent = runner.pedestrian_engine.agents[student.student_id]
        agent.state = AgentState.TO_WINDOW
        agent.cell = runner.pedestrian_engine.grid.service_cells[0]
        agent.wait_ticks = 200

        admitted = runner._admit_students_who_reached_window_queue(minute=12)

        self.assertGreaterEqual(admitted, 0)
        self.assertEqual(student.window_index, 0)
        self.assertEqual(runner.queues[0], [student])

    # 验证高级移动耦合下，尚未走到窗口的 pending 学生也会计入窗口负载。
    def test_advanced_coupling_window_choice_counts_pending_walkers(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=100, y=320, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=60, y=60, wall_side="top"),
                LayoutWindowData(id="W2", x=140, y=60, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=100, y=420, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=2,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
                seed=20260613,
            )
        )
        students = runner._create_party_students(minute=0, person_count=6)

        runner._enqueue_arrivals(students)
        runner._admit_due_entry_students(current_time_sec=60)

        self.assertEqual([len(queue) for queue in runner.queues], [0, 0])
        self.assertEqual(runner._pending_window_queue_count(0), 3)
        self.assertEqual(runner._pending_window_queue_count(1), 3)
        self.assertEqual(
            [sum(1 for student in students if student.window_index == idx) for idx in range(2)],
            [3, 3],
        )

    # 验证快照区分入口等待、走向窗口、物理队列和总压力，避免双计数。
    def test_advanced_snapshot_distinguishes_walking_to_window_and_physical_queue(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
                seed=20260615,
            )
        )
        first, second = runner._create_party_students(minute=0, person_count=2)
        runner._enqueue_arrivals([first, second])
        runner._admit_due_entry_students(current_time_sec=60)
        first_agent = runner.pedestrian_engine.agents[first.student_id]
        first_agent.cell = next(iter(first_agent.target_cells))
        runner._admit_students_who_reached_window_queue(minute=1)

        snapshot = runner._snapshot()

        self.assertEqual(snapshot["queue_lengths"], [1])
        self.assertEqual(snapshot["physical_queue_lengths"], [1])
        self.assertEqual(snapshot["walking_to_window_count"], 1)
        self.assertEqual(snapshot["total_waiting_pressure"], 2)

    # 验证质量模式下，窗口预计成本显著恶化时允许低频动态换队。
    def test_quality_window_rechoice_switches_when_alternative_is_significantly_better(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=100, y=320, wall_side="left")],
            windows=[
                LayoutWindowData(id="W1", x=60, y=60, wall_side="top"),
                LayoutWindowData(id="W2", x=140, y=60, wall_side="top"),
            ],
            tables=[LayoutTableData(id="T1", x=100, y=420, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=2,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                window_switch_cooldown_min=2,
                window_switch_threshold_min=1.0,
                window_switch_penalty_min=0.2,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
                seed=20260614,
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        runner._enqueue_arrivals([student])
        runner._admit_due_entry_students(current_time_sec=60)
        student.window_index = 0
        runner.pedestrian_engine.set_agent_target_window(student.student_id, 0)
        runner.waiting_to_queue_student_ids.add(student.student_id)
        runner.queues[0] = runner._create_party_students(minute=0, person_count=5)
        agent = runner.pedestrian_engine.agents[student.student_id]
        agent.state = AgentState.TO_WINDOW
        agent.cell = runner.pedestrian_engine.grid.service_cells[1]

        runner._retarget_stuck_window_agents()

        self.assertEqual(student.window_index, 1)
        self.assertEqual(runner.window_switch_minutes[student.student_id], runner.current_minute)

    # 验证 path 模型不受高级移动耦合开关影响，仍保持原先立即进入窗口队列的行为。
    def test_path_model_keeps_immediate_queue_entry_even_when_coupling_flag_is_true(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                movement_model="path",
                advanced_movement_coupling=True,
            )
        )
        students = runner._create_party_students(minute=0, person_count=1)

        runner._enqueue_arrivals(students)
        runner._start_window_services(minute=0)

        self.assertIsNotNone(runner.windows[0])
        self.assertEqual(students[0].service_start_time, 0)

    # 验证窗口服务按秒级时长推进，短服务时间下同一窗口一分钟内能服务多名学生。
    def test_subminute_window_service_can_finish_multiple_students_per_minute(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                arrival_rate=1.0,
                service_time_mean=0.25,
                dining_time_mean=20,
                duration_min=5,
                movement_model="path",
                party_size_distribution={1: 1.0},
                seed=20260613,
            )
        )
        students = runner._create_party_students(minute=0, person_count=4)
        runner.queues[0].extend(students)

        runner._start_window_services(minute=0)
        served = runner._advance_windows(minute=0)

        self.assertGreater(len(served), 1)
        self.assertTrue(all(getattr(student, "service_end_time_sec", None) is not None for student in served))

    # 验证 step() 中新到达后启动的短服务会在其启动分钟内推进，而不是等到下一分钟。
    def test_subminute_service_started_after_arrivals_advances_during_start_minute(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                arrival_rate=1.0,
                service_time_mean=0.25,
                dining_time_mean=20,
                duration_min=5,
                movement_model="path",
                party_size_distribution={1: 1.0},
                seed=20260614,
            )
        )
        created: dict[str, object] = {}

        def deterministic_arrivals(minute: int):
            if minute != 0:
                return []
            students = runner._create_party_students(minute=minute, person_count=1)
            created["student"] = students[0]
            return students

        runner._generate_arrivals = deterministic_arrivals
        runner._sample_service_duration_minutes = lambda _mean: 0.25

        record = runner.step()
        student = created["student"]

        self.assertEqual(record.served_count, 1)
        self.assertEqual(student.service_start_time_sec, 0)
        self.assertEqual(student.service_end_time_sec, 15)
        self.assertIsNone(runner.windows[0])

    # 验证 movement_model 只影响食堂内移动过程，不改变同一 seed 下的手动到达需求流。
    def test_movement_model_does_not_change_manual_arrival_stream(self):
        base_config = dict(
            num_windows=1,
            num_seats=8,
            arrival_rate=1.0,
            service_time_mean=1.0,
            dining_time_mean=2.0,
            duration_min=5,
            seed=20260613,
            party_size_distribution={1: 1.0},
        )

        path_result = run_simulation(SimulationConfigData(**base_config, movement_model="path"))
        advanced_result = run_simulation(SimulationConfigData(**base_config, movement_model="advanced_floor_field"))

        self.assertEqual(path_result.metrics.total_arrived, advanced_result.metrics.total_arrived)

    # 验证高级移动耦合下，完成取餐的小组必须实际走到餐桌附近后才正式入座。
    def test_advanced_movement_coupling_delays_seating_until_table_reached(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=60, y=60, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=320, y=560, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                max_movement_ticks_per_minute=1,
            )
        )
        students = runner._create_party_students(minute=0, person_count=1)
        runner._enqueue_arrivals(students)
        runner._admit_due_entry_students(current_time_sec=60)
        student = students[0]
        student.window_index = 0
        student.service_end_time = 0
        party = runner.parties[student.party_id]
        party.ready_time = 0
        runner.waiting_for_seat.append(party)

        runner._seat_waiting_students(minute=0)
        seated_count = runner._advance_walking_to_seats(end_time_sec=60)

        self.assertEqual(seated_count, 0)
        self.assertIsNone(student.seat_time)
        self.assertEqual(runner.table_occupied_seats[0], 0)

    # 验证 advanced CA 不允许靠几何超时强制入座，必须实际到达餐桌邻近目标格。
    def test_advanced_table_walk_does_not_force_seating_by_geometric_deadline(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        party = runner.parties[student.party_id]
        runner.pedestrian_engine.spawn_arrivals([student], door_index=0)
        student.window_index = 0
        student.service_end_time = 1
        party.ready_time = 1
        transfer = runner._start_walking_to_seat(party, 0, 1, 1)
        runner.walking_to_seat.append(transfer)
        runner.table_reserved_seats[0] = 1
        runner.pedestrian_engine.set_party_target_table(party, 0)
        runner.pedestrian_engine.agents[student.student_id].cell = (2, 2)

        seated = runner._advance_walking_to_seats(
            end_time_sec=transfer.arrive_time_sec + 10_000
        )

        self.assertEqual(seated, 0)
        self.assertEqual(runner.walking_to_seat, [transfer])
        self.assertIsNone(student.seat_time)
        self.assertEqual(runner.table_occupied_seats[0], 0)

    # 验证餐桌 approach slot 被占用时，成员可切换到同桌其他 slot，而不是几何超时入座。
    def test_advanced_table_recovery_reassigns_blocked_approach_slot(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=DiningLayoutData(
                    doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
                    windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
                    tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
                ),
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        party = runner.parties[student.party_id]
        blocker = runner._create_party_students(minute=0, person_count=1)[0]
        runner.pedestrian_engine.spawn_arrivals([student, blocker], door_index=0)
        transfer = runner._start_walking_to_seat(party, 0, 1, 1)
        runner.walking_to_seat.append(transfer)
        runner.table_reserved_seats[0] = 1
        runner.pedestrian_engine.set_party_target_table(party, 0)
        agent = runner.pedestrian_engine.agents[student.student_id]
        old_slot = agent.assigned_table_approach_cell
        runner.pedestrian_engine.agents[blocker.student_id].cell = old_slot
        runner.pedestrian_engine.agents[blocker.student_id].state = AgentState.WAITING_GROUP
        agent.stuck_ticks = 20

        ready = runner._advanced_transfer_ready_to_seat(transfer, end_time_sec=120)

        self.assertFalse(ready)
        self.assertNotEqual(agent.assigned_table_approach_cell, old_slot)
        self.assertEqual(runner.table_reserved_seats[0], 1)

    # 验证高级移动选桌会跳过缺少真实可达目标格的餐桌。
    def test_advanced_table_choice_skips_tables_without_movement_targets(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=18, y=580, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=60, y=60, wall_side="top")],
            tables=[
                LayoutTableData(id="T1", x=120, y=320, table_type="four_seat", capacity=4),
                LayoutTableData(id="T2", x=300, y=320, table_type="four_seat", capacity=4),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=8,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        party = runner.parties[student.party_id]
        runner.pedestrian_engine.grid.table_approach_cells[0].clear()

        table_index = runner._choose_table_for_party(party)

        self.assertEqual(table_index, 1)

    # 验证高级模式最终指标包含移动冲突、停滞和密度指标。
    def test_advanced_floor_field_metrics_include_movement_fields(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                arrival_rate=3.0,
                service_time_mean=1.0,
                dining_time_mean=2.0,
                duration_min=5,
                seed=20260613,
                movement_model="advanced_floor_field",
            )
        )

        self.assertIn("movement_conflict_count", result.final_state["movement_metrics"])
        self.assertGreater(result.metrics.avg_walking_time, 0)
        self.assertGreaterEqual(result.metrics.movement_conflict_count, 0)
        self.assertGreaterEqual(result.metrics.avg_stuck_ticks, 0)
        self.assertGreater(result.metrics.max_density, 0)

    # 验证高级 movement metrics 在确定性冲突场景中记录真实冲突和行走时间，而不只是字段存在。
    def test_advanced_floor_field_metrics_capture_deterministic_conflict(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=DiningLayoutData(
                    doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
                    windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
                    tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
                ),
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                floor_randomness=0.0,
            )
        )
        people = runner._create_party_students(minute=0, person_count=3)
        runner.pedestrian_engine.spawn_arrivals(people, door_index=0)
        target = (8, 8)
        for cell, agent in zip([(7, 8), (9, 8), (8, 7)], runner.pedestrian_engine.agents.values()):
            agent.cell = cell
            agent.state = AgentState.TO_WINDOW
            agent.target_cells = {target}

        runner.pedestrian_engine.tick(0)
        metrics = runner._snapshot()["movement_metrics"]

        self.assertEqual(metrics["movement_conflict_count"], 2)
        self.assertGreater(metrics["avg_walking_time"], 0)
        self.assertGreater(metrics["max_density"], 0)

    # 验证实时快照里的累计 movement 指标不会随 EXITED 或后续记录出现倒退。
    def test_advanced_snapshot_cumulative_movement_metrics_do_not_regress(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                arrival_rate=4.0,
                service_time_mean=0.5,
                dining_time_mean=1.0,
                duration_min=6,
                seed=20260616,
                movement_model="advanced_floor_field",
                party_size_distribution={1: 1.0},
            )
        )

        conflict_counts = [
            int(record.snapshot["movement_metrics"]["movement_conflict_count"])
            for record in result.records
            if "movement_metrics" in record.snapshot
        ]
        max_densities = [
            int(record.snapshot["movement_metrics"]["max_density"])
            for record in result.records
            if "movement_metrics" in record.snapshot
        ]

        self.assertEqual(conflict_counts, sorted(conflict_counts))
        self.assertEqual(max_densities, sorted(max_densities))

    # 验证吃完后 DES 指标立即释放座位，但 advanced 行人先进入 TO_EXIT 可视离场。
    def test_dining_completion_releases_seat_and_starts_to_exit_animation(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=4,
                movement_model="advanced_floor_field",
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        runner.pedestrian_engine.spawn_arrivals([student], door_index=0)
        agent = runner.pedestrian_engine.agents[student.student_id]
        agent.cell = (18, 24)
        runner.pedestrian_engine.set_agent_seated(student.student_id, table_index=0, preserve_cell=True)
        runner.seated = [DiningSeat(student=student, remaining=1, table_index=0)]
        runner.table_occupied_seats[0] = 1
        runner.table_party_ids[0].add(student.party_id)

        left_count = runner._advance_dining(minute=3)

        self.assertEqual(left_count, 1)
        self.assertEqual(runner.total_left, 1)
        self.assertEqual(runner.table_occupied_seats[0], 0)
        self.assertEqual(agent.state, AgentState.TO_EXIT)
        self.assertNotEqual(agent.state, AgentState.EXITED)

        pedestrian_result = runner.pedestrian_engine.run_for_minute(180, 240)

        self.assertIsNotNone(pedestrian_result["timeline"])
        self.assertTrue(
            any(event["type"] == "pedestrian_move" for event in pedestrian_result["timeline"]["events"])
        )

    # 验证仿真结束判断会等待 TO_EXIT 行人走完离场动画。
    def test_done_waits_for_active_to_exit_pedestrians(self):
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                duration_min=5,
                movement_model="advanced_floor_field",
                floor_randomness=0.0,
                party_size_distribution={1: 1.0},
            )
        )
        student = runner._create_party_students(minute=0, person_count=1)[0]
        runner.pedestrian_engine.spawn_arrivals([student], door_index=0)
        agent = runner.pedestrian_engine.agents[student.student_id]
        agent.state = AgentState.TO_EXIT
        agent.cell = (18, 24)
        agent.target_cells = set(runner.pedestrian_engine.grid.exit_cells)
        runner.current_minute = runner.arrival_horizon_minute

        self.assertFalse(runner.done)

    # 验证预占座和高级行人模式同时开启时容量不溢出，且小队能最终入座。
    def test_preemptive_reservation_with_advanced_floor_field_keeps_capacity_and_seats_parties(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
            tables=[
                LayoutTableData(id="T1", x=180, y=240, table_type="four_seat", capacity=4),
                LayoutTableData(id="T2", x=260, y=240, table_type="four_seat", capacity=4),
            ],
        )
        result = run_simulation(
            SimulationConfigData(
                layout=layout,
                num_windows=1,
                num_seats=8,
                arrival_rate=2.0,
                service_time_mean=1.0,
                dining_time_mean=2.0,
                duration_min=5,
                seed=20260614,
                party_size_distribution={2: 1.0},
                preempt_seat_probability=1.0,
                seat_holder_min_party_size=2,
                movement_model="advanced_floor_field",
            )
        )

        for record in result.records:
            for table in record.snapshot["table_occupancy"]:
                self.assertLessEqual(table["occupied"] + table["reserved"], table["capacity"])
        self.assertGreater(result.metrics.throughput, 0)

    # 验证相同 seed 下完整仿真结果可复现。
    def test_run_is_reproducible_with_same_seed(self):
        config = SimulationConfigData(
            num_windows=3,
            num_seats=80,
            arrival_rate=9.0,
            service_time_mean=3.0,
            dining_time_mean=18.0,
            duration_min=45,
            seed=20260428,
        )

        first = run_simulation(config)
        second = run_simulation(config)

        self.assertGreaterEqual(len(first.records), config.duration_min)
        self.assertEqual([r.queue_lengths for r in first.records], [r.queue_lengths for r in second.records])
        self.assertEqual(first.metrics.avg_wait, second.metrics.avg_wait)
        self.assertEqual(first.metrics.peak_queue, second.metrics.peak_queue)
        self.assertEqual(first.metrics.total_left, first.metrics.total_arrived)

    # 验证到达期结束后系统会继续运行，直到所有已到达学生离开。
    def test_simulation_drains_all_arrivals_after_arrival_period(self):
        config = SimulationConfigData(
            num_windows=1,
            num_seats=4,
            arrival_rate=4.0,
            service_time_mean=3.0,
            dining_time_mean=8.0,
            duration_min=8,
            seed=20260429,
        )

        result = run_simulation(config)

        self.assertGreater(len(result.records), config.duration_min)
        self.assertTrue(all(record.arrived_count == 0 for record in result.records[config.duration_min:]))
        self.assertEqual(result.metrics.total_left, result.metrics.total_arrived)
        self.assertEqual(result.final_state["totals"]["left"], result.final_state["totals"]["arrived"])
        self.assertEqual(sum(result.final_state["queue_lengths"]), 0)
        self.assertEqual(result.final_state["occupied_seats"], 0)
        self.assertEqual(result.final_state["waiting_for_seat_count"], 0)
        self.assertNotIn("seat_matrix", result.final_state)

    # 验证窗口不足时峰值队列和瓶颈类型会体现窗口服务压力。
    def test_window_capacity_pressure_is_reported(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=1,
                num_seats=200,
                arrival_rate=12.0,
                service_time_mean=4.0,
                dining_time_mean=12.0,
                duration_min=40,
                seed=7,
            )
        )

        self.assertGreater(result.metrics.peak_queue, 100)
        self.assertEqual(result.metrics.bottleneck_type, "窗口服务")
        self.assertGreater(result.metrics.window_utilization, 0.85)

    # 验证座位不足时会出现等座，并把瓶颈归因为座位容量。
    def test_seat_capacity_pressure_is_reported(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=8,
                num_seats=12,
                arrival_rate=10.0,
                service_time_mean=1.0,
                dining_time_mean=30.0,
                duration_min=50,
                seed=8,
            )
        )

        self.assertGreater(max(r.waiting_for_seat_count for r in result.records), 0)
        self.assertEqual(result.metrics.bottleneck_type, "座位容量")
        self.assertGreater(result.metrics.seat_utilization, 0.75)

    # 验证推荐排序会优先给出比基准等待更低的方案。
    def test_recommendation_ranks_lower_waiting_plan_first(self):
        base = SimulationConfigData(
            num_windows=2,
            num_seats=60,
            arrival_rate=9.0,
            service_time_mean=3.5,
            dining_time_mean=18.0,
            duration_min=45,
            seed=99,
        )
        request = RecommendationRequestData(
            base_config=base,
            window_options=[2, 3, 4],
            seat_options=[60, 80],
            stagger_options=[0, 10],
            top_k=4,
        )

        recommendation = recommend_config(request)

        self.assertEqual(len(recommendation.ranking), 4)
        self.assertLessEqual(
            recommendation.best.metrics.avg_wait,
            run_simulation(base).metrics.avg_wait,
        )
        self.assertIn(recommendation.best.config.num_windows, [3, 4])

    # 验证推荐候选改变窗口和座位数时会同步扩展布局资源。
    def test_recommendation_resizes_layout_for_candidate_resource_counts(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[LayoutTableData(id="T1", x=20, y=20, table_type="four_seat", capacity=4)],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=1,
                num_seats=4,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=30,
                layout=layout,
            ),
            window_options=[2],
            seat_options=[8],
            stagger_options=[0],
            top_k=1,
        )

        recommendation = recommend_config(request)

        self.assertEqual(recommendation.best.config.num_windows, 2)
        self.assertEqual(recommendation.best.config.num_seats, 8)
        self.assertIsNotNone(recommendation.best.config.layout)
        self.assertEqual(len(recommendation.best.config.layout.windows), 2)
        self.assertEqual(sum(table.capacity for table in recommendation.best.config.layout.tables), 8)

    # 验证推荐生成候选布局时保留已有自定义坐标和餐桌旋转。
    def test_recommendation_preserves_custom_layout_coordinates_for_candidates(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=35, y=155)],
            windows=[
                LayoutWindowData(id="W1", x=145, y=75),
                LayoutWindowData(id="W2", x=230, y=75),
            ],
            tables=[
                LayoutTableData(id="T1", x=90, y=280, table_type="two_seat", capacity=2, rotation=90),
                LayoutTableData(id="T2", x=170, y=280, table_type="four_seat", capacity=4),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=6,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=31,
                layout=layout,
            ),
            window_options=[3],
            seat_options=[8],
            stagger_options=[0],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_layout = recommendation.best.config.layout
        self.assertIsNotNone(candidate_layout)
        self.assertEqual(len(candidate_layout.windows), 3)
        self.assertEqual(sum(table.capacity for table in candidate_layout.tables), 8)
        self.assertEqual(candidate_layout.doors[0].x, 35)
        self.assertEqual(candidate_layout.windows[0].x, 145)
        self.assertEqual(candidate_layout.tables[0].x, 90)
        self.assertEqual(candidate_layout.tables[0].rotation, 90)

    # 验证座位数不变时推荐不会重建已有餐桌类型和容量。
    def test_recommendation_keeps_custom_table_types_when_seat_count_is_unchanged(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=35, y=155)],
            windows=[
                LayoutWindowData(id="W1", x=145, y=75),
                LayoutWindowData(id="W2", x=230, y=75),
            ],
            tables=[
                LayoutTableData(id="T1", x=90, y=280, table_type="six_seat", capacity=6),
                LayoutTableData(id="T2", x=170, y=280, table_type="two_seat", capacity=2),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=8,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=32,
                layout=layout,
            ),
            window_options=[2],
            seat_options=[8],
            stagger_options=[10],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_layout = recommendation.best.config.layout
        self.assertEqual([table.capacity for table in candidate_layout.tables], [6, 2])
        self.assertEqual([table.table_type for table in candidate_layout.tables], ["six_seat", "two_seat"])

    # 验证校园推荐会把教学楼分配到多个错峰下课时间。
    def test_recommendation_splits_campus_buildings_into_dismissal_peaks(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=90)],
                ),
                CampusBuildingDemandData(
                    building_id="siyuan",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=80)],
                ),
                CampusBuildingDemandData(
                    building_id="yifu",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=70)],
                ),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=120,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=5.0,
                duration_min=80,
                seed=43,
                campus_demand=campus,
            ),
            window_options=[2],
            seat_options=[120],
            stagger_options=[10],
            peak_count_options=[3],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_campus = recommendation.best.config.campus_demand
        self.assertIsNotNone(candidate_campus)
        self.assertEqual({building.building_id for building in candidate_campus.buildings}, {"no9", "siyuan", "yifu"})
        self.assertEqual(sorted({building.dismissal_minute for building in candidate_campus.buildings}), [0, 10, 20])
        self.assertEqual(recommendation.best.config.stagger_minutes, 0)
        self.assertIn("3 峰下课", recommendation.best.strategy)
        self.assertIn("间隔 10 分钟", recommendation.best.strategy)

    # 验证校园推荐候选使用快速估算器，不为每个候选跑完整仿真。
    def test_campus_recommendation_uses_fast_estimator_for_candidates(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=80)],
                ),
                CampusBuildingDemandData(
                    building_id="siyuan",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=70)],
                ),
                CampusBuildingDemandData(
                    building_id="yifu",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=60)],
                ),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=4,
                num_seats=120,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=5.0,
                duration_min=80,
                seed=44,
                campus_demand=campus,
            ),
            window_options=[2, 3, 4, 5, 6, 7],
            seat_options=[60, 80, 100, 120, 140, 160, 180, 200],
            stagger_options=[0, 5, 10, 15],
            peak_count_options=[1, 2, 3, 4],
            top_k=4,
        )
        estimator_calls = []
        original_estimator = optimization_module._estimate_recommendation_metrics

        def counted_estimator(config):
            estimator_calls.append(config)
            return original_estimator(config)

        optimization_module._estimate_recommendation_metrics = counted_estimator
        try:
            recommendation = optimization_module.recommend_config(request)
        finally:
            optimization_module._estimate_recommendation_metrics = original_estimator

        self.assertFalse(hasattr(optimization_module, "run_simulation"))
        self.assertGreater(len(estimator_calls), 1)
        self.assertEqual(len(recommendation.ranking), 4)
        self.assertGreater(recommendation.baseline_metrics.total_arrived, 0)
        self.assertTrue(any("峰下课" in candidate.strategy for candidate in recommendation.ranking))

    # 验证推荐估算器把用户自定义宿舍释放 profile 传给混合校园到达表。
    def test_recommendation_estimator_uses_custom_residential_release_profile(self):
        profile = ResidentialReleaseProfile("lunch", 700, 710, 705, "uniform", 0.25)
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[],
            residential_sources=[],
            population_pool=CampusPopulationPoolData(
                enabled=True,
                meal_period="lunch",
                total_population_pool=100,
                meal_participation_rate=1.0,
            ),
            residential_release_profile=profile,
            meal_period="lunch",
        )
        config = SimulationConfigData(
            campus_demand=campus,
            simulation_start_minute=700,
            seed=51,
        )
        captured: dict[str, object] = {}
        original = optimization_module.build_mixed_campus_arrival_schedule

        def fake_build_mixed_campus_arrival_schedule(**kwargs):
            captured["profile"] = kwargs.get("residential_release_profile")
            passed_profile = kwargs.get("residential_release_profile")
            if passed_profile is None:
                return {"schedule": {660: 65}, "breakdown": {}}
            return {"schedule": {passed_profile.start_minute: 25}, "breakdown": {}}

        optimization_module.build_mixed_campus_arrival_schedule = fake_build_mixed_campus_arrival_schedule
        try:
            schedule = optimization_module._estimate_arrival_schedule(config)
        finally:
            optimization_module.build_mixed_campus_arrival_schedule = original

        self.assertIs(captured["profile"], profile)
        self.assertEqual(schedule, {0: 25.0})

    # 验证手动到达模式下推荐候选同样走快速估算器。
    def test_manual_recommendation_uses_fast_estimator_for_candidates(self):
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=4,
                num_seats=120,
                arrival_rate=8.0,
                service_time_mean=3.0,
                dining_time_mean=20.0,
                duration_min=60,
                seed=45,
                peak_start_min=15,
                peak_end_min=40,
                peak_multiplier=1.4,
            ),
            window_options=[3, 4, 5, 6],
            seat_options=[80, 100, 120, 140, 160],
            stagger_options=[0, 5, 10],
            top_k=3,
        )

        estimator_calls = []
        original_estimator = optimization_module._estimate_recommendation_metrics

        def counted_estimator(config):
            estimator_calls.append(config)
            return original_estimator(config)

        optimization_module._estimate_recommendation_metrics = counted_estimator
        try:
            recommendation = optimization_module.recommend_config(request)
        finally:
            optimization_module._estimate_recommendation_metrics = original_estimator

        self.assertFalse(hasattr(optimization_module, "run_simulation"))
        self.assertGreater(len(estimator_calls), 1)
        self.assertEqual(len(recommendation.ranking), 3)
        self.assertGreater(recommendation.baseline_metrics.total_arrived, 0)
        self.assertTrue(any(candidate.config.num_windows > request.base_config.num_windows for candidate in recommendation.ranking))

    # 验证同一小组内的成员仍会按窗口队列和距离独立选择排队窗口。
    def test_party_members_choose_windows_independently(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0),
                LayoutWindowData(id="W2", x=80, y=0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=22,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)

        runner._enqueue_arrivals(students)

        self.assertEqual(students[0].party_id, students[1].party_id)
        self.assertEqual([len(queue) for queue in runner.queues], [1, 1])
        self.assertEqual({student.window_index for student in students}, {0, 1})
        self.assertEqual(runner.metrics_counters["party_window_split_count"], 1)

    # 验证窗口选择使用预计完成排队成本，而不是只看队伍长度。
    def test_window_choice_avoids_short_queue_with_long_remaining_service(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0),
                LayoutWindowData(id="W2", x=20, y=0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                service_time_mean=3.0,
                layout=layout,
                seed=101,
            )
        )
        busy_student = runner._create_party_students(minute=0, person_count=1)[0]
        runner.windows[0] = WindowService(student=busy_student, remaining=30)
        runner.queues[1] = runner._create_party_students(minute=0, person_count=2)
        candidate = runner._create_party_students(minute=1, person_count=1)[0]

        self.assertEqual(runner._choose_window_for_student(candidate), 1)

    # 验证相同队长下，服务能力更高的窗口有更低预计完成成本。
    def test_window_choice_prefers_faster_window_with_equal_queue_length(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0, service_rate_factor=0.5),
                LayoutWindowData(id="W2", x=100, y=0, service_rate_factor=2.0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                service_time_mean=4.0,
                layout=layout,
                seed=102,
            )
        )
        runner.queues[0] = runner._create_party_students(minute=0, person_count=2)
        runner.queues[1] = runner._create_party_students(minute=0, person_count=2)
        candidate = runner._create_party_students(minute=1, person_count=1)[0]

        self.assertEqual(runner._choose_window_for_student(candidate), 1)

    # 验证实时地图快照暴露排队、等座、入座小组和餐桌占用信息。
    def test_snapshot_exposes_party_locations_for_live_map(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0),
                LayoutWindowData(id="W2", x=80, y=0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=22,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        runner._enqueue_arrivals(students)

        queued_snapshot = runner._snapshot()

        self.assertEqual(
            sorted(group["member_count"] for group in queued_snapshot["queue_groups"]),
            [1, 1],
        )
        self.assertEqual({group["party_id"] for group in queued_snapshot["queue_groups"]}, {students[0].party_id})
        self.assertEqual(queued_snapshot["table_occupancy"][0]["party_count"], 0)

        party = runner.parties[students[0].party_id]
        runner.queues = [[], []]
        for student in students:
            student.window_index = 0
            student.service_end_time = 3
        party.ready_time = 3
        runner.waiting_for_seat.append(party)
        waiting_snapshot = runner._snapshot()
        self.assertEqual(waiting_snapshot["waiting_parties"][0]["window_index"], 0)
        runner._seat_waiting_students(minute=4)
        runner._advance_walking_to_seats(end_time_sec=5 * 60)

        seated_snapshot = runner._snapshot()

        self.assertEqual(seated_snapshot["seated_parties"][0]["party_id"], students[0].party_id)
        self.assertEqual(seated_snapshot["seated_parties"][0]["size"], 2)
        self.assertEqual(seated_snapshot["seated_parties"][0]["table_id"], "T1")
        self.assertEqual(seated_snapshot["table_occupancy"][0]["party_count"], 1)

    # 验证结伴小组入座时会被安排到同一张有足够容量的餐桌。
    def test_party_seating_keeps_companions_at_one_table(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=20, y=20, table_type="two_seat", capacity=2),
                LayoutTableData(id="T2", x=80, y=20, table_type="two_seat", capacity=2),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=23,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        for student in students:
            student.service_end_time = 3
        party.ready_time = 3
        runner.waiting_for_seat.append(party)

        seated = runner._seat_waiting_students(minute=4)
        arrived = runner._advance_walking_to_seats(end_time_sec=5 * 60)

        self.assertEqual(seated, 2)
        self.assertEqual(arrived, 2)
        self.assertEqual(runner.table_occupied_seats, [2, 0])
        self.assertEqual({student.seat_time for student in students}, {5})
        self.assertEqual(runner.metrics_counters["party_split_count"], 0)

    # 验证单人学生在有空桌时优先选择空桌而不是拼桌。
    def test_solo_student_prefers_empty_table_before_sharing(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=15, y=20, table_type="four_seat", capacity=4),
                LayoutTableData(id="T2", x=120, y=20, table_type="four_seat", capacity=4),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                layout=layout,
                party_size_distribution={1: 1.0},
                seed=24,
            )
        )
        occupied_student = runner._create_party_students(minute=0, person_count=1)[0]
        occupied_student.window_index = 0
        runner.table_occupied_seats[0] = 1
        runner.table_party_ids[0].add(occupied_student.party_id)
        solo = runner._create_party_students(minute=1, person_count=1)[0]
        solo.window_index = 0
        solo.service_end_time = 2
        party = runner.parties[solo.party_id]
        party.ready_time = 2
        runner.waiting_for_seat.append(party)

        runner._seat_waiting_students(minute=3)

        self.assertEqual(party.table_index, 1)

    # 验证选座随机效用模型在固定 seed 下可复现。
    def test_table_choice_temperature_is_reproducible_with_seed(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=20, y=20, table_type="two_seat", capacity=2),
                LayoutTableData(id="T2", x=20, y=-20, table_type="two_seat", capacity=2),
            ],
        )

        def choices_for_seed(seed: int) -> list[int]:
            runner = DiningSimulationRunner(
                SimulationConfigData(
                    num_windows=1,
                    num_seats=4,
                    layout=layout,
                    table_choice_temperature=1.0,
                    party_size_distribution={1: 1.0},
                    seed=seed,
                )
            )
            student = runner._create_party_students(minute=0, person_count=1)[0]
            student.window_index = 0
            student.service_end_time = 1
            party = runner.parties[student.party_id]
            party.ready_time = 1
            return [runner._choose_table_for_party(party) for _ in range(6)]

        first = choices_for_seed(1)
        second = choices_for_seed(1)

        self.assertEqual(first, second)
        self.assertGreater(len(set(first)), 1)

    # 验证碎片化座位统计覆盖“总空座足够，但没有单桌可容纳小队”的场景。
    def test_fragmented_seats_counts_scattered_empty_tables_for_waiting_party(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=20, y=20, table_type="two_seat", capacity=2),
                LayoutTableData(id="T2", x=80, y=20, table_type="two_seat", capacity=2),
                LayoutTableData(id="T3", x=140, y=20, table_type="three_seat", capacity=3),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=7,
                layout=layout,
                party_size_distribution={3: 1.0},
                seed=26,
            )
        )
        students = runner._create_party_students(minute=0, person_count=3)
        party = runner.parties[students[0].party_id]
        party.ready_time = 2
        runner.waiting_for_seat.append(party)
        runner.table_occupied_seats[2] = 1

        self.assertEqual(runner._fragmented_seats(), 6)

    # 验证同行服务结束时间不同会进入集合等待指标。
    def test_party_gather_and_seat_wait_metrics_are_reported(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=27,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        for index, student in enumerate(students):
            student.window_index = 0
            student.service_end_time = 2 + index * 3
        party.ready_time = 5
        runner.waiting_for_seat.append(party)

        runner._seat_waiting_students(minute=5)
        runner._advance_walking_to_seats(end_time_sec=6 * 60)
        metrics = runner._build_metrics()

        self.assertGreater(metrics.avg_party_gather_wait, 0)
        self.assertEqual(metrics.avg_seat_wait, 0)
        self.assertEqual(metrics.avg_party_seat_wait, 0)
        self.assertGreater(metrics.avg_post_service_to_seat_time, 0)

    # 验证窗口忙碌期利用率和全程利用率分开统计，避免到达后就餐尾段稀释服务压力。
    def test_active_window_utilization_is_reported_separately_from_whole_run_utilization(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=1,
                num_seats=30,
                arrival_rate=8.0,
                service_time_mean=0.5,
                dining_time_mean=30.0,
                duration_min=5,
                seed=20260613,
            )
        )

        self.assertGreater(result.metrics.active_window_utilization, result.metrics.window_utilization)
        self.assertLessEqual(result.metrics.active_window_utilization, 1.0)

    # 验证高级移动指标明显拥堵时，瓶颈分类优先报告动线拥堵而不是到达高峰。
    def test_movement_pressure_can_be_reported_as_bottleneck(self):
        runner = DiningSimulationRunner(SimulationConfigData())

        bottleneck = runner._classify_bottleneck(
            peak_queue=15,
            peak_waiting_for_seat=0,
            avg_seat_wait=0,
            seat_utilization=0.05,
            window_utilization=0.04,
            movement={
                "avg_walking_time": 332.0,
                "avg_stuck_ticks": 4.7,
                "movement_conflict_count": 100,
                "max_density": 6,
            },
        )

        self.assertEqual(bottleneck, "动线拥堵")

    # 验证静止状态的高 stuck_ticks 不会单独触发动线拥堵分类。
    def test_stationary_stuck_ticks_do_not_trigger_movement_bottleneck(self):
        runner = DiningSimulationRunner(SimulationConfigData())

        bottleneck = runner._classify_bottleneck(
            peak_queue=0,
            peak_waiting_for_seat=0,
            avg_seat_wait=0,
            seat_utilization=0.05,
            window_utilization=0.04,
            movement={
                "avg_walking_time": 0.0,
                "avg_stuck_ticks": 0.0,
                "movement_conflict_count": 0,
                "max_density": 1,
            },
        )

        self.assertEqual(bottleneck, "运行平衡")

    # 验证默认关闭的占座实验功能开启后会提前预留座位，且不超过桌面容量。
    def test_preempt_seat_probability_reserves_table_capacity_when_enabled(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="two_seat", capacity=2)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=2,
                layout=layout,
                party_size_distribution={2: 1.0},
                preempt_seat_probability=1.0,
                seat_holder_min_party_size=2,
                seed=28,
            )
        )

        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]

        self.assertEqual(party.reserved_table_index, 0)
        self.assertEqual(runner.table_reserved_seats, [2])
        self.assertLessEqual(runner.table_occupied_seats[0] + runner.table_reserved_seats[0], layout.tables[0].capacity)

        record = runner._build_record(
            t=0,
            arrived_count=2,
            served_count=0,
            seated_count=0,
            left_count=0,
        )

        self.assertEqual(record.empty_seats, 2)
        self.assertEqual(record.reserved_seats, 2)
        self.assertEqual(record.available_seats, 0)
        self.assertEqual(record.snapshot["empty_seats"], 2)
        self.assertEqual(record.snapshot["reserved_seats"], 2)
        self.assertEqual(record.snapshot["available_seats"], 0)

    # 验证预占座失效时释放旧桌 reserved 容量，避免座位泄漏。
    def test_invalid_preemptive_reservation_releases_reserved_capacity(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
            windows=[LayoutWindowData(id="W1", x=156, y=24, wall_side="top")],
            tables=[LayoutTableData(id="T1", x=220, y=260, table_type="two_seat", capacity=2)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=2,
                layout=layout,
                party_size_distribution={2: 1.0},
                preempt_seat_probability=1.0,
                seat_holder_min_party_size=2,
                movement_model="advanced_floor_field",
                advanced_movement_coupling=True,
                seed=29,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        self.assertEqual(runner.table_reserved_seats[0], 2)
        runner.pedestrian_engine.grid.table_approach_cells[0].clear()

        reserved = runner._reserved_table_for_party(party)

        self.assertIsNone(reserved)
        self.assertIsNone(party.reserved_table_index)
        self.assertEqual(runner.table_reserved_seats[0], 0)

    # 验证取餐完成小组通过后端 timeline 行走到餐桌并最终入座。
    def test_ready_party_walks_to_seat_through_backend_timeline(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=120)],
            windows=[LayoutWindowData(id="W1", x=120, y=24)],
            tables=[LayoutTableData(id="T1", x=220, y=220, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=8.0,
                duration_min=5,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=25,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        for student in students:
            student.window_index = 0
            student.service_end_time = 5
        party.ready_time = 5
        runner.waiting_for_seat.append(party)
        runner.current_minute = 5

        record = runner.step()

        timeline = record.snapshot["timeline"]
        event = timeline["events"][0]
        self.assertEqual(record.seated_count, 2)
        self.assertEqual(event["type"], "walk_to_seat")
        self.assertEqual(event["party_id"], party.party_id)
        self.assertEqual(event["table_id"], "T1")
        self.assertEqual(event["window_index"], 0)
        self.assertGreater(event["duration_sec"], 0)
        self.assertLess(event["duration_sec"], 60)
        self.assertEqual(event["frames"][0]["progress"], 0)
        self.assertEqual(event["frames"][-1]["progress"], 1)
        self.assertEqual(event["path"][0], event["from"])
        self.assertEqual(event["path"][-1], event["to"])
        self.assertGreaterEqual(timeline["playback_ms"], event["playback_end_ms"])
        self.assertEqual(record.snapshot["walking_parties"], [])
        self.assertEqual(record.snapshot["seated_parties"][0]["party_id"], party.party_id)
        self.assertEqual(record.snapshot["table_occupancy"][0]["occupied"], 2)


if __name__ == "__main__":
    unittest.main()
