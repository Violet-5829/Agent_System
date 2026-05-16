<script setup>
import { inject, onMounted, ref, watch } from "vue";
import ChatRunner from "../components/ChatRunner.vue";
import GraphViewer from "../components/GraphViewer.vue";
import TraceViewer from "../components/TraceViewer.vue";
import { I18N_KEY } from "../i18n";
import { fetchSqlDataSources, fetchExcelDatasets } from "../api";

const props = defineProps({
  workflows: { type: Array, required: true },
  agents: { type: Array, required: true },
  selectedWorkflowId: { type: String, default: "" },
  selectedWorkflow: { type: Object, default: null },
  selectedGraph: { type: Object, default: null },
  activeNodeId: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  trace: { type: Array, default: () => [] },
  tracePlaying: { type: Boolean, default: false },
  chatMessages: { type: Array, default: () => [] },
});

const emit = defineEmits(["run", "clear", "stop", "select-workflow"]);

const i18n = inject(I18N_KEY, null);
const t = i18n?.t || ((key) => key);
const workflowTypeLabel = i18n?.workflowTypeLabel || ((type) => type);
const leftVisible = ref(true);
const rightVisible = ref(true);

// ── 数据源选择 ──────────────────────────
const sqlSources = ref([]);
const excelDatasets = ref([]);
const dataSourceType = ref("");   // "" | "sql" | "excel"
const selectedSqlId = ref("");
const selectedExcelId = ref("");

async function loadDataSources() {
  try { sqlSources.value = await fetchSqlDataSources(); } catch { sqlSources.value = []; }
  try { excelDatasets.value = await fetchExcelDatasets(); } catch { excelDatasets.value = []; }
}

onMounted(loadDataSources);

// 选择工作流后关联上次存储的数据源
watch(() => props.selectedWorkflowId, (id) => {
  if (id) {
    const key = `playground-ds-${id}`;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "{}");
      dataSourceType.value = saved.type || "";
      selectedSqlId.value = saved.sqlId || "";
      selectedExcelId.value = saved.excelId || "";
    } catch { dataSourceType.value = ""; }
  }
});

function saveDataSourceConfig() {
  if (!props.selectedWorkflowId) return;
  const key = `playground-ds-${props.selectedWorkflowId}`;
  localStorage.setItem(key, JSON.stringify({
    type: dataSourceType.value,
    sqlId: selectedSqlId.value,
    excelId: selectedExcelId.value,
  }));
}

// 拦截 run 事件，注入数据源参数
function handleRun(payload) {
  const enriched = { ...payload };
  if (dataSourceType.value === "sql") {
    enriched.sql_data_source_id = selectedSqlId.value || undefined;
  } else if (dataSourceType.value === "excel") {
    enriched.excel_dataset_id = selectedExcelId.value || undefined;
  }
  saveDataSourceConfig();
  emit("run", enriched);
}
</script>

<template>
  <div class="playground-shell">
    <div
      class="playground-grid"
      :class="{ 'left-collapsed': !leftVisible, 'right-collapsed': !rightVisible }"
    >
    <aside v-if="leftVisible" class="playground-col-left">
      <section class="glass-panel workflow-select-card">
        <label class="field-label">{{ t("workflow.selectWorkflow") }}</label>
        <select
          class="workflow-native-select"
          :value="props.selectedWorkflowId"
          @change="$emit('select-workflow', $event.target.value)"
        >
          <option v-for="workflow in props.workflows" :key="workflow.id" :value="workflow.id">
            {{ workflow.name }} - {{ workflowTypeLabel(workflow.type) }}
          </option>
        </select>
      </section>

      <!-- 数据源选择 -->
      <section class="glass-panel workflow-select-card" style="margin-top:12px">
        <label class="field-label">数据源</label>
        <select v-model="dataSourceType" class="workflow-native-select" style="margin-bottom:8px"
                @change="selectedSqlId=''; selectedExcelId=''; saveDataSourceConfig()">
          <option value="">-- 无 --</option>
          <option value="sql">SQL 数据库</option>
          <option value="excel">Excel / CSV 文件</option>
        </select>

        <template v-if="dataSourceType === 'sql'">
          <label class="field-label" style="font-size:11px">SQL 数据源</label>
          <select v-model="selectedSqlId" class="workflow-native-select" @change="saveDataSourceConfig()">
            <option value="">-- 选择 --</option>
            <option v-for="s in sqlSources" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <p v-if="!sqlSources.length" style="font-size:11px;color:#94a3b8;margin-top:4px">
            暂无数据源，请先在「设置」页添加
          </p>
        </template>

        <template v-if="dataSourceType === 'excel'">
          <label class="field-label" style="font-size:11px">Excel 数据集</label>
          <select v-model="selectedExcelId" class="workflow-native-select" @change="saveDataSourceConfig()">
            <option value="">-- 选择 --</option>
            <option v-for="d in excelDatasets" :key="d.id" :value="d.id">{{ d.name }}</option>
          </select>
          <p v-if="!excelDatasets.length" style="font-size:11px;color:#94a3b8;margin-top:4px">
            暂无数据集，请先在「设置」页注册
          </p>
        </template>
      </section>

      <GraphViewer
        :graph="props.selectedGraph"
        :active-node-id="props.activeNodeId"
        :trace="props.trace"
      />
    </aside>

    <section class="playground-col-center">
      <ChatRunner
        :selected-workflow-id="props.selectedWorkflowId"
        :selected-workflow="props.selectedWorkflow"
        :loading="props.loading"
        :left-visible="leftVisible"
        :right-visible="rightVisible"
        :messages="props.chatMessages"
        @run="handleRun"
        @clear="$emit('clear')"
        @stop="$emit('stop')"
        @toggle-left="leftVisible = !leftVisible"
        @toggle-right="rightVisible = !rightVisible"
      />
    </section>

    <aside v-if="rightVisible" class="playground-col-right">
      <TraceViewer :trace="props.trace" :playing="props.tracePlaying" />
    </aside>
    </div>
  </div>
</template>
