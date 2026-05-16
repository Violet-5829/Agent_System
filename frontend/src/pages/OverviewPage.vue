<script setup>
import { computed, inject } from "vue";
import {
  Activity,
  ArrowRight,
  ChevronRight,
  GitBranch,
  Settings2,
  Users,
  Workflow as WorkflowIcon,
} from "lucide-vue-next";
import { I18N_KEY } from "../i18n";

const props = defineProps({
  agents: {
    type: Array,
    required: true,
  },
  workflows: {
    type: Array,
    required: true,
  },
  templates: {
    type: Array,
    required: true,
  },
});

const emit = defineEmits(["navigate"]);

const i18n = inject(I18N_KEY, null);
const t = i18n?.t || ((key) => key);
const workflowTypeLabel = i18n?.workflowTypeLabel || ((type) => type);

const defaultWorkflow = computed(() => props.workflows[0] || null);

const defaultWorkflowAgents = computed(() => {
  if (!defaultWorkflow.value) return [];
  return defaultWorkflow.value.specialist_agent_ids
    .map((id) => props.agents.find((agent) => agent.id === id))
    .filter(Boolean);
});

const steps = computed(() => [
  { id: "01", title: t("overview.step1Title"), detail: t("overview.step1Desc"), tab: "agents" },
  { id: "02", title: t("overview.step2Title"), detail: t("overview.step2Desc"), tab: "workflows" },
  { id: "03", title: t("overview.step3Title"), detail: t("overview.step3Desc"), tab: "playground" },
]);
</script>

<template>
  <div class="page-stack page-overview">
    <section class="overview-grid">
      <div class="glass-panel hero-card">
        <span class="chip chip-blue">{{ t("overview.chip") }}</span>
        <h2>
          {{ t("overview.headline1") }}
          <br />
          {{ t("overview.headline2") }}
        </h2>
        <p>{{ t("overview.desc") }}</p>
        <div class="hero-orb"></div>
      </div>

      <div class="stat-stack">
        <article class="glass-panel stat-tile" @click="emit('navigate', 'agents')">
          <div class="stat-icon stat-icon-blue">
            <Users :size="22" />
          </div>
          <div>
            <div class="stat-label">{{ t("overview.agents") }}</div>
            <div class="stat-value">{{ props.agents.length }}</div>
          </div>
          <ChevronRight :size="18" class="stat-chevron" />
        </article>

        <article class="glass-panel stat-tile" @click="emit('navigate', 'workflows')">
          <div class="stat-icon stat-icon-violet">
            <GitBranch :size="22" />
          </div>
          <div>
            <div class="stat-label">{{ t("overview.workflows") }}</div>
            <div class="stat-value">{{ props.workflows.length }}</div>
          </div>
          <ChevronRight :size="18" class="stat-chevron" />
        </article>

        <article class="glass-panel stat-tile" @click="emit('navigate', 'playground')">
          <div class="stat-icon stat-icon-green">
            <WorkflowIcon :size="22" />
          </div>
          <div>
            <div class="stat-label">{{ t("overview.templates") }}</div>
            <div class="stat-value">{{ props.templates.length }}</div>
          </div>
          <ChevronRight :size="18" class="stat-chevron" />
        </article>
      </div>
    </section>

    <section class="glass-panel section-card">
      <div class="section-header">
        <div>
          <h3>
            <Settings2 :size="18" class="text-slate-400" />
            {{ t("overview.flowTitle") }}
          </h3>
          <p>{{ t("overview.flowDesc") }}</p>
        </div>
      </div>

      <div class="step-grid">
        <button
          v-for="step in steps"
          :key="step.id"
          class="step-card"
          @click="$emit('navigate', step.tab)"
        >
          <div class="step-line">
            <span class="step-index">{{ step.id }}</span>
            <span class="step-divider"></span>
          </div>
          <h4>
            {{ step.title }}
            <ArrowRight :size="15" class="step-arrow" />
          </h4>
          <p>{{ step.detail }}</p>
        </button>
      </div>
    </section>

    <section class="glass-panel section-card">
      <div class="section-header">
        <div>
          <h3>
            <Activity :size="18" class="text-emerald-500" />
            Default Workflow
          </h3>
          <p>This setup is loaded first in Run.</p>
        </div>
        <button class="text-button" @click="$emit('navigate', 'playground')">
          Go to Run
          <ArrowRight :size="14" />
        </button>
      </div>

      <div v-if="defaultWorkflow" class="workflow-highlight">
        <div>
          <div class="workflow-title">{{ defaultWorkflow.name }}</div>
          <div class="workflow-id">workflow_{{ defaultWorkflow.id }}</div>
          <div class="workflow-badges">
            <span class="chip">{{ workflowTypeLabel(defaultWorkflow.type) }}</span>
            <span
              v-for="agent in defaultWorkflowAgents"
              :key="agent.id"
              class="chip chip-blue"
            >
              {{ agent.name }}
            </span>
          </div>
        </div>
        <div class="workflow-mark">
          <WorkflowIcon :size="24" />
        </div>
      </div>

      <div v-else class="trace-empty">No setup yet.</div>
    </section>
  </div>
</template>
