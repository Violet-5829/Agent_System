<template>
  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <h3>工作流</h3>
        <button class="btn btn-primary btn-sm" @click="showForm = true">创建</button>
      </div>
      <table>
        <thead><tr><th>名称</th><th>类型</th><th>Agent 数</th><th>Finalizer</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="w in workflows" :key="w.id">
            <td>{{ w.name }}</td>
            <td><span class="badge badge-blue">{{ typeLabel(w.type) }}</span></td>
            <td>{{ w.specialist_agent_ids.length }}</td>
            <td>{{ w.finalizer_enabled ? '开启' : '关闭' }}</td>
            <td>
              <button class="btn btn-outline btn-sm" @click="viewGraph(w)">拓扑</button>
              <button class="btn btn-danger btn-sm" style="margin-left:4px" @click="remove(w.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" v-if="graph">
      <div class="card-header"><h3>拓扑图: {{ graphName }}</h3></div>
      <div class="graph-container">
        <div v-for="n in graph.nodes" :key="n.id" style="margin:4px 0">
          <span :class="'graph-node ' + n.kind">
            {{ n.label }}
            <span style="font-size:10px;color:#9ca3af;margin-left:4px">({{ n.kind }})</span>
          </span>
          <span v-if="n.parent_id" style="font-size:10px;color:#9ca3af"> ↳ 在 {{ n.parent_id }} 内</span>
        </div>
        <div v-for="(e,i) in graph.edges" :key="i" class="graph-edge">
          {{ e.source }} → {{ e.target }}
          <span v-if="e.label" style="color:#6b7280">[{{ e.label }}]</span>
        </div>
      </div>
    </div>
  </div>

  <div v-if="showForm" class="modal-overlay" @click.self="showForm=false">
    <div class="modal">
      <h3>创建工作流</h3>
      <div class="form-group"><label>名称</label><input v-model="form.name" /></div>
      <div class="form-group">
        <label>类型</label>
        <select v-model="form.type" @change="onTypeChange">
          <option v-for="t in templates" :key="t.type" :value="t.type">{{ t.label }} (≥{{ t.required_agent_count }} Agent)</option>
        </select>
      </div>
      <div class="form-group">
        <label>绑定 Agent</label>
        <div v-for="a in agents" :key="a.id" style="font-size:12px">
          <label style="display:inline">
            <input type="checkbox" :value="a.id" v-model="form.specialist_agent_ids" /> {{ a.name }}
          </label>
        </div>
      </div>
      <div class="form-group"><label>路由提示词</label><textarea v-model="form.router_prompt" rows="3"></textarea></div>
      <div class="form-group">
        <label><input type="checkbox" v-model="form.finalizer_enabled" /> 启用 Finalizer</label>
      </div>
      <div class="modal-actions">
        <button class="btn btn-outline" @click="showForm=false">取消</button>
        <button class="btn btn-primary" @click="create">创建</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const TYPE_LABELS = {
  single_agent_chat: '单智能体对话',
  router_specialists: '路由专家',
  planner_executor: '规划执行',
  supervisor_dynamic: '监督者动态',
  peer_handoff: '专家交接',
}

export default {
  setup() {
    const workflows = ref([])
    const agents = ref([])
    const templates = ref([])
    const showForm = ref(false)
    const graph = ref(null)
    const graphName = ref('')
    const form = ref({
      name: '', type: 'single_agent_chat', specialist_agent_ids: [],
      router_prompt: '你是一个工作流路由器。根据用户意图选择最合适的专家。',
      finalizer_enabled: true,
    })

    async function load() {
      workflows.value = await api.getWorkflows()
      agents.value = await api.getAgents()
      templates.value = await api.getTemplates()
    }
    onMounted(load)

    function typeLabel(t) { return TYPE_LABELS[t] || t }

    async function viewGraph(w) {
      try {
        graph.value = await api.getWorkflowGraph(w.id)
        graphName.value = w.name
      } catch(e) { alert(e.message) }
    }

    async function create() {
      await api.createWorkflow(form.value)
      showForm.value = false
      form.value = {
        name: '', type: 'single_agent_chat', specialist_agent_ids: [],
        router_prompt: '你是一个工作流路由器。',
        finalizer_enabled: true,
      }
      await load()
    }

    async function remove(id) {
      await api.deleteWorkflow(id)
      await load()
    }

    return { workflows, agents, templates, showForm, graph, graphName, form, typeLabel, viewGraph, create, remove }
  }
}
</script>
