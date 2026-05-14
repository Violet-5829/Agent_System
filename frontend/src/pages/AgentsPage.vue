<template>
  <div class="card">
    <div class="card-header">
      <h3>智能体</h3>
      <button class="btn btn-primary btn-sm" @click="showForm = true">创建</button>
    </div>
    <table>
      <thead><tr><th>名称</th><th>角色</th><th>描述</th><th>绑定技能</th><th>内置能力</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="a in agents" :key="a.id">
          <td><span :class="roleBadge(a.name)">{{ a.name }}</span></td>
          <td style="font-size:12px">{{ roleLabel(a.name) }}</td>
          <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ a.description }}
          </td>
          <td>
            <span v-for="sid in a.skill_ids" :key="sid" class="badge badge-green" style="margin:1px">
              {{ skillNames[sid] || sid.slice(0,12) }}
            </span>
          </td>
          <td>
            <span v-for="c in a.builtin_capabilities" :key="c" class="badge badge-blue" style="margin:1px">{{ c }}</span>
          </td>
          <td>
            <button class="btn btn-outline btn-sm" @click="edit(a)">编辑</button>
            <button class="btn btn-danger btn-sm" style="margin-left:4px" @click="remove(a.id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="showForm" class="modal-overlay" @click.self="showForm=false">
    <div class="modal">
      <h3>{{ editing ? '编辑' : '创建' }}智能体</h3>
      <div class="form-group"><label>名称</label><input v-model="form.name" /></div>
      <div class="form-group"><label>描述</label><input v-model="form.description" /></div>
      <div class="form-group"><label>系统提示词</label><textarea v-model="form.system_prompt" rows="4"></textarea></div>
      <div class="form-group">
        <label>绑定技能</label>
        <div v-for="s in allSkills" :key="s.id" style="font-size:12px">
          <label style="display:inline">
            <input type="checkbox" :value="s.id" v-model="form.skill_ids" /> {{ s.name }}
          </label>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn btn-outline" @click="showForm=false">取消</button>
        <button class="btn btn-primary" @click="save">{{ editing ? '保存' : '创建' }}</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api.js'

const ROLE_MAP = {
  '数据工程师': { badge: 'badge badge-blue', label: '数据工程' },
  '数据分析师': { badge: 'badge badge-green', label: '统计分析' },
  '可视化专家': { badge: 'badge badge-purple', label: '可视化' },
  '报表专家': { badge: 'badge badge-orange', label: '报表' },
}

export default {
  setup() {
    const agents = ref([])
    const allSkills = ref([])
    const showForm = ref(false)
    const editing = ref(null)
    const form = ref({ name: '', description: '', system_prompt: '', skill_ids: [], builtin_capabilities: ['filesystem'] })

    const skillNames = computed(() => {
      const m = {}
      for (const s of allSkills.value) m[s.id] = s.name
      return m
    })

    async function load() {
      agents.value = await api.getAgents()
      allSkills.value = await api.getSkills()
    }
    onMounted(load)

    function roleBadge(name) {
      return (ROLE_MAP[name] || {}).badge || 'badge badge-blue'
    }
    function roleLabel(name) {
      return (ROLE_MAP[name] || {}).label || '通用'
    }
    function edit(a) {
      editing.value = a
      form.value = { ...a }
      showForm.value = true
    }
    async function save() {
      if (editing.value) {
        await api.updateAgent(editing.value.id, form.value)
      } else {
        await api.createAgent(form.value)
      }
      showForm.value = false
      editing.value = null
      form.value = { name: '', description: '', system_prompt: '', skill_ids: [], builtin_capabilities: ['filesystem'] }
      await load()
    }
    async function remove(id) {
      await api.deleteAgent(id)
      await load()
    }

    return { agents, allSkills, skillNames, showForm, editing, form, roleBadge, roleLabel, edit, save, remove }
  }
}
</script>
