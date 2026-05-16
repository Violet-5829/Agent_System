# Agent Playground

基于 **FastAPI + Vue 3 + LangGraph** 的多智能体协作平台。支持 DeepSeek V4 等兼容 OpenAI API 的 LLM，通过 5 种工作流编排多个专家 Agent 协同完成数据分析任务。

## 功能

- **5 种 LangGraph 工作流**：单智能体 / 路由专家 / 规划执行 / 监督者调度 / 专家交接
- **4 个专家 Agent**：数据工程师、数据分析师、可视化专家、报表专家
- **SQL + Excel 双数据源**：只读 SQL 查询、Excel/CSV 加载物化
- **SSE 流式 Trace**：实时追踪工具调用和节点执行进度
- **Graph 拓扑可视化**：节点高亮跟随执行进度

## 快速开始

### 环境

- Python 3.11+
- Node.js 18+

### 后端

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # 编辑 .env 填入 API Key
uvicorn app.main:app --host 127.0.0.1 --port 8011
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`，在设置页配置 LLM 和数据源后即可使用。

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py / routes.py / schemas.py / store.py
│   │   ├── runtime.py              # LLM 网关 + 工具注册
│   │   ├── settings_bridge.py      # 环境变量配置
│   │   ├── datalayer/              # 数据访问层 (SQL/Excel/Chart/Report)
│   │   └── workflows/              # 5 种工作流 (LangGraph)
│   ├── skills/                     # 官方 Skill 定义
│   └── data/                       # SQLite + artifacts
├── frontend/
│   └── src/
│       ├── pages/                  # Overview / Agents / Workflows / Playground / Settings
│       ├── components/             # AgentManager / ChatRunner / GraphViewer / TraceViewer
│       └── api.js                  # API 客户端 + SSE 流
└── .env.example
```

## 工作流

| 类型 | 说明 | Agent 数 |
|------|------|---------|
| `single_agent_chat` | 单分析师问答 | 1 |
| `router_specialists` | 意图路由到专家 | 2+ |
| `planner_executor` | 规划→校验→分发→执行→合成 | 2+ |
| `supervisor_dynamic` | 监督者动态委派审查 | 2+ |
| `peer_handoff` | 专家流水线交接 | 2+ |

## 专家 Agent

| Agent | 职责 | 工具 |
|-------|------|------|
| 数据工程师 | SQL 查询、Excel 加载、预处理 | `analytics_run_sql` `analytics_load_excel` |
| 数据分析师 | 统计描述、趋势发现、相关性 | `analytics_run_sql` `analytics_load_excel` |
| 可视化专家 | matplotlib 图表生成 | `analytics_save_chart` |
| 报表专家 | Markdown 报告撰写 | `analytics_write_report_md` |

## API

### 核心
`GET /api/health` · `GET/PUT /api/settings` · `GET /api/workflow-templates`

### Skills / Agents / Workflows
`GET/POST /api/skills` · `POST /api/skills/{id}/install` · `POST /api/skills/sync`
`GET/POST/PUT/DELETE /api/agents`
`GET/POST/PUT/DELETE /api/workflows` · `GET /api/workflows/{id}/graph`

### 运行
`POST /api/runs` · `POST /api/runs/stream`

### 会话
`GET/POST/DELETE /api/conversations` · `GET /api/conversations/{id}`

### 数据源
`GET/POST/DELETE /api/sql-data-sources` · `POST /api/sql-data-sources/{id}/probe`
`GET/POST/DELETE /api/excel-datasets`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | - | API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API 地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 模型名 |
| `EXCEL_DATA_ROOT` | `./data/excel_inbox` | Excel 文件目录 |
| `SQL_MAX_ROWS` | `5000` | 查询最大行数 |
| `SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS` | `30` | SQL 超时 |

## 技术栈

FastAPI · LangGraph · Pydantic v2 · OpenAI SDK · SQLAlchemy · pandas · matplotlib · Vue 3 · Vite

## License

MIT
