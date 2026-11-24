<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listPendingAdventurers, auditAdventurer } from '../api/admin'

const rows = ref([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })
const loading = ref(false)
const actingId = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await listPendingAdventurers(page)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}
onMounted(load)

const tagsOf = a => (Array.isArray(a.skill_tags) ? a.skill_tags : [])

async function decide(row, target) {
  const label = target === 'approved' ? '通过' : '拒绝'
  try {
    await ElMessageBox.confirm(
      `确认${label}「${row.game_nickname}」的申请？${target === 'rejected' ? '拒绝后不可撤销。' : ''}`,
      `${label}审核`, { type: 'warning' },
    )
  } catch {
    return   // 用户点取消，不做事
  }
  actingId.value = row.id
  try {
    await auditAdventurer(row.id, target)
    ElMessage.success(`已${label}「${row.game_nickname}」`)
    await load()   // 审核后该行离开待审队列，重新拉一次
  } finally {
    actingId.value = null
  }
  // 失败弹窗由 request.js 拦截器统一处理，这里不重复弹
}
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>冒险家审核</h2>
      <span class="sub">待审 {{ total }} 人 · 通过后才能接单</span>
    </div>

    <el-table :data="rows" v-loading="loading" border style="width: 100%">
      <el-table-column prop="game_nickname" label="游戏昵称" min-width="130" />
      <el-table-column prop="game_uid" label="游戏 UID" min-width="140" />
      <el-table-column prop="server" label="服务器" width="110" />
      <el-table-column label="技能标签" min-width="150">
        <template #default="{ row }">
          <el-tag v-for="t in tagsOf(row)" :key="t" size="small" type="info"
                  style="margin-right: 4px">{{ t }}</el-tag>
          <span v-if="!tagsOf(row).length" class="muted">无</span>
        </template>
      </el-table-column>
      <el-table-column label="申请时间" min-width="170">
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button type="success" size="small" :loading="actingId === row.id"
                     @click="decide(row, 'approved')">通过</el-button>
          <el-button type="danger" size="small" :loading="actingId === row.id"
                     @click="decide(row, 'rejected')">拒绝</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top: 16px; justify-content: flex-end"
                   layout="total, prev, pager, next" :total="total"
                   v-model:current-page="page.page" :page-size="page.page_size"
                   @current-change="load" />

    <el-empty v-if="!loading && !total" description="暂无待审申请" />
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
h2 {
  font-weight: 600;
}
.sub {
  color: #909399;
  font-size: 13px;
}
.muted {
  color: #c0c4cc;
  font-size: 13px;
}
</style>
