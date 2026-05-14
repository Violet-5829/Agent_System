<template>
  <div class="playground-layout">
    <!-- 左侧配置 -->
    <div class="playground-sidebar">
      <div class="card">
        <h3 style="margin-bottom:12px">运行配置</h3>
        <div class="form-group">
          <label>工作流</label>
          <select v-model="run.workflow_id">
            <option value="">-- 选择工作流 --</option>
            <option v-for="w in workflows" :key="w.id" :value="w.id">{{ w.name }} ({{ typeLabel(w.type) }})</option>
          </select>
        </div>
        <div class="form-group">
          <label>数据源类型</label>
          <select v-model="dataSourceType">
            <option value="">-- 无 --</option>
            <option value="sql">SQL 数据源</option>
            <option value="excel">Excel 数据集</option>
          </select>
        </div>
        <div class="form-group" v-if="dataSourceType === 'sql'">
          <label>SQL 数据源</label>
          <select v-model="run.sql_data_source_id">
            <option value="">-- 选择 --</option>
            <option v-for="s in sqlSources" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </div>
        <div class="form-group" v-if="dataSourceType === 'excel'">
          <label>Excel 数据集</label>
          <select v-model="run.excel_dataset_id">
            <option value="">-- 选择 --</option>
            <option v-for="d in excelDatasets" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>任务描述</label>
          <textarea v-model="run.user_input" rows="3" placeholder="描述你的数据分析需求..."></textarea>
        </div>
        <button class="btn btn-success" style="width:100%" @click="execute" :disabled="running">
          {{ running ? '执行中...' : '▶ 运行' }}
        </button>
        <div v-if="error" style="margin-top:8px;color:#ef4444;font-size:12px">{{ error }}</div>
      </div>

      <!-- 会话列表 -->
      <div class="card" v-if="conversations.length">
        <h3 style="margin-bottom:8px">历史会话</h3>
        <div v-for="c in conversations" :key="c.id"
             style="padding:6px 8px;cursor:pointer;border-radius:6px;font-size:12px"
             :style="{ background: c.id === run.conversation_id ? '#e0e7ff' : 'transparent' }"
             @click="loadConv(c)">
          {{ c.title || c.id }} <span style="color:#9ca3af">{{ c.created_at.slice(0, 10) }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧结果 -->
    <div class="playground-main">
      <!-- 输出区与 Trace 切换 -->
      <div style="display:flex;gap:8px;margin-bottom:4px">
        <button :class="tab === 'output' ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'" @click="tab='output'">输出</button>
        <button :class="tab === 'trace' ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'" @click="tab='trace'">Trace ({{ traces.length }})</button>
        <button :class="tab === 'graph' ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'" @click="tab='graph'">拓扑图</button>
        <button :class="tab === 'artifacts' ? 'btn btn-primary btn-sm' : 'btn btn-outline btn-sm'" @click="tab='artifacts'">产物</button>
      </div>

      <!-- 输出区 -->
      <div v-if="tab === 'output'" class="card" style="flex:1;overflow-y:auto">
        <div v-if="result">
          <div style="margin-bottom:12px">
            <strong>回答：</strong>
            <div style="white-space:pre-wrap;font-size:13px;margin-top:4px">{{ result.assistant_message }}</div>
          </div>
          <div v-if="result.artifacts.dataset_summary" style="font-size:12px;color:#6b7280">
            <strong>数据概览：</strong>{{ result.artifacts.dataset_summary }}
          </div>
        </div>
        <div v-else style="color:#9ca3af;text-align:center;padding:40px">
          点击「运行」开始分析
        </div>
      </div>

      <!-- Trace -->
      <div v-if="tab === 'trace'" class="card">
        <div class="trace-list">
          <div v-for="(t,i) in traces" :key="i" class="trace-item">
            <span class="trace-type">[{{ t.type }}]</span>
            <span class="trace-title">{{ t.title }}</span>
            <span style="font-size:11px;color:#9ca3af;margin-left:4px">{{ t.detail?.slice(0, 100) }}</span>
            <span class="trace-time">{{ t.at?.slice(11, 19) }}</span>
          </div>
        </div>
      </div>

      <!-- 拓扑图 -->
      <div v-if="tab === 'graph' && result?.graph" class="card">
        <div class="graph-container">
          <div v-for="n in result.graph.nodes" :key="n.id" style="margin:4px 0">
            <span :class="'graph-node ' + n.kind">
              {{ n.label }} <span style="font-size:10px;opacity:0.6">({{ n.kind }})</span>
            </span>
            <span v-if="n.parent_id" style="font-size:10px;color:#9ca3af"> ↳ {{ n.parent_id }}</span>
          </div>
          <div v-for="(e,i) in result.graph.edges" :key="'e'+i" class="graph-edge">
            {{ e.source }} → {{ e.target }}
            <span v-if="e.label">[{{ e.label }}]</span>
          </div>
        </div>
      </div>

      <!-- 产物 -->
      <div v-if="tab === 'artifacts' && result?.artifacts" class="card">
        <h4 style="margin-bottom:8px">图表</h4>
        <div class="artifacts-grid" v-if="result.artifacts.chart_paths?.length">
          <div v-for="p in result.artifacts.chart_paths" :key="p" class="artifact-card">
            <img :src="'/artifacts/' + p.split('/artifacts/')[1]?.replace(/\\/g,'/')" :alt="p" />
          </div>
        </div>
        <div v-else style="color:#9ca3af">无图表</div>

        <h4 style="margin:12px 0 8px">报表</h4>
        <div v-if="result.artifacts.report_path">
          <a :href="'/artifacts/' + result.artifacts.report_path.split('/artifacts/')[1]?.replace(/\\/g,'/')" target="_blank">
            打开报表
          </a>
        </div>
        <div v-else style="color:#9ca3af">无报表</div>

        <div v-if="result.artifacts.queries_used?.length" style="margin-top:12px">
          <h4 style="margin-bottom:4px">已执行查询</h4>
          <div v-for="(q,i) in result.artifacts.queries_used" :key="i"
               style="font-family:monospace;font-size:11px;background:#f3f4f6;padding:4px 8px;margin:2px 0;border-radius:4px">
            {{ q }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import { api, streamRun } from '../api.js'

const STORAGE_KEY = 'playground_run_config'

const TYPE_LABELS = {
  single_agent_chat: '单智能体',
  router_specialists: '路由',
  planner_executor: '规划执行',
  supervisor_dynamic: '监督者',
  peer_handoff: '交接',
}

export default {
  setup() {
    const workflows = ref([])
    const sqlSources = ref([])
    const excelDatasets = ref([])
    const conversations = ref([])

    // 从 localStorage 恢复上次的运行配置
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    const run = ref({
      workflow_id: saved.workflow_id || '',
      user_input: '',
      sql_data_source_id: saved.sql_data_source_id || '',
      excel_dataset_id: saved.excel_dataset_id || '',
      conversation_id: saved.conversation_id || '',
    })
    const dataSourceType = ref(saved.dataSourceType || '')
    const running = ref(false)
    const error = ref('')
    const result = ref(null)
    const traces = ref([])
    const tab = ref('output')

    async function load() {
      workflows.value = await api.getWorkflows()
      sqlSources.value = await api.getSqlDataSources()
      excelDatasets.value = await api.getExcelDatasets()
      // 恢复后自动加载会话列表
      if (run.value.workflow_id) {
        loadConversations()
      }
    }
    onMounted(load)

    // 监听 workflow 变化，自动加载会话 + 持久化
    watch(() => run.value.workflow_id, (newId) => {
      if (newId) {
        loadConversations()
      } else {
        conversations.value = []
      }
      saveConfig()
    })
    // 监听数据源变化，持久化
    watch([() => run.value.sql_data_source_id, () => run.value.excel_dataset_id, dataSourceType], () => {
      saveConfig()
    })

    function saveConfig() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        workflow_id: run.value.workflow_id,
        sql_data_source_id: run.value.sql_data_source_id,
        excel_dataset_id: run.value.excel_dataset_id,
        dataSourceType: dataSourceType.value,
        conversation_id: run.value.conversation_id,
      }))
    }

    async function loadConversations() {
      if (run.value.workflow_id) {
        try {
          conversations.value = await api.getConversations(run.value.workflow_id)
        } catch(e) {
          conversations.value = []
        }
      }
    }

    async function loadConv(c) {
      run.value.conversation_id = c.id
      saveConfig()
      try {
        const conv = await api.getConversation(c.id)
        // 从会话历史恢复 messages 显示
        if (conv && conv.messages && conv.messages.length) {
          const lastMsg = conv.messages[conv.messages.length - 1]
          if (lastMsg.role === 'assistant' && !result.value) {
            result.value = { assistant_message: lastMsg.content, artifacts: {}, trace: [], graph: { nodes: [], edges: [] } }
          }
        }
      } catch(e) { /* ignore */ }
    }

    async function execute() {
      if (!run.value.workflow_id || !run.value.user_input) {
        error.value = '请选择工作流并输入任务'
        return
      }
      if (dataSourceType.value === 'sql' && !run.value.sql_data_source_id) {
        error.value = '请选择 SQL 数据源'
        return
      }
      if (dataSourceType.value === 'excel' && !run.value.excel_dataset_id) {
        error.value = '请选择 Excel 数据集'
        return
      }
      if (!dataSourceType.value) {
        error.value = '请选择数据源类型并绑定数据源'
        return
      }

      running.value = true
      error.value = ''
      result.value = null
      traces.value = []

      const payload = {
        workflow_id: run.value.workflow_id,
        user_input: run.value.user_input,
        conversation_id: run.value.conversation_id || null,
      }
      if (dataSourceType.value === 'sql') {
        payload.sql_data_source_id = run.value.sql_data_source_id
        payload.excel_dataset_id = null
      } else {
        payload.sql_data_source_id = null
        payload.excel_dataset_id = run.value.excel_dataset_id
      }

      try {
        await streamRun(
          payload,
          (trace) => traces.value.push(trace),
          (final) => {
            result.value = final
            if (final.conversation_id) {
              run.value.conversation_id = final.conversation_id
              saveConfig()
              loadConversations()
            }
          },
          (err) => { error.value = err.message || JSON.stringify(err) },
        )
      } catch(e) {
        error.value = e.message
      }
      running.value = false
    }

    function typeLabel(t) { return TYPE_LABELS[t] || t }

    return {
      workflows, sqlSources, excelDatasets, conversations,
      run, dataSourceType, running, error, result, traces, tab,
      execute, loadConv, typeLabel,
    }
  }
}
</script>
