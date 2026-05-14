const BASE = '/api'

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || res.statusText)
  }
  return res.json()
}

export const api = {
  // Health
  health: () => request('/health'),

  // Settings
  getSettings: () => request('/settings'),
  updateSettings: (data) => request('/settings', { method: 'PUT', body: JSON.stringify(data) }),

  // Workflow Templates
  getTemplates: () => request('/workflow-templates'),

  // Skills
  getSkills: () => request('/skills'),
  createSkill: (data) => request('/skills', { method: 'POST', body: JSON.stringify(data) }),

  // Agents
  getAgents: () => request('/agents'),
  createAgent: (data) => request('/agents', { method: 'POST', body: JSON.stringify(data) }),
  updateAgent: (id, data) => request(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAgent: (id) => request(`/agents/${id}`, { method: 'DELETE' }),

  // Workflows
  getWorkflows: () => request('/workflows'),
  createWorkflow: (data) => request('/workflows', { method: 'POST', body: JSON.stringify(data) }),
  updateWorkflow: (id, data) => request(`/workflows/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteWorkflow: (id) => request(`/workflows/${id}`, { method: 'DELETE' }),
  getWorkflowGraph: (id) => request(`/workflows/${id}/graph`),

  // Runs
  runWorkflow: (data) => request('/runs', { method: 'POST', body: JSON.stringify(data) }),

  // Conversations
  getConversations: (workflowId) => request(`/conversations?workflow_id=${workflowId || ''}`),
  getConversation: (id) => request(`/conversations/${id}`),
  deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),

  // SQL Data Sources
  getSqlDataSources: () => request('/sql-data-sources'),
  createSqlDataSource: (data) => request('/sql-data-sources', { method: 'POST', body: JSON.stringify(data) }),
  deleteSqlDataSource: (id) => request(`/sql-data-sources/${id}`, { method: 'DELETE' }),
  probeSqlDataSource: (id) => request(`/sql-data-sources/${id}/probe`, { method: 'POST' }),

  // Excel Datasets
  getExcelDatasets: () => request('/excel-datasets'),
  createExcelDataset: (data) => request('/excel-datasets', { method: 'POST', body: JSON.stringify(data) }),
  deleteExcelDataset: (id) => request(`/excel-datasets/${id}`, { method: 'DELETE' }),
}

export function streamRun(payload, onTrace, onFinal, onError) {
  return fetch(`${BASE}/runs/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(async (res) => {
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6))
          if (eventType === 'trace') onTrace(data)
          else if (eventType === 'final') onFinal(data)
          else if (eventType === 'error') onError(data)
        }
      }
    }
  })
}
