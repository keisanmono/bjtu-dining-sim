# 北京交通大学就餐仿真系统首版实现设计

## 依据

实现以 `doc/20_group_bjtu_dining_design_spec.md` 和 `doc/20_group_development_environment_setup.md` 为主。Markdown 中引用的界面与架构图没有附带图片资源，因此补充查看了原始 PDF 中第 6、9、13、14、15、18 页的部署拓扑、模块协同、页面原型、跳转关系和数据生命周期。

## 首版范围

首版完成课程演示闭环：参数配置、配置校验、完整仿真运行、单步推进、过程记录、指标分析、结果展示、推荐计算和规则化解释。LLM 模块保留后端接口和解释 DTO，默认使用规则模板，不依赖外部模型。

## 架构

项目采用 B/S 架构：

- `backend/`：Python 3.11 兼容的 FastAPI 服务，内部包含 CFG、DRV、ARR、QUE、DIN、REC、ANA、OPT、LLM-EXP 模块。
- `frontend/`：Vue 3 + Vite + Element Plus + ECharts 页面，实现配置页、实时运行页、结果分析页和优化推荐页。
- `data/`：SQLite 数据库与导出文件目录。
- `tests/`：标准库 `unittest` 覆盖核心仿真行为，避免当前环境缺少 pytest 时无法验证核心逻辑。

## 后端数据流

`SimulationConfig` 进入仿真引擎后，驱动器按分钟推进。每一分钟先释放已完成就餐的座位，再完成窗口服务、安排入座、生成新到学生，并将学生分配到最短窗口队列。每一步产生 `StepRecord`，完整运行结束后由分析模块生成 `MetricsSummary`。

指标包括平均等待时间、峰值排队长度、累计接待人数、空座位变化、窗口利用率、座位利用率和瓶颈类型。优化模块对窗口数、座位数、错峰分钟数的候选组合批量运行仿真，并按等待、队列、资源成本与过载惩罚综合评分。

## REST 接口

首版提供以下接口：

- `GET /api/health`
- `POST /api/config/validate`
- `POST /api/sim/run`
- `POST /api/sim/step`
- `GET /api/run/{run_id}/records`
- `GET /api/run/{run_id}/metrics`
- `POST /api/optimize/recommend`
- `POST /api/explain`
- `GET /api/export/{run_id}`

## 前端布局

前端按 PDF 原型实现：

- 参数配置页：基础参数表单、场景说明、窗口与座位预览三栏布局。
- 实时运行页：顶部控制条、当前时刻、指标卡片、窗口队列柱状图、座位矩阵和关键指标趋势。
- 结果分析页：汇总指标、趋势曲线、过程记录表和导出入口。
- 优化推荐页：推荐摘要、方案对比表、规则解释和备选策略。

## 验证

核心仿真用 `python -m unittest` 验证可复现、记录长度、指标口径、座位瓶颈和优化推荐排序。FastAPI 与 Vue 依赖由 `requirements.txt` 和 `frontend/package.json` 声明；当前环境缺少依赖时不阻塞核心标准库测试。
