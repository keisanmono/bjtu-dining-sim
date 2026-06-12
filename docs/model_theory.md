# 食堂内部行为仿真模型说明

本项目不是把食堂过程写成一组拍脑袋规则，而是在现有 FastAPI + Vue 架构上采用一个轻量混合仿真模型。当前实现仍按分钟推进，保留前端实时动画和已有数据结构；新增逻辑主要集中在窗口选择、选座、同行小队同步和可选预占座。

## 1. 窗口服务：排队论视角

高校食堂窗口可以近似看作多服务台有限容量排队系统，参考 M/M/C/K 思想：学生到达率记作 `lambda`，单窗口服务率记作 `mu`，开放窗口数为 `C`，系统容量为 `K`。项目中 `arrival_rate` 对应到达强度，`service_time_mean` 与窗口 `service_rate_factor` 共同决定服务率，`num_windows` 或布局中的窗口数对应 `C`。

当前实现没有直接套用闭式公式求解 M/M/C/K，而是在离散时间仿真中记录相同口径的可观测指标：平均排队等待 `avg_queue_wait`、峰值队列 `peak_queue`、窗口利用率 `window_utilization` 和吞吐量 `throughput`。窗口选择也从旧的“队长 + 距离”升级为预计完成成本：

```text
expected_window_cost =
    当前窗口正在服务学生的剩余服务时间
  + 当前队列人数 * 该窗口平均服务时长
  + 入口到窗口的步行时间
```

这让服务能力更高、当前剩余服务更短的窗口自然更有吸引力，也能支撑开放窗口数量、错峰策略和队列管理的 what-if 分析。

## 2. 全流程：DES 与离散时间推进

项目的 `DiningSimulationRunner.step()` 采用离散时间推进，每一步代表 1 分钟。它按固定顺序处理离开、窗口服务、等座、到达、排队、开始服务、步行入座和状态记录。这个工程实现属于离散事件仿真 DES 的简化版本：事件仍然是到达、服务完成、入座和离开，只是统一落到分钟刻度上推进，便于前端实时播放和课程展示。

优化推荐模块沿用 DES/排队管理思想，对窗口数、座位数和错峰参数做候选方案比较，服务于校园餐饮容量重分配与队列管理分析。

## 3. 学生个体：Agent-Based Modeling

每个 `Student` 都保存到达时间、排队时间、服务开始/结束时间、入座时间、离开时间和窗口编号。每个学生会根据当前环境状态选择窗口，再随着服务和座位状态变化推进生命周期。因此，系统整体拥堵不是直接写死的结果，而是多个个体在共享窗口、队列和餐桌资源上的交互结果。

## 4. 同行小队：Group Behavior 与同步等待

`DiningParty` 表示同行小队。组内成员可以分别排到不同窗口，但必须等所有成员取餐完成后才作为整体进入等座队列。这相当于 fork-join 同步：小队到达后分叉到个人服务流程，最后在取餐完成后汇合。

后端指标包括：

- `party_window_split_count`：同行小队成员被分配到多个窗口的次数。
- `avg_party_gather_wait`：同组第一名成员取餐完成到最后一名成员取餐完成的平均时间差。
- `avg_party_seat_wait`：小队取餐完成汇合后到入座之间的平均等待。
- `blocked_party_count`：因为没有同桌容量而等待过的小队数。
- `shared_table_count`：实际发生拼桌的次数。

## 5. 选座：随机效用与离散选择

选座从固定最小成本规则整理为随机效用模型。默认 `table_choice_temperature = 0`，仍然确定性选择成本最低的餐桌，保证测试和展示复现稳定；温度大于 0 时，使用 `softmax(-cost / temperature)` 按概率选择，模拟有限理性、视野误差和偏好扰动。

当前餐桌成本包括：

```text
table_cost =
    alpha_distance * distance
  + beta_share * sharing_penalty
  + gamma_waste * seat_waste
  - delta_empty * empty_table_bonus
  + crowd_penalty
```

容量约束始终优先：单桌可用座位不足以容纳整个 `party` 时不能选择该桌，因此随机性不会把一个同行小队拆到不同餐桌。

## 6. 食堂内部移动：路径规则与 Floor Field CA

当前版本仍采用“路径规则 + 动画帧”：取餐完成后，后端根据窗口服务点、餐桌坐标和餐桌障碍生成一条行走路径，再输出 `walking_to_seat`、`path` 和 `frames` 给前端播放。这保证了现有实时地图稳定。

后续可以替换为 Cellular Automaton / Floor Field 模型。CA 模型把食堂空间离散成网格，静态 Floor Field 表示每个格子到目标的距离势能，动态占用格子表示人群拥堵。学生每一步选择势能更低且未被占用的相邻格，从而自然形成绕行、避让和局部拥堵。项目已预留 `backend/app/floor_field.py`，包含：

- `grid_from_layout(layout)`：把布局转换为网格和障碍。
- `build_static_floor_field(layout, target)`：构造到目标的静态距离场。
- `next_cell_by_floor_field(agent, grid, target, occupied_cells)`：给出下一步候选格。

该模块暂不接入主流程，避免重写动画和仿真器；它是后续从规则路径升级到 Floor Field CA 的最小稳定骨架。

## 7. 可选预占座实验

参考大学食堂中的 preempting seat 行为，项目提供默认关闭的轻量实验参数：

- `preempt_seat_probability`，默认 `0.0`。
- `seat_holder_min_party_size`，默认 `2`。

当小队人数达到阈值且随机命中时，小队会提前为整组预留一张可容纳同桌的餐桌容量。预留通过现有 `table_reserved_seats` 表示，并保证 `occupied + reserved <= capacity`。所有成员取餐完成后，小队优先前往已预留桌；如果没有预留成功，则回到普通选座流程。

默认关闭时，主流程与既有结果保持接近；开启后可用于研究占座对座位利用率、等座小队和碎片化座位的影响。
