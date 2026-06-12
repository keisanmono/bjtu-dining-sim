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

## 6. 食堂内部移动：三种 movement_model

食堂内部移动现在支持三种模型，默认仍是稳定的几何路径规则：

1. `path`：原有“路径规则 + 动画帧”。后端根据窗口服务点、餐桌坐标和餐桌障碍生成行走路径，再输出 `walking_to_seat`、`path` 和 `frames` 给前端播放。该模式是默认值，用于保证既有仿真结果和实时地图行为不被高级模型影响。
2. `static_floor_field`：静态 Floor Field 路径。后端把布局离散成网格，餐桌主体为 blocked cell，餐桌周围 approach cell 可达；然后从目标格反向 BFS 构造静态距离场，行走路径按距离场下降生成，避免穿过 blocked cell。
3. `advanced_floor_field`：动态 Floor Field / Cellular Automaton 微观移动。`DiningSimulationRunner.step()` 仍按分钟推进 DES/ABM 主流程，但 `PedestrianEngine` 在每分钟内部运行多个 movement tick，用于更新学生在网格中的微观位置、冲突、拥堵和热力图。

高级 CA 模型包括：

- 静态场：由目标集合反向扩散，表示到窗口、队列格、餐桌 approach cell 或出口的距离。
- 动态场：行人每 tick 在当前格 deposit，随后按 `dynamic_field_decay` 衰减并按 `dynamic_field_diffusion` 扩散。
- 密度惩罚：按邻域占用计算局部密度，使候选格成本随拥堵升高。
- 并行更新：所有可移动 agent 先同时选择 intended cell，再统一解决冲突。
- 冲突解决：多个 agent 选择同一目标格时，低成本者进入，其余等待并累计 `conflict_count`。
- 同伴凝聚：同一 `party_id` 的成员按 group center 产生凝聚成本，减少同行小队无限分散。
- 物理队列位置：窗口 service cell 和 queue cells 会作为微观目标，前端可直接绘制 agent cell 坐标。

高级模型的候选格成本采用 Social-Force-inspired 项，而不是完整连续 Social Force 或 ORCA：

```text
cost(cell, agent) =
    floor_static_weight * static_distance(cell, target)
  + floor_density_weight * density_penalty(cell)
  - floor_dynamic_weight * dynamic_field_value(cell)
  + floor_wall_weight * wall_penalty(cell)
  + floor_inertia_weight * turn_penalty(previous, current, cell)
  + floor_group_weight * group_distance_penalty(party, cell)
  + random_noise
```

因此当前实现是 Floor Field CA 主体加上 Social-Force-inspired 成本项：它能表达目标吸引、局部避让、墙体/障碍惩罚和同伴吸引，但不求解连续速度、加速度或 ORCA 半平面避碰。

## 7. 可选预占座实验

参考大学食堂中的 preempting seat 行为，项目提供默认关闭的轻量实验参数：

- `preempt_seat_probability`，默认 `0.0`。
- `seat_holder_min_party_size`，默认 `2`。

当小队人数达到阈值且随机命中时，小队会提前为整组预留一张可容纳同桌的餐桌容量。预留通过现有 `table_reserved_seats` 表示，并保证 `occupied + reserved <= capacity`。所有成员取餐完成后，小队优先前往已预留桌；如果没有预留成功，则回到普通选座流程。

默认关闭时，主流程与既有结果保持接近；开启后可用于研究占座对座位利用率、等座小队和碎片化座位的影响。

## 参考文献

1. Yuan Ningman, Wang Xianhua, Chen Xiaoxin. “Analysis on the Service Capacity of University Canteens under the Epidemic Prevention Based on Queue Theory.”
2. Tang Tie-Qiao, Zhang Bo-Tao, Xie Chuan-Zhi. “Modeling and simulation of pedestrian flow in university canteen.”
3. Kambli et al. “Improving campus dining operations using capacity and queue management: A simulation-based case study.”
4. Rajaei, Khakzad. “A Real-World Example for Student Learning: BTSU Cafeteria Simulation.”
