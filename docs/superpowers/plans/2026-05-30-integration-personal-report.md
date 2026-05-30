# Integration Personal Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the individual integration-stage report for `24281239_王云瑜` as a submit-ready PDF.

**Architecture:** Keep the report as a Markdown source file under the personal deliverables directory, then export it to DOCX and PDF with Pandoc. The source content is based on existing project documents, code, and tests; no application behavior is changed.

**Tech Stack:** Markdown, Pandoc 3.9, LuaLaTeX, Noto Serif CJK SC.

---

## File Structure

- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.md`
  - Source text for the report.
- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.docx`
  - Editable Word version generated from Markdown.
- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf`
  - Submit-ready PDF generated from Markdown.

## Task 1: Create Report Source

**Files:**
- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.md`

- [ ] **Step 1: Create the output directory**

Run:

```bash
mkdir -p 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料'
```

Expected: the directory exists.

- [ ] **Step 2: Write the Markdown source**

Use `apply_patch` to create the Markdown report with these exact sections:

```markdown
# 软件综合实训集成阶段实训报告

**课程名称：** 软件综合实训  
**项目名称：** 北京交通大学就餐仿真系统  
**小组编号：** 20组  
**学号：** 24281239  
**姓名：** 王云瑜  
**阶段：** 集成阶段  
**日期：** 2026年5月30日

## 一、集成阶段任务概述

集成阶段的主要目标是将开发阶段已经完成的后端仿真、前端交互、数据存储、优化推荐、规则化解释和测试用例串联为能够稳定运行的完整系统。北京交通大学就餐仿真系统采用前后端分离结构，前端基于 Vue 3 和 Vite 实现参数配置、布局编辑、实时地图、趋势图和推荐结果展示，后端基于 FastAPI、Pydantic 和 SQLite 实现接口服务、离散时间仿真、指标汇总、推荐计算、解释生成和结果导出。

本阶段个人工作的重点不是重新设计系统功能，而是围绕“配置输入—接口请求—仿真推进—状态返回—指标分析—推荐解释—结果保存”这一完整链路进行联调和验证，确认各模块之间的数据结构一致、调用顺序正确、异常情况能够被及时发现并处理。通过集成阶段工作，系统能够支持完整仿真运行、实时单步运行、校园人流到达、餐厅布局联动、优化推荐、规则化解释和 CSV 导出等核心流程。

## 二、个人承担的主要工作

根据小组开发任务划分，我在本项目中主要负责系统核心功能开发、整体联调与测试验证。集成阶段继续围绕这些职责开展工作，主要包括以下几个方面。

第一，负责后端接口与仿真核心的联调。后端 `backend/app/main.py` 提供健康检查、参数校验、完整仿真、单步仿真、推荐、解释、历史记录查询和导出接口；`backend/app/simulation.py` 保存核心离散时间仿真逻辑。集成阶段重点检查前端请求体经过 Pydantic 模型校验后能否正确转换为仿真内部 dataclass，确认窗口数、座位数、到达率、服务时间、就餐时间、校园到达配置和布局信息能够完整进入仿真器。

第二，负责实时仿真链路的联调。实时运行依赖 `/api/sim/step` 接口和后端 `ACTIVE_RUNS` 内存运行表。首次请求创建 `DiningSimulationRunner`，后续请求通过 `run_id` 找回同一仿真状态并继续推进。集成阶段重点验证前端开始、单步、暂停和快速完成等操作不会造成运行状态丢失，后端在仿真结束后能够保存结果并清理已完成的 runner。

第三，负责前端展示与后端状态快照的对接。前端需要根据每分钟 `StepRecord` 和 `snapshot` 更新队列、窗口、餐桌、行走动画、指标卡片和趋势图。集成阶段核对了 `queue_lengths`、`waiting_for_seat_count`、`empty_seats`、`table_occupancy`、`timeline` 等字段在前后端之间的含义，确保页面展示与后端状态保持一致。

第四，负责优化推荐和规则化解释的集成验证。推荐模块 `backend/app/optimization.py` 根据基准配置枚举窗口、座位、错峰和多峰下课候选方案，并用评分方式排序；解释模块 `backend/app/explanation.py` 根据瓶颈类型、基准指标和推荐指标生成可读说明。集成阶段验证推荐结果能够从后端返回到结果分析页，并能继续作为解释接口的输入。

第五，负责存储、导出和测试验证。`backend/app/storage.py` 使用 SQLite 保存运行配置、分钟记录、最终指标、推荐结果和解释结果，并支持 CSV 导出。集成阶段检查完整仿真和实时仿真结束后都能落库，历史记录和指标查询能够读回结果，导出接口能够生成过程记录文件。同时运行后端与前端测试，检查主要链路没有被集成修改破坏。

## 三、集成联调内容

本阶段联调围绕系统主流程展开。首先进行接口连通性联调，前端通过 Vite 开发服务访问页面，请求 `/api/health` 判断后端是否在线。后端允许来自 `127.0.0.1:5173` 和 `localhost:5173` 的跨域访问，保证本地开发和展示环境下前端可以正常调用 FastAPI 接口。

其次进行参数配置和校验联调。前端表单中的窗口数、座位数、平均到达率、平均服务时间、平均就餐时间、高峰时间段、随机种子、布局对象和校园到达配置会组装为 JSON 请求体。后端 `SimulationConfig` 负责基础字段范围校验，`validate_config()` 负责业务层面的错误和警告提示，例如窗口数、座位数、布局资源数量和高峰时间设置。通过该联调可以在仿真运行前发现明显不合理的配置。

然后进行完整仿真和实时仿真联调。完整仿真接口 `/api/sim/run` 一次性运行到结束，适合快速得到结果；实时仿真接口 `/api/sim/step` 每次推进一分钟，适合展示排队、取餐、等座、行走到餐桌和离开的动态过程。两类接口底层都使用 `DiningSimulationRunner`，因此集成阶段重点确认两种运行方式的指标来源一致，只是前端展示方式不同。

接着进行布局和地图展示联调。前端布局编辑器传入入口、取餐窗口和餐桌坐标，后端根据布局计算学生选择窗口、排队、选择餐桌和入座路径。集成阶段验证了自定义布局能够影响最终餐桌状态，餐桌容量、类型和旋转角度能够通过接口模型进入仿真，并在最终状态和指标中体现。

最后进行推荐、解释、存储和导出联调。仿真结束后，前端将基准配置和候选范围发送到推荐接口，后端返回排序后的候选方案和最佳策略；结果分析页再把基准指标、最佳方案指标和推荐策略发送到解释接口，得到规则化说明。完整运行结果、推荐结果和解释结果都会保存到 SQLite，过程记录可以导出为 CSV，便于后续复核。

## 四、集成阶段遇到的问题与解决

第一个问题是前后端字段含义需要保持一致。仿真核心中包含 `StepRecord`、`MetricsSummary`、布局数据、校园到达数据和实时快照等多类结构，如果前端字段名和后端返回字段不一致，就会出现页面不刷新或图表数据为空的问题。解决方式是在后端集中维护 Pydantic 模型和 dataclass 转换逻辑，在前端通过统一的 `api.js` 封装接口调用，并在测试中覆盖布局 payload、指标字段和推荐字段。

第二个问题是实时单步运行需要保持后端状态。实时仿真不是每次重新计算，而是依赖同一个 runner 持续推进。如果 `run_id` 丢失或已完成运行仍被复用，就会导致状态跳变或接口报错。解决方式是在后端使用 `ACTIVE_RUNS` 按 `run_id` 保存运行中的仿真器，首次请求或重置时创建 runner，仿真完成后保存结果并移除对应运行状态。

第三个问题是校园到达和推荐候选数量增加后，完整枚举运行可能影响响应速度。特别是多个教学楼、多个座位选项、多个窗口选项和多峰下课组合同时存在时，如果每个候选都完整跑仿真，会让推荐接口变慢。解决方式是在推荐模块中对候选方案使用快速估算逻辑，只对基准配置进行完整指标计算，并通过测试确保候选枚举不会误调用完整仿真。

第四个问题是布局资源和配置资源需要同步。当前端调整窗口或餐桌数量后，如果后端仍按旧布局运行，就会造成窗口数、座位数和实际布局容量不一致。解决方式是在校验阶段给出资源数量提示，在推荐候选生成时同步扩展窗口和餐桌布局，并保留已有自定义坐标、餐桌类型和旋转信息。

第五个问题是中文报告和课程材料需要符合提交命名规范。集成阶段个人交付物只要求实训报告，因此不应混入团队联调测试报告或系统源代码压缩包。解决方式是根据课程交付物要求和文档命名规范，将最终文件命名为 `软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf`，并单独放入集成阶段个人材料目录。

## 五、测试验证结果

集成阶段主要通过自动化测试和人工运行检查共同验证。后端测试覆盖仿真可复现性、到达期结束后的系统清空、窗口服务瓶颈、座位容量瓶颈、推荐排序、布局候选扩展、自定义布局保留、校园多峰下课、结伴就餐、实时地图快照、餐桌选择和后端入座时间线等行为。

接口集成测试覆盖参数校验、完整仿真、记录查询、指标查询、推荐生成和解释生成的完整链路，能够验证 FastAPI handler、仿真器、存储层、推荐模块和解释模块之间可以协同工作。存储测试覆盖 SQLite 保存、读取和 CSV 导出，确保仿真结束后的过程记录和指标可以被追溯。

前端测试覆盖运行控制、候选配置、实时地图模型、布局 payload、推荐面板、图表工具和路径动画等模块，验证前端关键数据处理逻辑能够独立运行。通过这些测试，可以确认集成阶段主流程没有只停留在页面展示层，而是从接口、业务逻辑、状态转换、持久化和可视化数据处理多个层面进行了验证。

## 六、阶段总结

通过集成阶段工作，我进一步理解了前后端分离项目中数据契约的重要性。单个模块在开发阶段可以独立通过测试，但只有放到完整链路中，才能发现字段含义、运行状态、异常处理和展示逻辑之间的细节问题。本项目中，仿真核心、接口模型、前端状态、推荐解释和 SQLite 存储之间都依赖稳定的数据结构，因此集成阶段的重点是减少隐式假设，让每个模块的输入输出清晰可查。

本阶段我完成了个人负责范围内的核心联调和测试验证工作，确认系统能够从参数配置进入仿真运行，持续生成过程记录，最终形成指标、推荐、解释和导出结果。遇到的问题主要集中在接口字段一致性、实时运行状态保持、推荐性能、布局资源同步和交付物命名规范等方面，均通过统一模型、运行状态管理、快速估算、校验提示和文档规范检查得到解决。

总体来看，集成阶段使系统从“各模块可以单独运行”推进到“完整业务流程可以连续运行”。这也为后续部署阶段的环境搭建、使用手册编写和课程展示打下了基础。
```

- [ ] **Step 3: Inspect the source**

Run:

```bash
sed -n '1,260p' 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.md'
```

Expected: all sections are present and there are no `TODO` or `TBD` markers.

## Task 2: Export Report Files

**Files:**
- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.docx`
- Create: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf`

- [ ] **Step 1: Export the editable DOCX**

Run:

```bash
pandoc 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.md' \
  -o 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.docx'
```

Expected: command exits with status 0 and the `.docx` file exists.

- [ ] **Step 2: Export the submit-ready PDF**

Run:

```bash
pandoc 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.md' \
  --pdf-engine=lualatex \
  -V CJKmainfont='Noto Serif CJK SC' \
  -V mainfont='Noto Serif CJK SC' \
  -V geometry:margin=2.5cm \
  -o 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf'
```

Expected: command exits with status 0 and the `.pdf` file exists.

## Task 3: Validate Deliverable

**Files:**
- Read: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf`
- Read: `deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.docx`

- [ ] **Step 1: Check generated files**

Run:

```bash
ls -lh 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料'
```

Expected: `.md`, `.docx`, and `.pdf` files are present.

- [ ] **Step 2: Check DOCX text extraction**

Run:

```bash
officecli view 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.docx' text --max-lines 220
```

Expected: extracted text includes `集成阶段任务概述`、`个人承担的主要工作`、`测试验证结果` and no `TODO` or `TBD`.

- [ ] **Step 3: Check PDF metadata and text**

Run:

```bash
pdfinfo 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf' 2>/dev/null || true
pdftotext 'deliverables/软件综合实训_24281239_王云瑜_集成阶段个人材料/软件综合实训_24281239_王云瑜_集成阶段实训报告.pdf' - 2>/dev/null | sed -n '1,80p' || true
```

Expected: if `pdfinfo` or `pdftotext` is installed, the PDF can be inspected and contains the report title. If those tools are unavailable, file existence and successful Pandoc export are sufficient.

- [ ] **Step 4: Review git status**

Run:

```bash
git status --short
```

Expected: generated deliverable files are visible under `deliverables/`, and unrelated existing untracked course materials remain untouched.
