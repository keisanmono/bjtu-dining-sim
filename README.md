# 北京交通大学就餐仿真系统

第 20 组课程项目。系统面向学校食堂高峰就餐过程，支持参数配置、仿真运行、过程记录、指标分析、结果展示、优化推荐和规则化解释。

## 技术栈

- 前端：Vue 3 + Vite + Element Plus + ECharts
- 后端：Python 3.11 + FastAPI + Uvicorn + Pydantic
- 存储：SQLite + CSV 导出
- 测试：`unittest` 核心测试，兼容后续 `pytest`

## 目录

```text
backend/   FastAPI 接口、仿真、分析、推荐、解释、持久化
frontend/  Vue 3 页面
tests/     核心仿真与存储测试
data/      SQLite 与导出文件
doc/       设计规格说明书与环境搭建说明
scripts/   启动脚本
```

## 后端运行

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/api/health
```

## 前端运行

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。

若使用其他后端端口，启动前端前设置 `VITE_API_TARGET`，例如 `VITE_API_TARGET=http://127.0.0.1:8000 npm run dev`。

## 验证

```bash
python -m unittest tests.test_storage tests.test_simulation
cd frontend && npm run build
```

## GitHub 仓库

本地仓库已初始化为 `main`。如果 GitHub API 可访问并且 `gh` 已登录，可执行：

```bash
gh repo create bjtu-dining-sim --private --source=. --remote=origin
git add .
git commit -m "Initial BJTU dining simulation system"
git push -u origin main
```
