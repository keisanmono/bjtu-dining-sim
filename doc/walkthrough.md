# 北京交通大学就餐仿真系统展示说明稿

这份文档用于课程展示现场口播。README 负责当项目总索引，本说明稿负责按展示顺序把“项目背景、页面操作、前后端调用、仿真核心、指标推荐”串起来。

## 1. 一句话介绍

我们第 20 组做的是北京交通大学就餐仿真系统。系统模拟食堂高峰期学生到达、排队取餐、等待座位、入座就餐和离开的过程，并用指标分析瓶颈，给出窗口、座位和错峰方面的优化推荐。

展示时可以先强调：这是一个前后端分离项目，前端负责配置和可视化，后端负责仿真计算、指标汇总、推荐和数据保存。

## 2. 项目文件结构

| 目录/文件 | 说明重点 |
|---|---|
| `README.md` | 项目总索引、启动方式、说明路线和 Mermaid 图 |
| `frontend/src/App.vue` | 页面主入口，保存表单状态、运行状态、指标状态 |
| `frontend/src/api.js` | axios 接口封装，统一访问 `/api/...` |
| `frontend/vite.config.js` | Vite 5173 端口和 `/api` proxy 配置 |
| `backend/app/main.py` | FastAPI 入口，定义连通性、参数校验、仿真、推荐、解释、导出接口 |
| `backend/app/schemas.py` | Pydantic 请求和响应模型 |
| `backend/app/simulation.py` | 核心离散时间仿真，每次 `step()` 推进一分钟 |
| `backend/app/storage.py` | SQLite 保存仿真配置、过程记录、指标、推荐、解释 |
| `backend/app/optimization.py` | 枚举候选方案并用评分排序 |
| `backend/app/explanation.py` | 本地规则化解释，不依赖外部大模型 |
| `tests/` | 核心仿真和存储测试 |

## 3. 启动方式

先启动后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。前端代码调用 `/api/...`，Vite 会代理到 `http://127.0.0.1:8001`，所以前端组件里不需要写完整后端地址。

## 4. 一次仿真从点击到结果的运行流程

可以按下面顺序说明实时仿真：

1. 用户在“参数配置”页填写窗口数、座位数、到达率、服务时间、就餐时间等参数。
2. 用户点击“开始仿真”。
3. `frontend/src/App.vue` 里的 `startLiveRun()` 切到实时运行页，并调用 `singleStep(true)` 发起第一次单步请求。
4. `singleStep()` 通过 `api.stepSimulation(payload)` 调用 `/api/sim/step`。
5. `backend/app/main.py` 的 `step_simulation()` 接收请求，用 `_resolve_runner()` 创建或取回当前运行的 `DiningSimulationRunner`。
6. `runner.step()` 推进一分钟，返回 `StepRecord` 和当前状态快照。
7. 前端把记录追加到 `records`，把状态放到 `currentState`，地图和 ECharts 图表随状态刷新。
8. 如果后端返回 `done=true` 和 `metrics`，前端停止定时单步，切到结果分析页。

现场演示时建议打开浏览器页面，同时打开 `App.vue`、`api.js`、`main.py`、`simulation.py` 四个文件，对照一次请求链路说明。

## 5. 前端关键文件说明

### `frontend/src/App.vue`

这个文件是前端主页面。它包含四个页签：参数配置、场景预览、实时运行、结果分析。

说明顺序：

1. 先看 `defaultConfig`，说明默认窗口数、座位数、到达率、服务时间、就餐时间和随机种子。
2. 再看 `ref` 和 `reactive` 状态，例如 `runId`、`records`、`metrics`、`currentState`。
3. 看 `checkHealth()`，说明页面右上角如何判断后端是否连接。
4. 看 `validateConfig()`，说明参数会先发给后端校验。
5. 看 `startLiveRun()` 和 `singleStep()`，说明实时仿真的入口和单步请求。
6. 看 `appendRunRecord()` 和 `renderCharts()`，说明过程记录如何驱动卡片和图表刷新。
7. 看 `generateRecommendation()`，说明前端如何请求优化推荐和规则化解释。

### `frontend/src/api.js`

这个文件统一封装后端接口。说明时重点说明：前端调用的是 `/api/health`、`/api/config/validate`、`/api/sim/step` 等路径，实际转发由 Vite proxy 完成。

### `frontend/vite.config.js`

这个文件说明前端服务端口是 5173，`/api` 请求转发到 FastAPI 后端 8001。展示时可以用它解释为什么浏览器只访问前端地址，也能调用后端接口。

## 6. 后端关键文件说明

### `backend/app/main.py`

这是 FastAPI 应用入口。说明重点：

1. `STORE` 是 SQLite 持久化对象。
2. `ACTIVE_RUNS` 保存正在实时运行的仿真器。
3. `/api/config/validate` 做参数校验。
4. `/api/sim/run` 一次完整运行并保存结果。
5. `/api/sim/step` 找到 runner 后调用 `runner.step()`，结束时保存结果并返回 `metrics`。
6. `/api/optimize/recommend` 和 `/api/explain` 分别生成推荐和规则化解释。
7. `/api/export/{run_id}` 导出 CSV。

### `backend/app/schemas.py`

这个文件定义接口模型。说明重点是 `SimulationConfig` 和 `StepRequest`：

- `SimulationConfig` 是前端传来的核心配置。
- `Field` 限定参数范围，例如窗口数、座位数、持续时间。
- `to_data()` 把 Pydantic 模型转换成后端仿真内部 dataclass。
- `RunResponse` 对应完整仿真返回，`StepResponse` 对应单步仿真返回。

### `backend/app/storage.py`

这个文件负责保存和导出。SQLite 表包括运行配置、每分钟过程记录、指标汇总、推荐结果和解释结果。`save_result()` 保存完整仿真结果，`export_records_csv()` 把每分钟记录导出为 CSV。

## 7. 核心仿真算法说明

核心类是 `DiningSimulationRunner`。它内部保存队列、窗口服务状态、等座队列、行走到座位的小组、已入座学生、餐桌占用情况和所有分钟记录。

`step()` 的顺序可以这样说明：

1. 处理已经吃完并离开的学生。
2. 推进窗口服务，找出本分钟取餐完成的学生。
3. 等同组成员都取餐完成后，把小组放入等座队列。
4. 给等座小组选择合适餐桌。
5. 生成本分钟新到达学生。
6. 新学生根据队伍长度和入口到窗口距离选择窗口排队。
7. 空闲窗口从队列中取学生开始服务。
8. 推进入座行走动画，把到达餐桌的小组转为已入座。
9. 生成 `StepRecord`，记录到达、取餐、入座、离开、空座、排队、等座和状态快照。

需要强调：这个顺序没有在展示准备中改动，只是补充了中文注释。

## 8. 指标与瓶颈判断

最终指标来自 `_build_metrics()`：

| 指标 | 含义 |
|---|---|
| `avg_wait` | 学生从到达到入座的平均等待时间 |
| `avg_queue_wait` | 从到达到开始窗口服务的平均等待 |
| `avg_seat_wait` | 取餐完成后等待座位的平均等待 |
| `peak_queue` | 全部窗口队列人数的峰值 |
| `peak_waiting_for_seat` | 等座人数峰值 |
| `throughput` | 成功入座就餐人数 |
| `seat_utilization` | 座位平均利用率 |
| `window_utilization` | 窗口平均利用率 |
| `bottleneck_type` | 后端规则判断出的瓶颈类型 |

瓶颈判断在 `_classify_bottleneck()` 中，根据等座人数、座位利用率、平均等座时间、排队峰值、窗口利用率和高峰倍数，分成座位容量、窗口服务、到达高峰、运行平衡四类。

## 9. 优化推荐逻辑

推荐逻辑在 `backend/app/optimization.py`。它不会重构核心仿真，也不依赖外部优化服务，而是：

1. 接收基准配置和候选范围。
2. 枚举窗口数、座位数、错峰分钟、下课峰数。
3. 对每个候选估算等待、排队、等座和利用率。
4. 用 `_score_candidate()` 计算综合评分。
5. 按评分从低到高排序，返回最佳方案和候选列表。

评分里等待时间、峰值排队、峰值等座、窗口成本、座位成本、错峰成本和过载惩罚都会产生影响。分数越低，说明方案在改善效果和资源成本之间更优。

`backend/app/explanation.py` 只负责把这些结果生成可读说明，它是规则化解释，不是外部大模型能力，核心仿真和推荐都可以独立运行。

## 10. 老师可能追问的问题与回答

| 追问 | 回答 |
|---|---|
| 为什么选择离散时间仿真？ | 食堂过程天然可以按分钟观察，离散时间模型容易解释、实现和测试。 |
| 学生怎么选择窗口？ | 后端会综合窗口当前队伍长度和入口到窗口的距离，选择代价最低的窗口。 |
| 小组怎么选餐桌？ | 后端会看容量是否够、距离、是否拼桌、空座浪费等因素，选择综合代价最低的餐桌。 |
| 为什么有随机种子？ | 为了让同一配置可以复现实验结果，方便演示和测试。 |
| 实时仿真为什么要保存 `ACTIVE_RUNS`？ | 因为每次 `/api/sim/step` 只推进一分钟，后端需要保存当前 runner 的队列、窗口、座位等状态。 |
| 快速完成和实时运行结果是否同源？ | 是。同源于 `DiningSimulationRunner`，只是 `/api/sim/run` 循环调用 `step()` 到结束。 |
| 数据库保存了什么？ | 保存运行配置、每分钟记录、最终指标、推荐结果和解释结果。 |
| 推荐结果是不是机器学习？ | 不是。这里是候选枚举加规则评分，更适合课程展示时解释原因。 |
| 规则化解释是不是调用大模型？ | 不是。`explanation.py` 是本地规则文本生成，核心功能不依赖 LLM。 |
| 本次展示准备改了功能吗？ | 没有。只扩写 README、增加说明文档、补充中文注释，不改接口字段、不改算法、不引入依赖。 |

## 建议现场打开顺序

1. `README.md`
2. 浏览器 `http://127.0.0.1:5173`
3. `frontend/src/App.vue`
4. `frontend/src/api.js`
5. `frontend/vite.config.js`
6. `backend/app/main.py`
7. `backend/app/schemas.py`
8. `backend/app/simulation.py`
9. `backend/app/optimization.py`
10. `backend/app/explanation.py`
11. `backend/app/storage.py`
