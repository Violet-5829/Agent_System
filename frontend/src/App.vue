<template>
  <div>
    <header class="app-header">
      <h1>数据分析 Agent Playground</h1>
      <nav>
        <a v-for="p in pages" :key="p.key"
           :class="{ active: currentPage === p.key }"
           @click.prevent="currentPage = p.key" href="#">
          {{ p.label }}
        </a>
      </nav>
    </header>
    <main class="app-main">
      <SettingsPage v-if="currentPage === 'settings'" />
      <DataSourcesPage v-else-if="currentPage === 'datasources'" />
      <SkillsPage v-else-if="currentPage === 'skills'" />
      <AgentsPage v-else-if="currentPage === 'agents'" />
      <WorkflowsPage v-else-if="currentPage === 'workflows'" />
      <PlaygroundPage v-else-if="currentPage === 'playground'" />
    </main>
  </div>
</template>

<script>
import { ref } from 'vue'
import SettingsPage from './pages/SettingsPage.vue'
import DataSourcesPage from './pages/DataSourcesPage.vue'
import SkillsPage from './pages/SkillsPage.vue'
import AgentsPage from './pages/AgentsPage.vue'
import WorkflowsPage from './pages/WorkflowsPage.vue'
import PlaygroundPage from './pages/PlaygroundPage.vue'

export default {
  components: {
    SettingsPage, DataSourcesPage, SkillsPage,
    AgentsPage, WorkflowsPage, PlaygroundPage,
  },
  setup() {
    const currentPage = ref('playground')
    const pages = [
      { key: 'playground', label: 'Playground' },
      { key: 'agents', label: '智能体' },
      { key: 'workflows', label: '工作流' },
      { key: 'skills', label: '技能' },
      { key: 'datasources', label: '数据源' },
      { key: 'settings', label: '设置' },
    ]
    return { currentPage, pages }
  }
}
</script>
