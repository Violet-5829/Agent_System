<template>
  <div class="card">
    <div class="card-header"><h3>模型配置</h3></div>
    <div class="form-group">
      <label>API Key</label>
      <input v-model="settings.openai_api_key" type="password" placeholder="sk-..." />
    </div>
    <div class="form-group">
      <label>Base URL</label>
      <input v-model="settings.openai_base_url" placeholder="https://api.openai.com/v1" />
    </div>
    <div class="form-group">
      <label>Model</label>
      <input v-model="settings.openai_model" placeholder="gpt-4o-mini" />
    </div>
    <button class="btn btn-primary" @click="save">保存设置</button>
    <span v-if="saved" style="margin-left:12px;color:#10b981">已保存</span>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  setup() {
    const settings = ref({
      openai_api_key: '',
      openai_base_url: 'https://api.openai.com/v1',
      openai_model: 'gpt-4o-mini',
    })
    const saved = ref(false)

    onMounted(async () => {
      try {
        const s = await api.getSettings()
        if (s.env_vars) {
          for (const e of s.env_vars) {
            if (settings.value[e.key.toLowerCase()] !== undefined) {
              settings.value[e.key.toLowerCase()] = e.value
            }
          }
        }
      } catch(e) { /* ignore */ }
    })

    async function save() {
      await api.updateSettings({
        model_profiles: [{
          id: 'default',
          provider: 'custom',
          name: 'Default',
          api_key: settings.value.openai_api_key,
          base_url: settings.value.openai_base_url,
          model: settings.value.openai_model,
        }],
        active_model_profile_id: 'default',
        env_vars: [
          { key: 'OPENAI_API_KEY', value: settings.value.openai_api_key },
          { key: 'OPENAI_BASE_URL', value: settings.value.openai_base_url },
          { key: 'OPENAI_MODEL', value: settings.value.openai_model },
        ],
      })
      saved.value = true
      setTimeout(() => saved.value = false, 2000)
    }

    return { settings, saved, save }
  }
}
</script>
