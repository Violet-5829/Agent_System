# 数据分析多智能体 Playground — 开发规格书（供 Claude Code 执行）

> **参考仓库**：[Jasper-zh/Multi-Agent-Playground](https://github.com/Jasper-zh/Multi-Agent-Playground)  
> **定位**：在参考项目的 **FastAPI 路由形态、SQLite 元数据、Vue3 前端、五种 `WorkflowType`、SSE `/runs/stream`、Skills/会话模型** 等骨架上，实现面向 **数据处理 → 分析 → 制图 → 报表** 的多智能体协同；**每个专家角色对应独立 LangGraph 子图**，数据来自 **SQL 数据库** 或 **Excel 文件**（统一抽象后再进入下游子图）。

---

## 1. 项目目标

构建**本地优先**的数据分析 Agent Playground：

- 用户管理 **Skills**、**Agents（按数据分析角色划分）**、**Workflows**；可选注册 **数据源**（数据库连接 / Excel 数据集）。
- 一次运行中：主工作流图负责编排；**各专家 Agent 在代码层各自为编译好的 `StateGraph`（子图）**，由主图节点 `invoke` 或作为 subgraph 挂载，统一读写 **共享分析状态**（见第 4.3 节）。
- 运行结束返回：**自然语言结论**、**trace**、**拓扑 graph**、**RunArtifacts**（含图表路径、报表路径、物化数据集引用等扩展字段）。
- 支持 **多轮会话**（`conversation_id` + 最近消息 `history`，与参考实现一致）。
- 可选：**SkillHub**、**Electron + PyInstaller**（与参考仓库一致）。

---

## 2. 技术栈（参考实现 + 数据分析增量）

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+，`FastAPI`，`uvicorn[standard]`，`pydantic` v2，`openai`，`python-dotenv`，**`langgraph`** |
| 分析运行时 | **`pandas`**，**`openpyxl`**（或 `calamine`）读 Excel；**`SQLAlchemy` 2.x** + 各数据库驱动（建议先支持 **SQLite / PostgreSQL** 只读） |
| 制图 | **`matplotlib`** 或 **`plotly`**（输出到 `backend/data/artifacts/{run_id}/`） |
| 报表 | 先生成 **Markdown/HTML**（可选后续接 Pandoc PDF） |
| 元数据 DB | **SQLite** `backend/data/playground.db`（与参考一致） |
| 前端 | **Vue 3** + Vite **5173**，代理 **8011** |
| 桌面 | **Electron** + 后端 **PyInstaller**（可选） |

**`requirements.txt` 在参考底线之上增加**（版本号由实现时锁定）：`pandas`、`openpyxl`、`sqlalchemy`、`matplotlib` 或 `plotly`。

---

## 3. 仓库目录结构（在参考结构上扩展）

```
project-root/
├── .env.example
├── .env
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   ├── store.py
│   │   ├── runtime.py              # LLM + 按 Agent 所绑 Skill 注册工具（Skill 内可调用 datalayer）
│   │   ├── settings_bridge.py
│   │   ├── skillhub_client.py      # 可选
│   │   ├── datalayer/              # 【新增】数据源与统一访问
│   │   │   ├── __init__.py
│   │   │   ├── models.py           # DataSource / DatasetHandle 内部结构
│   │   │   ├── sql_runner.py       # 只读、超时、行数上限、单语句
│   │   │   ├── excel_loader.py     # 白名单路径 + sheet -> DataFrame -> 物化 parquet
│   │   │   └── context_builder.py  # 构建注入各子图的 DataContext
│   │   └── workflows/              # 五种 type 与参考仓库同名目录
│   │       ├── langgraph_adapter.py
│   │       ├── single_agent_chat/
│   │       ├── router_specialists/
│   │       ├── planner_executor/
│   │       ├── supervisor_dynamic/
│   │       └── peer_handoff/
│   ├── skills/
│   ├── data/
│   │   ├── playground.db
│   │   └── artifacts/              # 图表、报表、中间 parquet
│   ├── requirements.txt
│   └── requirements-desktop.txt
├── frontend/
└── desktop/
```

---

## 4. 工作流与 LangGraph 约定

### 4.1 五种 `WorkflowType`（**保持与参考仓库相同的字面量**，便于对照 fork）

| `type` | 在数据分析场景下的语义 |
|--------|------------------------|
| `single_agent_chat` | 单分析师子图：在已绑定的 **DataContext** 上做问答、简单查询/脚本、小图表；可选 `finalizer` 生成简短执行摘要。 |
| `router_specialists` | 路由器根据用户意图选择 **数据工程 / 统计分析 / 可视化 / 报表** 某一专家子图执行；可链式多轮路由；可选 finalizer。 |
| `planner_executor` | **规划 → 校验 → 分发 → 执行 → 合成**：适合「端到端分析任务」；校验节点检查 schema/行数/SQL 与上一步产物一致性。 |
| `supervisor_dynamic` | 监督者动态拆分子任务并分发给不同专家子图（适合复杂、多步探索）。 |
| `peer_handoff` | 专家之间 **handoff**（如工程 → 分析 → 制图 → 报告），直至收敛。 |

每种目录仍导出：

- `build_*_graph(workflow, agents) -> WorkflowGraph`（**前端拓扑用**，可与 LangGraph 节点 id 对齐）
- `run_*(store, workflow, user_input, *, data_context, history=..., on_event=...) -> WorkflowRunResponse`

其中 **`data_context`** 由 `datalayer.context_builder` 根据本次 run 绑定的数据源构建（见第 6、7 节）；**禁止**在 `routes.py` 内写分析业务逻辑。

### 4.2 每个 Agent = 一个 LangGraph 子图

- **实现要求**：在 `workflow.py` 内，为 `workflow.specialist_agent_ids` 映射到的每个 `AgentDefinition` 编译 **独立 `StateGraph`**（子图），节点包含：`prepare_tools` → `model` → `tool_node`（可选）→ `emit_artifact` 等；**主工作流图**通过节点调用 `subgraph.invoke(sub_state)` 或 LangGraph 官方 **subgraph** 模式组合。
- **提示词**：各子图使用对应 `AgentDefinition.system_prompt` + 角色专用 `prompts.py`（数据工程/分析/可视化/报表模板）。
- **Trace**：子图内关键节点通过 `on_event` 上报 `TraceEvent`（`node_entered` / `message_generated` / `state_updated` 等），`payload` 可含 `agent_id`、`subgraph_name`，**不得**含数据库密码、完整连接串、未脱敏的大段原始数据。

### 4.3 共享分析状态（建议字段，供各子图读写）

主图与各子图通过 **同一 TypedDict / dataclass** 传递（名称示例 `AnalyticsState`）：

| 字段 | 说明 |
|------|------|
| `user_input` | 当前用户自然语言任务 |
| `data_source_kind` | `"sql"` \| `"excel"` |
| `materialized_uri` | 标准化后的数据集路径（如 parquet）或逻辑表名 + connection_id |
| `schema_summary` | 列名、类型、行数估算（给 LLM 的短文本，非全表） |
| `sample_rows` | 极少行 JSON（可选） |
| `sql_log` | 已执行 SQL 摘要列表（脱敏、截断） |
| `artifact_dir` | 本次 run 输出目录 |
| `messages` | 多轮消息（与 LangGraph message 列表对齐时可合并） |
| `errors` | 结构化错误，供校验节点消费 |

Excel：**excel_loader** 将文件读入 DataFrame → 写入 `data/artifacts/{run_id}/input.parquet`（或按会话分目录），后续子图**只操作该物化结果**，与 SQL 路径统一。  
SQL：**sql_runner** 仅允许 **SELECT**（或白名单视图），限制返回行数，超时中断。

---

## 5. 核心数据模型（Pydantic / API 契约）

### 5.1 与参考一致的部分（字段名保持）

- `WorkflowType`：**不变** — `router_specialists` | `planner_executor` | `supervisor_dynamic` | `single_agent_chat` | `peer_handoff`
- `TraceEventType`：与参考一致
- `Skill*`、`Agent*`、`Workflow*`、`Conversation*`、`Message*`、`ModelProfile`、`AppSettings`、`WorkflowRunRequest` 基字段：与参考一致

### 5.2 `BuiltinCapability`（**与参考仓库完全一致，不增删字面量**）

取值**仅**为：`filesystem` | `fs_list` | `fs_read` | `fs_write`（`schemas.py` 中 `Literal` 与上游保持一致）。

**SQL / Excel 数据访问不通过 BuiltinCapability**，一律走 **Skill**：

- Skill 在元数据中携带 **工具定义**（名称、描述、参数 schema，与参考仓库 `SkillDefinition.tool` 形态一致）。
- **runtime** 在组装某 Agent 的可调用工具集时：合并 **BuiltinCapability 对应内置工具** + 该 Agent `skill_ids` 所关联的 **Skill 工具**；Skill 工具的实现函数内部调用 `datalayer/sql_runner.py`、`datalayer/excel_loader.py` 等，并**注入当前 run 的 `DataContext`**（如 `sql_data_source_id` / `excel_dataset_id` 解析后的连接或文件句柄），避免模型自行拼接连接串。
- 建议随 `seed_defaults` 在 `backend/skills/` 下附带 **官方示例 Skill**（如 `skill-sql-select`、`skill-excel-load`），并在默认数据分析 Agent 上绑定，降低用户从零编写 Skill 的成本；用户仍可通过 SkillHub 或手写扩展。

**安全**：即使工具由 Skill 暴露，`sql_runner` / `excel_loader` 仍必须在代码层强制执行只读、超时、行数上限、`EXCEL_DATA_ROOT` 白名单；**不信任** Skill 文本中的「绕过说明」。

### 5.3 `RunArtifacts`（保留参考字段，**新增可选字段**）

参考保留：`route_agent_id?`、`route_agent_name?`、`route_reason?`、`specialist_answer?`、`final_answer?`

**新增（均为可选，便于前端展示下载链接）**：

- `dataset_summary?`：str，人类可读的数据概况  
- `materialized_paths?`：`list[str]`，中间 parquet / 导出 csv  
- `chart_paths?`：`list[str]`，png/html  
- `report_path?`：str，md/html  
- `queries_used?`：`list[str]`，脱敏后的 SQL 片段（禁止含密码）

### 5.4 数据源实体（**新增**，存 SQLite，与 agents/workflows 同级管理）

**`SqlDataSourceCreate`**

- `name`：展示名  
- `dialect`：`sqlite` | `postgresql`（可扩展）  
- `connection_string`：服务端存储，**API 响应中默认不返回明文**，可返回 `has_secret: bool`  
- `read_only`：默认 `true`

**`SqlDataSource`**：+ `id`，`created_at`

**`ExcelDatasetCreate`**

- `name`  
- `file_path`：必须在服务端配置的 **`EXCEL_DATA_ROOT`** 白名单下，或使用上传接口落到该目录后的相对路径

**`ExcelDataset`**：+ `id`，`file_path`，`created_at`

（实现时可合并为统一 `DatasetRef` 表，但 API 分 SQL / Excel 更清晰。）

### 5.5 `WorkflowRunRequest` 扩展

在参考字段基础上**增加可选字段**（不传则要求用户在 `user_input` 中明确已有默认数据集，或由会话上次 run 缓存恢复——二选一，实现时文档写清）：

- `sql_data_source_id?: str`  
- `excel_dataset_id?: str`  

**校验**：二者至多选一；选中则构建 `DataContext` 并注入 Skill 工具处理器。若当前 Agent **未绑定**可提供 SQL/Excel 能力的 Skill，则模型侧不应注册对应工具；若用户强制在提示词里要求执行 SQL，**runtime** 应在工具层无可用处理器时直接失败并返回明确错误（勿由模型伪造查询结果）。

---

## 6. HTTP API 清单

### 6.1 与参考一致（前缀 `/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | |
| GET/PUT | `/settings` | |
| GET | `/workflow-templates` | 模板文案改为**数据分析角色说明**与 `required_agent_count` |
| GET/POST | `/skills` | |
| POST | `/skills/{id}/install` | 可选 |
| POST | `/skills/sync` | 可选 |
| GET/POST/PUT/DELETE | `/agents` | |
| GET/POST/PUT/DELETE | `/workflows` | |
| GET | `/workflows/{id}/graph` | |
| POST | `/runs` | body 含扩展的 `WorkflowRunRequest` |
| POST | `/runs/stream` | SSE 不变 |
| GET/POST/DELETE | `/conversations` | |
| GET | `/conversations/{id}` | |

**CORS / SSE**：与参考一致。

### 6.2 新增：数据源

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sql-data-sources` | 列表（隐藏连接串） |
| POST | `/api/sql-data-sources` | 创建 |
| DELETE | `/api/sql-data-sources/{id}` | |
| POST | `/api/sql-data-sources/{id}/probe` | 可选：测试连接，返回可见 schema 名列表（不含数据） |
| GET | `/api/excel-datasets` | |
| POST | `/api/excel-datasets` | 注册 **`EXCEL_DATA_ROOT` 下已有文件** 的元数据（首版不做 multipart 上传，见 §14.4） |
| DELETE | `/api/excel-datasets/{id}` | |

**静态文件**：图表/报表可通过 `FastAPI.StaticFiles` 挂载 `data/artifacts` 或以带签名的短期 URL 返回（实现任选，规格要求**前端能访问 URL 或 base64 小图二选一**）。

---

## 7. 运行与持久化逻辑要点

1. **Startup**：与参考一致：`seed_defaults` + settings + `llm_gateway.refresh_client()`。  
2. **`POST /runs` / `/runs/stream`**：  
   - 解析 `sql_data_source_id` 或 `excel_dataset_id` → `datalayer.context_builder.build(...)` → 注入 `_dispatch_run(..., data_context=...)`。  
   - `history`：仍取最近 **2** 条消息。  
3. **产物路径**：每次 run 生成 `artifact_dir = data/artifacts/{run_id}/`，写入 `RunArtifacts`。  
4. **会话标题**：与参考一致。  
5. **删除保护**：若某 `SqlDataSource` / `ExcelDataset` 被会话或 workflow 默认引用，需 409 或级联策略（实现时二选一并在 README 说明）。

---

## 8. 环境变量（`.env.example`）

在参考项目基础上增加：

```
# 分析数据
EXCEL_DATA_ROOT=./backend/data/excel_inbox
SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS=30
SQL_MAX_ROWS=5000

# 可选：仅允许访问的额外目录（逗号分隔）；与 BuiltinCapability 中 fs_* 及 Skill 落盘路径策略配合
ARTIFACT_PUBLIC_BASE_URL=http://127.0.0.1:8011/artifacts
```

保留参考中的 `OPENAI_*`、`SKILLHUB_*`、`TAVILY_*` 等。

---

## 9. 前端功能清单（Vue 3）

1. **设置**：同参考（模型 Profile、环境变量）。  
2. **数据源**：SQL 连接列表 + 探测；Excel 数据集列表 + 路径/上传说明。  
3. **技能 / 智能体**：强调**角色标签**（数据工程、分析、可视化、报表）；**BuiltinCapability 仅四项**；数据分析用 SQL/Excel 通过 **安装并绑定 Skill** 完成，前端可提示「推荐官方 SQL/Excel Skill」。  
4. **工作流**：模板说明改为数据分析场景；拓扑 `/graph` 展示子图节点（可分组显示「子图边界」）。  
5. **Playground**：选择 workflow + **绑定数据源（SQL 或 Excel）** → 输入任务 → trace + **图表预览 / 报表下载**。  
6. **代理**：`/api` → `8011`。

---

## 10. 分阶段实施计划

### Phase A — 骨架与元数据

- [ ] 目录与参考对齐；`store.py` 增加 `sql_data_sources`、`excel_datasets` 表及 seed（示例连接可指向本地 sqlite 文件数据集）  
- [ ] `schemas.py`：**不修改** `BuiltinCapability`；扩展 `RunArtifacts`、`WorkflowRunRequest`、数据源模型  
- [ ] `routes.py`：新数据源路由 + 原 stub  
- [ ] `datalayer/sql_runner.py`、`excel_loader.py` 单元测试（超时、行数、路径穿越）

### Phase B — LLM + 单智能体数据分析子图

- [ ] `runtime.py`：按 Agent 合并 **BuiltinCapability 工具** + **Skill 工具**；Skill 处理器内调用 `datalayer`（sql_runner / excel_loader）并注入 `DataContext`；制图可再经 Skill 或单独 `fs_write` 白名单目录工具输出  
- [ ] `backend/skills/`：落地官方示例 Skill（SQL 只读查询、Excel 物化），`seed_defaults` 中创建并绑定到示例 Agent  
- [ ] `single_agent_chat`：单子图，端到端 `POST /runs` 返回含 `dataset_summary` 的 artifacts

### Phase C — 多智能体四种工作流

- [ ] 为四类多智能体各实现 **主图 + 多子图 invoke**，默认 seed 四个角色 Agent  
- [ ] `router_specialists`：路由提示词改为「分析任务意图」  
- [ ] `planner_executor`：含**校验节点**（schema/行数/文件存在）  
- [ ] `supervisor_dynamic`、`peer_handoff`  
- [ ] 每种补全 `build_*_graph` 与 `_dispatch_run`

### Phase D — 会话、SSE、SkillHub

- [ ] 与参考一致；流式 trace 中附带 `subgraph_name` 便于 UI 分栏

### Phase E — 前端

- [ ] 数据源管理页 + Playground 数据源选择器 + artifacts 预览区

### Phase F — 桌面端（可选）

- [ ] 与参考一致

---

## 11. 质量与验收标准

- [ ] 五种 `WorkflowType` 在**绑定 SQL 或 Excel 之一**时均可完整跑通，`RunArtifacts` 至少一种场景含 `chart_paths` 或 `report_path`；且示例 Agent 已绑定可提供查询/加载能力的 **Skill**（非 BuiltinCapability 扩展）  
- [ ] SQL：**禁止**多语句、**禁止**写操作（除非未来单独开关且默认关）  
- [ ] Excel：路径不在 `EXCEL_DATA_ROOT` 下 → 400  
- [ ] trace 与 `/graph` 无 500；无密钥/连接失败时错误信息友好且**无敏感信息泄露**  
- [ ] 多轮 `history` 仍有效（与参考行为一致）

---

## 12. 给 Claude Code 的执行提示

1. **先 clone** [Multi-Agent-Playground](https://github.com/Jasper-zh/Multi-Agent-Playground) 对照 `routes.py`、`store.py`、`runtime.py` 分层，再按本文档改领域逻辑。  
2. **WorkflowType 字面量勿改名**，降低与参考前端路由枚举的合并成本。  
3. **`BuiltinCapability` 勿增删字面量**；数据库与表格访问**仅经 Skill 工具**进入 `datalayer`，与参考 `SkillDefinition.tool` 模型对齐。  
4. **子图边界清晰**：每个 `Agent` 对应独立 `StateGraph` 文件或工厂函数，主图只做编排与状态合并。  
5. **统一 DataContext**：下游子图不区分 Excel/SQL，只认 `materialized_uri` + `schema_summary`。  
6. **Windows**：路径用 `pathlib`；Excel 中文路径注意编码。

---

## 13. 本地启动命令

与参考一致：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8011
```

```bash
cd frontend
npm install
npm run dev
```

---

## 14. 附录：是否可交给 Claude Code — 结论与补齐项

### 14.1 总体结论

**可以交给 Claude Code 开发。** 骨架（参考 fork 路径、五种工作流目录、`/api` 形态、`datalayer` 职责、Skill-only 数据访问、分阶段任务）已足够驱动实现；下列项在原文中略模糊，**按本节默认决议执行即可**，无需再向你反复确认（若与产品冲突再改 README）。

### 14.2 Claude Code 建议阅读顺序

1. Clone 并对照 [Multi-Agent-Playground](https://github.com/Jasper-zh/Multi-Agent-Playground) 的 `schemas.py`、`routes.py`、`store.py`、`runtime.py` 与各 `workflows/*/workflow.py`。  
2. 再通读本规格第 **4、5、6、7、10** 节，按 Phase A→F 改代码。  
3. 实现 **官方示例 Skill** 时以 **14.3** 的工具名为准（可与参考仓库 `SkillDefinition.tool` 的 JSON 结构对齐，字段可增减但语义勿漂移）。

### 14.3 官方示例 Skill — 工具名与参数（最小约定）

以下工具由 **代码注册**（非 LLM 编造）；`SkillDefinition` 中 `tool` 字段与之一致即可被前端/调试器识别。

| 工具名（建议） | 作用 | 参数（示例） | 说明 |
|----------------|------|----------------|------|
| `analytics_run_sql` | 在当前 run 已绑定 `sql_data_source_id` 时执行只读查询 | `query: str` | 仅 `SELECT`；由 `sql_runner` 解析并拒绝多语句；`DataContext` 注入连接，**禁止**在参数中传连接串。 |
| `analytics_load_excel` | 将已注册 `excel_dataset_id` 对应文件物化为 parquet | 可无参或 `sheet_name?: str` | 路径来自服务端存储的 `ExcelDataset`，**禁止**由模型传任意文件路径。 |

制图/写报表：首版可再各提供一个 Skill（如 `analytics_save_chart`、`analytics_write_report_md`），内部仅写 `artifact_dir`；或复用 `fs_write` 白名单 + 提示词约束（二选一，**首版推荐单独 Skill**，行为更可控）。

### 14.4 待决项的默认决议

| 模糊点 | 默认决议 |
|--------|----------|
| `WorkflowRunRequest` 未带 `sql_data_source_id` / `excel_dataset_id` | **首版**：必须二选一传入，否则 `POST /runs` 返回 **400** 并提示绑定数据源；**不做**「仅从 user_input 猜数据源」。会话级「记住上次数据源」留作 v2。 |
| Excel「上传」 | **首版**：仅 **注册已存在于 `EXCEL_DATA_ROOT` 下的相对路径`**（管理员拷贝文件进目录）；**multipart 上传**列为 v2，避免首版 scope 膨胀。 |
| `RunArtifacts` 扩展字段 | 在 `schemas.py` 中为 **可选字段** 追加；旧客户端忽略即可；与参考字段并存。 |
| 是否允许任意 Python 执行 | **首版禁止**通用 `exec`/`eval` 类工具；仅允许 **白名单工具**（上表 + datalayer）。后续若加「沙箱 Python」须单独规格与安全评审。 |
| LangGraph API 细节 | 以 **当前 `langgraph` 发行版官方文档**为准实现子图组合；规格不锁定具体函数名（`compile` / `invoke` 等随版本迁移）。 |

### 14.5 文档仍依赖的外部真值

- **参考仓库**中 `SkillDefinition.tool` 的实际 JSON 形状、`store` 表结构：以 clone 后的代码为准；本规格描述的是**语义与增量**，不是逐行 diff。  
- **各 `WorkflowType` 的 `required_agent_count`**：与参考 `store.get_templates()` 保持一致；若 seed 改为「四专家 + 路由」等，在 `seed_defaults` 内写死并与 `/workflow-templates` 一致。

---

*文档版本：2.2 — 数据分析领域版；`WorkflowType` 与 `BuiltinCapability` 均与参考仓库字面量对齐；SQL/Excel 经 Skill 工具 + `datalayer` 实现；§14 为 Claude Code 交付补强。*

