<template>
  <div class="card">
    <div class="card-header"><h3>技能列表</h3></div>
    <div v-if="skills.length === 0" style="color:#9ca3af">暂无技能。系统启动时自动创建 4 个官方数据分析 Skill。</div>
    <table v-else>
      <thead><tr><th>名称</th><th>描述</th><th>工具</th><th>来源</th></tr></thead>
      <tbody>
        <tr v-for="s in skills" :key="s.id">
          <td>{{ s.name }}</td>
          <td>{{ s.description }}</td>
          <td>
            <span v-if="s.tool" class="badge badge-green">{{ s.tool.name }}</span>
            <span v-else class="badge badge-blue">仅提示词</span>
          </td>
          <td>{{ s.source_provider || '本地' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  setup() {
    const skills = ref([])
    onMounted(async () => {
      skills.value = await api.getSkills()
    })
    return { skills }
  }
}
</script>
