# 检查讲解注释分支任务说明

本分支 `inspection-commented` 专门用于课程检查前的讲解准备。目标是让项目代码更容易现场讲清楚，而不是重构功能或改变运行效果。

## 总目标

在不改变系统功能、不改变接口行为、不破坏现有运行方式的前提下，为关键文件补充中文讲解注释，并补充一份检查讲解文档。注释应帮助不熟悉 Python、Vue、FastAPI 的同学快速说明：这个文件负责什么、核心函数怎么被调用、一次仿真请求从前端到后端如何流转。

## 严格禁止

- 不要重写核心算法。
- 不要调整仿真数值逻辑。
- 不要改变接口路径、字段名、返回结构。
- 不要引入新的外部依赖。
- 不要大规模格式化全文件。
- 不要把主分支 `main` 作为工作分支。

## 建议工作分支

```bash
git fetch origin
git checkout inspection-commented
git pull origin inspection-commented
```

## 需要重点加注释的文件

### 1. `README.md`

补充一个“检查时如何介绍项目”的小节，包含：

- 项目背景：食堂高峰期排队、窗口、座位问题。
- 项目目标：模拟就餐过程，统计指标，给出优化建议。
- 运行流程：启动后端、启动前端、配置参数、开始仿真、查看结果。
- 文件结构：frontend、backend、tests、data、doc、scripts 各负责什么。

### 2. `frontend/src/App.vue`

在关键区域补充中文注释：

- `defaultConfig`：默认仿真参数，例如窗口数、座位数、到达率、服务时间。
- `ref` / `reactive` 状态：解释 `runId`、`records`、`metrics`、`currentState`。
- `checkHealth()`：前端如何确认后端是否连接。
- `validateConfig()`：参数校验如何触发。
- `startLiveRun()`：点击开始仿真后的入口。
- `singleStep()`：一次单步请求如何发送到后端，后端返回后如何更新页面。
- `appendRunRecord()`：过程记录如何追加并驱动图表刷新。
- `generateRecommendation()`：优化推荐如何调用后端接口。
- `renderCharts()` / `trendOption()`：ECharts 图表数据来源。

注释风格应简洁，不要每一行都注释，重点解释“为什么”和“数据流”。

### 3. `frontend/src/api.js`

在每个接口旁补充用途注释：

- `/health`：健康检查。
- `/config/validate`：参数校验。
- `/sim/step`：实时单步仿真。
- `/sim/run`：完整仿真。
- `/optimize/recommend`：优化推荐。
- `/explain`：规则化解释。
- `/export/{runId}`：导出 CSV。

### 4. `frontend/vite.config.js`

补充注释说明：

- Vite 前端默认端口是 5173。
- `/api` 请求通过 proxy 转发到 FastAPI 后端 8001。
- 这样前端代码里可以写 `/api/...`，不需要直接写完整后端地址。

### 5. `backend/app/main.py`

在接口分组处补充中文注释：

- FastAPI 应用入口。
- CORS 为什么允许 `127.0.0.1:5173`。
- `STORE` 用于保存 SQLite 数据。
- `ACTIVE_RUNS` 用于保存正在进行的实时仿真。
- `/api/sim/step` 如何通过 `_resolve_runner()` 找到仿真器，再调用 `runner.step()`。
- 仿真结束后为什么保存结果并返回 `metrics`。

### 6. `backend/app/schemas.py`

补充注释说明 Pydantic 模型的作用：

- `SimulationConfig` 是前端传来的核心配置。
- `Field` 用于限制参数范围。
- `to_data()` 把接口模型转换成仿真内部 dataclass。
- `RunResponse`、`StepResponse` 分别对应完整仿真和单步仿真的返回值。

### 7. `backend/app/simulation.py`

这是检查最重要的文件。补充模块级注释和关键类/函数注释：

- 文件开头说明：这是核心离散时间仿真模块。
- `SimulationConfigData`：仿真参数。
- `Student`：单个学生。
- `DiningParty`：结伴就餐小组。
- `StepRecord`：每一分钟的过程记录。
- `MetricsSummary`：最终指标汇总。
- `run_simulation()`：完整运行直到结束。
- `DiningSimulationRunner`：保存当前仿真状态。
- `step()`：推进一分钟，重点写清顺序：
  1. 处理吃完离开。
  2. 推进窗口服务。
  3. 取餐完成的小组进入等座。
  4. 给等座小组分配餐桌。
  5. 生成本分钟新到达学生。
  6. 新学生选择窗口并排队。
  7. 空闲窗口开始服务。
  8. 推进走向座位动画。
  9. 生成 StepRecord。
- `_generate_arrivals()`：手动到达与校园到达两种模式。
- `_choose_window_for_student()`：按队伍长度和距离选择窗口。
- `_choose_table_for_party()`：按容量、距离、拼桌、浪费座位等因素选择餐桌。
- `_build_metrics()`：统计平均等待、排队峰值、利用率、瓶颈类型。
- `_classify_bottleneck()`：解释座位容量、窗口服务、到达高峰、运行平衡四类判断。

### 8. `backend/app/optimization.py`

补充注释说明：

- 推荐模块通过枚举候选方案进行比较。
- 候选包括窗口数、座位数、错峰时间、下课峰数。
- `_score_candidate()` 中等待时间、峰值排队、等座人数、资源成本都会影响评分。
- 分数越低表示方案越优。

### 9. `backend/app/explanation.py`

补充注释说明：

- 这里是规则化解释，不依赖外部大模型。
- 根据瓶颈、基准指标和推荐指标生成说明文本。

### 10. `backend/app/storage.py`

补充注释说明：

- SQLite 表的作用。
- `save_result()` 保存配置、过程记录和指标。
- `export_records_csv()` 导出每分钟记录。

## 需要新增的讲解文档

新增：`doc/inspection_walkthrough.md`

建议结构：

```markdown
# 北京交通大学就餐仿真系统检查讲解稿

## 1. 一句话介绍
## 2. 项目文件结构
## 3. 启动方式
## 4. 一次仿真从点击到结果的运行流程
## 5. 前端关键文件说明
## 6. 后端关键文件说明
## 7. 核心仿真算法说明
## 8. 指标与瓶颈判断
## 9. 优化推荐逻辑
## 10. 老师可能追问的问题与回答
```

## 验证要求

完成注释和文档后至少运行：

```bash
python -m unittest tests.test_storage tests.test_simulation
cd frontend && npm run build
```

如果环境缺少 Node 或 Python 依赖，需要在最终说明中写清楚未运行的原因，不要假装已经通过。

## 最终提交要求

提交信息建议：

```bash
git add README.md frontend/src/App.vue frontend/src/api.js frontend/vite.config.js backend/app/main.py backend/app/schemas.py backend/app/simulation.py backend/app/optimization.py backend/app/explanation.py backend/app/storage.py doc/inspection_walkthrough.md doc/inspection_comment_task.md
git commit -m "docs: add inspection-oriented comments and walkthrough"
git push origin inspection-commented
```

最终输出请包含：

- 修改了哪些文件。
- 没有改动哪些运行逻辑。
- 测试/构建是否通过。
- 检查时推荐从哪个文件开始讲。
