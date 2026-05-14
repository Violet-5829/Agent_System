# 数据分析多智能体 Playground

基于 FastAPI + Vue 3 + LangGraph 构建的**数据分析多智能体协作平台**。用户管理 Skills、Agents、Workflows 和数据源，通过 LLM 驱动多个专家 Agent 协同完成数据加载 → 统计分析 → 可视化 → 报表生成的端到端分析任务。

## 功能特性

- **5 种 LangGraph 工作流**：单智能体对话 / 路由专家 / 规划执行 / 监督者动态调度 / 专家交接
- **4 个专家 Agent**：数据工程师、数据分析师、可视化专家、报表专家
- **双重数据源**：SQL 数据库（SQLite/PostgreSQL）只读查询 + Excel/CSV 文件加载物化
- **4 个官方 Skill**：SQL 查询 / Excel 加载 / 图表生成 / 报表写入
- **SSE 流式 Trace**：实时追踪每个 Agent 的工具调用和推理过程
- **多轮会话**：历史消息上下文，会话持久化
- **安全沙箱**：SQL 仅 SELECT、多语句拦截、路径白名单、超时/行数限制

## 架构概览

```
用户输入 → Workflow 主图 (编排)
              ├── Agent 子图 1 (数据工程师) ── invoke
              ├── Agent 子图 2 (数据分析师) ── invoke
              ├── Agent 子图 3 (可视化专家) ── invoke
              └── Agent 子图 4 (报表专家)   ── invoke
                    │
                    ├── Skill 工具 → datalayer (sql_runner / excel_loader)
                    └── 共享 AnalyticsState (materialized_uri, schema_summary, ...)
```

每个 Agent 对应独立的 LangGraph `StateGraph` 子图，主图只做编排与状态合并。所有 Agent 通过统一的 `DataContext` 读写数据，Excel 路径先物化为 Parquet，与 SQL 路径在下游统一。

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── routes.py            # API 路由 (25+ 端点)
│   │   ├── schemas.py           # Pydantic 模型
│   │   ├── store.py             # SQLite 存储 + seed 数据
│   │   ├── runtime.py           # LLM 网关 + 工具注册执行
│   │   ├── settings_bridge.py   # 环境变量配置
│   │   ├── datalayer/           # 数据访问层
│   │   │   ├── sql_runner.py    # 只读 SQL 执行器
│   │   │   ├── excel_loader.py  # Excel/CSV → Parquet
│   │   │   ├── context_builder.py
│   │   │   ├── chart_writer.py  # matplotlib 图表生成
│   │   │   └── report_writer.py # Markdown 报表写入
│   │   └── workflows/           # 5 种工作流
│   │       ├── single_agent_chat/
│   │       ├── router_specialists/
│   │       ├── planner_executor/
│   │       ├── supervisor_dynamic/
│   │       └── peer_handoff/
│   ├── skills/                  # 官方 Skill 定义
│   │   ├── analytics-sql-select/
│   │   ├── analytics-excel-load/
│   │   ├── analytics-save-chart/
│   │   └── analytics-write-report/
│   └── data/
│       ├── excel_inbox/         # Excel 源文件目录
│       └── artifacts/           # 运行时产物 (图表/报表/parquet)
├── frontend/
│   └── src/
│       ├── pages/               # 6 个页面
│       │   ├── PlaygroundPage   # 主运行界面
│       │   ├── AgentsPage       # 智能体管理
│       │   ├── WorkflowsPage    # 工作流管理 + 拓扑图
│       │   ├── SkillsPage       # 技能列表
│       │   ├── DataSourcesPage  # 数据源管理
│       │   └── SettingsPage     # 模型配置
│       ├── api.js               # API 客户端 + SSE 流
│       └── App.vue
└── .env.example
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- （可选）SQLite / PostgreSQL 数据库

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 配置 API Key
cp ../.env.example ../.env
# 编辑 .env 填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL

# 启动
uvicorn app.main:app --host 127.0.0.1 --port 8011
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

### 3. 使用 Playground

1. **设置**页面：配置 LLM API Key
2. **数据源**页面：添加 SQL 连接 或 注册 Excel/CSV 文件（先放入 `data/excel_inbox/`）
3. **Playground**页面：选择工作流 → 绑定数据源 → 输入分析任务 → 点击运行

## API 端点

### 核心

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET/PUT | `/api/settings` | 应用设置 |
| GET | `/api/workflow-templates` | 工作流模板 |

### Skills / Agents / Workflows

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/skills` | 技能列表/创建 |
| POST | `/api/skills/{id}/install` | 安装技能 |
| GET/POST/PUT/DELETE | `/api/agents` | Agent CRUD |
| GET/POST/PUT/DELETE | `/api/workflows` | Workflow CRUD |
| GET | `/api/workflows/{id}/graph` | 拓扑图 |

### 运行与会话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/runs` | 执行工作流 |
| POST | `/api/runs/stream` | SSE 流式执行 |
| GET/POST/DELETE | `/api/conversations` | 会话管理 |
| GET | `/api/conversations/{id}` | 会话详情 |

### 数据源

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/DELETE | `/api/sql-data-sources` | SQL 数据源管理 |
| POST | `/api/sql-data-sources/{id}/probe` | 测试连接 |
| GET/POST/DELETE | `/api/excel-datasets` | Excel 数据集管理 |

### 静态文件

图表和报表通过 `/artifacts/` 公开访问。

## 5 种工作流

| 类型 | 说明 | 最少 Agent |
|------|------|-----------|
| `single_agent_chat` | 单分析师在绑定数据源上问答、查询、图表 | 1 |
| `router_specialists` | 根据意图路由到数据工程/分析/可视化/报表专家 | 2 |
| `planner_executor` | 规划→校验→分发→执行→合成，含中间产物一致性检查 | 2 |
| `supervisor_dynamic` | 监督者动态拆分子任务分发，适合复杂探索 | 2 |
| `peer_handoff` | 专家流水线交接：工程→分析→可视化→报告 | 2 |

## 4 个专家 Agent

| Agent | 职责 | 绑定 Skill |
|-------|------|-----------|
| 数据工程师 | SQL 查询、Excel 加载、数据预处理 | `analytics_run_sql` `analytics_load_excel` |
| 数据分析师 | 统计描述、趋势发现、相关性分析 | `analytics_run_sql` `analytics_load_excel` |
| 可视化专家 | matplotlib 图表生成 | `analytics_save_chart` |
| 报表专家 | Markdown 综合分析报告 | `analytics_write_report_md` |

## 安全设计

- SQL 执行器**仅允许 SELECT/WITH/EXPLAIN**，代码层拦截多语句和写操作
- Excel 加载器**路径白名单**（`EXCEL_DATA_ROOT`），拒绝路径穿越
- 查询结果**自动截断**（默认 5000 行），**超时中断**（默认 30 秒）
- 数据访问**仅经 Skill 工具**，不通过 `BuiltinCapability` 暴露
- API 响应**隐藏数据库连接串**，trace 不含密码/密钥/原始数据

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | - | API Key（兼容 OpenAI/DeepSeek 等） |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API 地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 模型名称 |
| `EXCEL_DATA_ROOT` | `./data/excel_inbox` | Excel 文件白名单目录 |
| `SQL_MAX_ROWS` | `5000` | SQL 查询最大行数 |
| `SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS` | `30` | SQL 超时秒数 |
| `ARTIFACT_PUBLIC_BASE_URL` | `http://127.0.0.1:8011/artifacts` | 产物访问 URL |

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + uvicorn |
| 数据校验 | Pydantic v2 |
| LLM 编排 | LangGraph >= 0.2.0 |
| LLM 调用 | OpenAI SDK（兼容 DeepSeek） |
| 数据分析 | pandas, openpyxl, SQLAlchemy |
| 可视化 | matplotlib |
| 元数据 DB | SQLite |
| 前端 | Vue 3 + Vite |
| 流式通信 | SSE (Server-Sent Events) |

## License

MIT
