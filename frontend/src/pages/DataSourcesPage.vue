<template>
  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <h3>SQL 数据源</h3>
        <button class="btn btn-primary btn-sm" @click="showSqlForm = true">添加</button>
      </div>
      <table>
        <thead><tr><th>名称</th><th>方言</th><th>只读</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="s in sqlSources" :key="s.id">
            <td>{{ s.name }}</td>
            <td><span class="badge badge-blue">{{ s.dialect }}</span></td>
            <td>{{ s.read_only ? '是' : '否' }}</td>
            <td>
              <button class="btn btn-outline btn-sm" @click="probe(s)">探测</button>
              <button class="btn btn-danger btn-sm" style="margin-left:4px" @click="removeSql(s.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="probeResult" style="margin-top:8px;font-size:12px;color:#374151">{{ probeResult }}</div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>Excel 数据集</h3>
        <button class="btn btn-primary btn-sm" @click="showExcelForm = true">注册</button>
      </div>
      <table>
        <thead><tr><th>名称</th><th>文件路径</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in excelDatasets" :key="d.id">
            <td>{{ d.name }}</td>
            <td style="font-family:monospace;font-size:12px">{{ d.file_path }}</td>
            <td>
              <button class="btn btn-danger btn-sm" @click="removeExcel(d.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- SQL Form Modal -->
  <div v-if="showSqlForm" class="modal-overlay" @click.self="showSqlForm=false">
    <div class="modal">
      <h3>添加 SQL 数据源</h3>
      <div class="form-group"><label>名称</label><input v-model="sqlForm.name" /></div>
      <div class="form-group">
        <label>方言</label>
        <select v-model="sqlForm.dialect"><option value="sqlite">SQLite</option><option value="postgresql">PostgreSQL</option></select>
      </div>
      <div class="form-group"><label>连接串</label><input v-model="sqlForm.connection_string" /></div>
      <div class="modal-actions">
        <button class="btn btn-outline" @click="showSqlForm=false">取消</button>
        <button class="btn btn-primary" @click="addSql">确认</button>
      </div>
    </div>
  </div>

  <!-- Excel Form Modal -->
  <div v-if="showExcelForm" class="modal-overlay" @click.self="showExcelForm=false">
    <div class="modal">
      <h3>注册 Excel 数据集</h3>
      <p style="font-size:12px;color:#6b7280;margin-bottom:12px">请先将文件放入 data/excel_inbox/ 目录，再注册相对路径。</p>
      <div class="form-group"><label>名称</label><input v-model="excelForm.name" /></div>
      <div class="form-group"><label>文件路径（相对于 data/excel_inbox/）</label><input v-model="excelForm.file_path" placeholder="example.xlsx" /></div>
      <div class="modal-actions">
        <button class="btn btn-outline" @click="showExcelForm=false">取消</button>
        <button class="btn btn-primary" @click="addExcel">确认</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

export default {
  setup() {
    const sqlSources = ref([])
    const excelDatasets = ref([])
    const showSqlForm = ref(false)
    const showExcelForm = ref(false)
    const probeResult = ref('')
    const sqlForm = ref({ name: '', dialect: 'sqlite', connection_string: '' })
    const excelForm = ref({ name: '', file_path: '' })

    async function load() {
      sqlSources.value = await api.getSqlDataSources()
      excelDatasets.value = await api.getExcelDatasets()
    }
    onMounted(load)

    async function addSql() {
      await api.createSqlDataSource(sqlSources.value)
      sqlForm.value = { name: '', dialect: 'sqlite', connection_string: '' }
      showSqlForm.value = false
      await load()
    }
    async function removeSql(id) {
      await api.deleteSqlDataSource(id)
      await load()
    }
    async function probe(s) {
      try {
        const r = await api.probeSqlDataSource(s.id)
        probeResult.value = `表: ${r.tables.join(', ')}`
      } catch(e) {
        probeResult.value = `错误: ${e.message}`
      }
    }
    async function addExcel() {
      await api.createExcelDataset(excelForm.value)
      excelForm.value = { name: '', file_path: '' }
      showExcelForm.value = false
      await load()
    }
    async function removeExcel(id) {
      await api.deleteExcelDataset(id)
      await load()
    }

    return {
      sqlSources, excelDatasets, showSqlForm, showExcelForm,
      sqlForm, excelForm, probeResult,
      addSql, removeSql, probe, addExcel, removeExcel,
    }
  }
}
</script>
