<script setup>
import { computed, inject, nextTick, ref, watch } from "vue";
import { Bot, BrainCircuit, GitBranch, Sparkles, Terminal } from "lucide-vue-next";
import { I18N_KEY } from "../i18n";

const props = defineProps({
  trace: {
    type: Array,
    default: () => [],
  },
  playing: {
    type: Boolean,
    default: false,
  },
});

const i18n = inject(I18N_KEY, null);
const t = i18n?.t || ((key) => key);
const locale = i18n?.locale;
const traceRef = ref(null);
const expandedMap = ref({});
const traceMode = ref("simple");
const hiddenSimpleTypes = new Set(["node_entered", "node_exited"]);
const hiddenSimpleTitles = new Set();

const nodeLabelMap = {
  start: "System Entry",
  end: "End Session",
  router: "Router",
  finalize: "Output Engine",
  planner_core: "Planner Core",
  planner_validator: "Plan Validator",
  task_dispatcher: "Task Dispatcher",
  synthesizer: "Synthesizer",
  supervisor_intake: "Supervisor Intake",
  delegation_policy: "Delegation Policy",
  supervisor_review: "Supervisor Review",
  first_owner_router: "First Owner Router",
  peer_pool: "Peer Pool",
};

function sourceTrace() {
  return Array.isArray(props.trace) ? props.trace : [];
}

function isSimpleHiddenEvent(event) {
  return (
    hiddenSimpleTypes.has(String(event?.type || "")) ||
    hiddenSimpleTitles.has(String(event?.title || ""))
  );
}

function isAgentNodeId(nodeId) {
  return String(nodeId || "").startsWith("agent_");
}

function isAgentExecutionStart(event) {
  if (String(event?.type || "") !== "node_entered") return false;
  const nodeId = String(event?.payload?.node_id || "");
  return isAgentNodeId(nodeId);
}

function isMatchingAgentExecutionEnd(event, nodeId) {
  return (
    String(event?.type || "") === "node_exited" &&
    String(event?.payload?.node_id || "") === String(nodeId || "")
  );
}

function humanizeToken(value) {
  return String(value || "")
    .replace(/^agent_/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function nodeLabel(nodeId) {
  const normalized = String(nodeId || "").trim();
  if (!normalized) return "System";
  if (nodeLabelMap[normalized]) return nodeLabelMap[normalized];
  if (isAgentNodeId(normalized)) return humanizeToken(normalized) || "Agent";
  return humanizeToken(normalized);
}

function extractAgentLabel(startEvent, children) {
  const payloadName = String(startEvent?.payload?.agent_name || "").trim();
  if (payloadName) return payloadName;

  const detailSources = [
    String(startEvent?.detail || "").trim(),
    ...children.map((child) => String(child?.detail || "").trim()),
  ];
  for (const detail of detailSources) {
    if (!detail) continue;
    const patterns = [
      /^(.*?)\s+is\b/,
      /^(.*?)\s+returned\b/,
      /^(.*?)\s+reported\b/,
      /^(.*?)\s+completed\b/,
      /^(.*?)\s+正在/,
    ];
    for (const pattern of patterns) {
      const matched = detail.match(pattern);
      if (matched?.[1]?.trim()) {
        return matched[1].trim();
      }
    }
  }

  const nodeId = String(startEvent?.payload?.node_id || "").trim();
  return nodeLabel(nodeId) || "Agent";
}

function filesystemVerification(event) {
  const title = String(event?.title || "");
  const payload = event?.payload || {};
  const toolName = String(payload?.tool_name || "");
  const preview = String(payload?.preview || "").trim();
  const generatedFiles = Array.isArray(payload?.generated_files) ? payload.generated_files : [];
  const ok = payload?.ok !== false;

  if (!toolName.startsWith("fs_")) return null;

  if (title === "Tool Finished" && ok) {
    if (toolName === "fs_make_directory") {
      return {
        tone: "verified",
        label: "Verified Directory",
        detail: generatedFiles[0] ? `Confirmed via tool: ${generatedFiles[0]}` : "Directory creation was confirmed by the tool.",
      };
    }
    if (toolName === "fs_write_file" || toolName === "fs_append_file") {
      return {
        tone: "verified",
        label: "Verified File Write",
        detail: generatedFiles[0] ? `Confirmed via tool: ${generatedFiles[0]}` : "File write was confirmed by the tool.",
      };
    }
    if (toolName === "fs_move_path") {
      return {
        tone: "verified",
        label: "Verified Move",
        detail: preview || "Move/rename was confirmed by the tool.",
      };
    }
    if (toolName === "fs_delete_path") {
      return {
        tone: "verified",
        label: "Verified Delete",
        detail: preview || "Deletion was confirmed by the tool.",
      };
    }
  }

  if (title === "Tool Output" && preview) {
    if (toolName === "fs_make_directory") {
      return {
        tone: "verified",
        label: "Verified Directory",
        detail: preview,
      };
    }
    if (toolName === "fs_write_file" || toolName === "fs_append_file") {
      return {
        tone: "verified",
        label: "Verified File Write",
        detail: preview,
      };
    }
    if (toolName === "fs_read_file") {
      return {
        tone: "evidence",
        label: "Verified Read",
        detail: preview,
      };
    }
    if (toolName === "fs_list_directory" || toolName === "fs_list_roots" || toolName === "fs_search_paths") {
      return {
        tone: "evidence",
        label: "Verified Listing",
        detail: preview,
      };
    }
  }

  if ((title === "Tool Failed" || title === "Tool Unavailable") && toolName.startsWith("fs_")) {
    return {
      tone: "warning",
      label: "Filesystem Tool Failed",
      detail: String(event?.detail || "").trim(),
    };
  }

  return null;
}

function eventPayloadText(event) {
  if (!event?.payload || !Object.keys(event.payload).length) return "";
  return JSON.stringify(event.payload, null, 2);
}

function eventStage(event) {
  const title = String(event?.title || "");
  const type = String(event?.type || "");
  const payload = event?.payload || {};
  const nodeId = String(payload?.node_id || "");

  if (title.startsWith("Tool ") || String(payload?.tool_name || "")) return "tool";
  if (title.includes("workflow") || type === "workflow") return "system";
  if (title.includes("route") || title.includes("Route") || nodeId === "router" || nodeId.includes("router")) return "routing";
  if (nodeId === "finalize" || nodeId === "synthesizer" || title.includes("Finalizer") || title.includes("Synthesizer")) return "finalize";
  if (type === "node_entered" || type === "node_exited") return "node";
  return "event";
}

function eventStatus(event) {
  const title = String(event?.title || "");
  const detail = String(event?.detail || "");
  const payload = event?.payload || {};

  if (title === "Tool Finished" || payload?.ok === true) return { label: "ok", tone: "ok" };
  if (title === "Tool Failed" || title === "Tool Unavailable" || payload?.ok === false) return { label: "issue", tone: "issue" };
  if (detail.includes("completed") || detail.includes("complete") || detail.includes("finished")) return { label: "done", tone: "done" };
  if (title === "Tool Started") return { label: "running", tone: "running" };
  return null;
}

function eventTarget(event) {
  const payload = event?.payload || {};
  const nextNodeId = String(payload?.next_node_id || "").trim();
  const toolName = String(payload?.tool_name || "").trim();
  const nodeId = String(payload?.node_id || "").trim();

  if (nextNodeId) return nodeLabel(nextNodeId);
  if (toolName) return toolName;
  if (nodeId) return nodeLabel(nodeId);
  return "";
}

function eventAction(event) {
  const title = String(event?.title || "").trim();
  const type = String(event?.type || "").trim();
  const payload = event?.payload || {};
  const nodeId = String(payload?.node_id || "").trim();

  if (title) return title;
  if (type === "node_entered") return `Entered ${nodeLabel(nodeId)}`;
  if (type === "node_exited") return `Exited ${nodeLabel(nodeId)}`;
  return type || "Trace Event";
}

function actorMetaFromEvent(event) {
  const payload = event?.payload || {};
  const nodeId = String(payload?.node_id || "").trim();
  const stage = eventStage(event);

  if (String(payload?.agent_name || "").trim()) {
    return {
      key: `agent:${payload.agent_name}`,
      label: String(payload.agent_name).trim(),
      subtitle: "Agent Trace Card",
      kind: "agent",
    };
  }

  if (nodeId) {
    const label = nodeLabel(nodeId);
    if (nodeId === "router" || nodeId.includes("router")) {
      return { key: `routing:${nodeId}`, label, subtitle: "Routing Trace Card", kind: "logic" };
    }
    if (nodeId === "finalize" || nodeId === "synthesizer") {
      return { key: `finalize:${nodeId}`, label, subtitle: "Final Response Card", kind: "finalize" };
    }
    if (nodeId === "start" || nodeId === "end") {
      return { key: `system:${nodeId}`, label, subtitle: "System Trace Card", kind: "system" };
    }
    return { key: `node:${nodeId}`, label, subtitle: "Workflow Trace Card", kind: stage === "tool" ? "tool" : "logic" };
  }

  if (stage === "tool") {
    return { key: "tool-runtime", label: "Tool Runtime", subtitle: "Tool Trace Card", kind: "tool" };
  }

  return { key: "system-runtime", label: "System Entry", subtitle: "System Trace Card", kind: "system" };
}

function stepFromEvent(event, idPrefix) {
  return {
    id: `${idPrefix}-${event?.at || "no-at"}`,
    action: eventAction(event),
    detail: String(event?.detail || "").trim(),
    target: eventTarget(event),
    stage: eventStage(event),
    status: eventStatus(event),
    verification: filesystemVerification(event),
    payloadText: eventPayloadText(event),
    at: event?.at || "",
    rawType: String(event?.type || ""),
  };
}

const simpleTraceItems = computed(() => {
  const source = sourceTrace();
  const items = [];

  for (let index = 0; index < source.length; index += 1) {
    const event = source[index];
    if (isAgentExecutionStart(event)) {
      const nodeId = String(event?.payload?.node_id || "");
      const children = [];
      let endEvent = null;
      let cursor = index + 1;

      while (cursor < source.length) {
        const candidate = source[cursor];
        if (isMatchingAgentExecutionEnd(candidate, nodeId)) {
          endEvent = candidate;
          break;
        }
        children.push(candidate);
        cursor += 1;
      }

      const visibleChildren = children.filter((child) => !isSimpleHiddenEvent(child));
      items.push({
        kind: "agent_block",
        event,
        endEvent,
        index,
        at: event?.at || "",
        nodeId,
        nodeLabel: nodeLabel(nodeId),
        agentLabel: extractAgentLabel(event, visibleChildren),
        children: visibleChildren,
      });
      index = cursor;
      continue;
    }

    if (isSimpleHiddenEvent(event)) continue;
    items.push({
      kind: "event",
      event,
      index,
      at: event?.at || "",
    });
  }

  return items;
});

const detailTraceItems = computed(() =>
  sourceTrace().map((event, index) => ({
    kind: "event",
    event,
    index,
    at: event?.at || "",
  })),
);

const traceItems = computed(() => (traceMode.value === "detail" ? detailTraceItems.value : simpleTraceItems.value));

const groupedTrace = computed(() => {
  const groups = [];

  simpleTraceItems.value.forEach((item, index) => {
    let actor;
    let steps;

    if (item.kind === "agent_block") {
      actor = {
        key: `agent:${item.nodeId}:${item.agentLabel}`,
        label: item.agentLabel,
        subtitle: "Agent Trace Card",
        kind: "agent",
      };
      steps = [
        stepFromEvent(
          {
            ...item.event,
            title: item.event?.title || "Agent Started",
            detail: item.event?.detail || `${item.agentLabel} entered ${item.nodeLabel}.`,
          },
          `${item.nodeId}-start`,
        ),
        ...item.children.map((child, childIndex) => stepFromEvent(child, `${item.nodeId}-${childIndex}`)),
      ];

      if (item.endEvent) {
        steps.push(
          stepFromEvent(
            {
              ...item.endEvent,
              title: item.endEvent?.title || "Agent Completed",
            },
            `${item.nodeId}-end`,
          ),
        );
      }
    } else {
      actor = actorMetaFromEvent(item.event);
      steps = [stepFromEvent(item.event, `event-${index}`)];
    }

    const lastGroup = groups[groups.length - 1];
    if (lastGroup && lastGroup.key === actor.key) {
      lastGroup.steps.push(...steps);
      return;
    }

    groups.push({
      ...actor,
      steps,
    });
  });

  return groups;
});

function traceKey(event, index) {
  return `${event?.at || "no-at"}-${index}`;
}

function isCollapsible(event) {
  return event?.type === "node_entered" || event?.type === "node_exited";
}

function isExpanded(event, index) {
  if (!isCollapsible(event)) return true;
  return !!expandedMap.value[traceKey(event, index)];
}

function toggleEvent(event, index) {
  if (!isCollapsible(event)) return;
  const key = traceKey(event, index);
  expandedMap.value = {
    ...expandedMap.value,
    [key]: !expandedMap.value[key],
  };
}

function formatTime(isoString) {
  try {
    const targetLocale = locale?.value === "zh-CN" ? "zh-CN" : "en-GB";
    return new Date(isoString).toLocaleTimeString(targetLocale, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoString;
  }
}

function actorIcon(kind) {
  if (kind === "agent") return Bot;
  if (kind === "logic") return BrainCircuit;
  if (kind === "finalize") return Sparkles;
  if (kind === "tool") return Terminal;
  return GitBranch;
}

watch(
  () => traceItems.value.length,
  async () => {
    if (!traceRef.value) return;
    await nextTick();
    traceRef.value.scrollTop = traceRef.value.scrollHeight;
  },
);
</script>

<template>
  <section class="glass-panel trace-shell">
    <header class="run-panel-header">
      <h3 class="run-panel-title">
        <Terminal :size="18" class="text-slate-400" />
        Trace
      </h3>
      <div class="trace-toolbar">
        <div class="trace-mode-switch" role="tablist" aria-label="Trace mode">
          <button
            type="button"
            class="trace-mode-button"
            :class="{ active: traceMode === 'simple' }"
            @click="traceMode = 'simple'"
          >
            {{ t("trace.showKey") }}
          </button>
          <button
            type="button"
            class="trace-mode-button"
            :class="{ active: traceMode === 'detail' }"
            @click="traceMode = 'detail'"
          >
            {{ t("trace.showAll") }}
          </button>
        </div>
        <span class="chip chip-green">{{ playing ? t("trace.playing") : t("trace.live") }}</span>
      </div>
    </header>

    <div v-if="traceItems.length" ref="traceRef" class="trace-list">
      <template v-if="traceMode === 'simple'">
        <article
          v-for="(group, groupIndex) in groupedTrace"
          :key="`${group.key}-${groupIndex}`"
          class="trace-group"
          :class="`trace-group-${group.kind}`"
        >
          <div class="trace-group-card">
            <div class="trace-group-head">
              <div class="trace-group-identity">
                <div class="trace-group-icon">
                  <component :is="actorIcon(group.kind)" :size="16" />
                </div>
                <div>
                  <strong class="trace-group-title">{{ group.label }}</strong>
                  <p class="trace-group-subtitle">{{ group.subtitle }}</p>
                </div>
              </div>
              <span class="chip trace-group-count">{{ group.steps.length }} Steps</span>
            </div>

            <div class="trace-group-flow">
              <article
                v-for="(step, stepIndex) in group.steps"
                :key="step.id"
                class="trace-flow-step"
              >
                <div class="trace-flow-node"></div>
                <div class="trace-flow-body">
                  <div class="trace-flow-top">
                    <div class="trace-flow-heading">
                      <span class="trace-flow-action">{{ step.action }}</span>
                      <span
                        v-if="step.status"
                        class="trace-flow-status"
                        :class="`trace-flow-status-${step.status.tone}`"
                      >
                        {{ step.status.label }}
                      </span>
                    </div>
                    <span class="trace-flow-time">{{ formatTime(step.at) }}</span>
                  </div>

                  <div class="trace-flow-meta">
                    <span v-if="step.target" class="trace-flow-target">Target: {{ step.target }}</span>
                    <span class="trace-flow-stage">{{ step.stage }}</span>
                  </div>

                  <p v-if="step.detail" class="trace-flow-detail">{{ step.detail }}</p>

                  <div
                    v-if="step.verification"
                    class="trace-verification"
                    :class="step.verification.tone"
                  >
                    <strong>{{ step.verification.label }}</strong>
                    <span>{{ step.verification.detail }}</span>
                  </div>

                  <pre v-if="step.payloadText" class="trace-json-block">{{ step.payloadText }}</pre>
                </div>
              </article>
            </div>
          </div>

          <div v-if="groupIndex < groupedTrace.length - 1" class="trace-group-connector"></div>
        </article>
      </template>

      <template v-else>
        <article
          v-for="item in traceItems"
          :key="`${item.at}-${item.index}`"
          class="trace-item"
        >
          <div class="trace-dot"></div>
          <div class="trace-body">
            <div class="trace-time">{{ formatTime(item.at) }}</div>
            <div
              class="trace-card trace-card-detail"
              :class="{ collapsed: isCollapsible(item.event) && !isExpanded(item.event, item.index) }"
            >
              <button
                class="trace-head trace-head-button"
                :class="{ collapsible: isCollapsible(item.event) }"
                type="button"
                :aria-disabled="!isCollapsible(item.event)"
                @click="toggleEvent(item.event, item.index)"
              >
                <div class="trace-detail-title">
                  <strong>{{ eventAction(item.event) }}</strong>
                  <span class="trace-detail-subtitle">{{ actorMetaFromEvent(item.event).label }}</span>
                </div>
                <span class="trace-head-right">
                  <span class="chip">{{ eventStage(item.event) }}</span>
                  <span v-if="eventTarget(item.event)" class="chip chip-blue">{{ eventTarget(item.event) }}</span>
                  <span v-if="isCollapsible(item.event)" class="trace-expand-indicator">
                    {{ isExpanded(item.event, item.index) ? "v" : ">" }}
                  </span>
                </span>
              </button>
              <template v-if="isExpanded(item.event, item.index)">
                <p>{{ item.event.detail }}</p>
                <div
                  v-if="filesystemVerification(item.event)"
                  class="trace-verification"
                  :class="filesystemVerification(item.event).tone"
                >
                  <strong>{{ filesystemVerification(item.event).label }}</strong>
                  <span>{{ filesystemVerification(item.event).detail }}</span>
                </div>
                <pre v-if="eventPayloadText(item.event)" class="trace-json-block trace-json-block-detail">{{ eventPayloadText(item.event) }}</pre>
              </template>
            </div>
          </div>
        </article>
      </template>
    </div>
    <div v-else class="trace-empty">{{ t("trace.empty") }}</div>
  </section>
</template>
