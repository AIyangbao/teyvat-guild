<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAccepted, deliverOrder } from '../api/commission'

// 与后端 app/core/state_machine.py 的 ALL_STATES 逐字对齐。
// list_by_adventurer 会拿这个值校验，写错（比如旧页面里的「已交付」）直接 400
const STATUS = ['待支付', '待接单', '进行中', '待验收', '已完成',
                '已结算', '已取消', '已关闭', '争议中']

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ status: '', page: 1, page_size: 10 })
const deliveringId = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await listAccepted({
      page: query.page, page_size: query.page_size,
      status: query.status || undefined,
    })
    total.value = data.total
    rows.value = data.items
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function doDeliver(row) {
  deliveringId.value = row.id
  try {
    await deliverOrder(row.id)
    ElMessage.success('已提交交付，等待玩家验收')
    await load()
  } catch (e) {
    // request.js 已统一弹错；409 说明状态被别处推进过，刷新拿最新状态即可
    if (e.response?.status === 409) await load()
  } finally {
    deliveringId.value = null
  }
}

const itemsText = o => o.items.map(i => `${i.name}×${i.quantity}`).join('，')
const fmtTime = s => (s || '').slice(0, 19).replace('T', ' ')
const statusTag = s => ({
  待支付: 'warning', 待接单: 'primary', 进行中: 'primary',
  待验收: 'warning', 已完成: 'success', 已结算: 'success',
  已取消: 'info', 已关闭: 'info', 争议中: 'danger',
}[s] || 'info')
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>我的接单</h2>
      <el-select v-model="query.status" clearable placeholder="全部状态"
                 style="width: 140px" @change="() => { query.page = 1; load() }">
        <el-option v-for="s in STATUS" :key="s" :label="s" :value="s" />
      </el-select>
    </div>

    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px"
              title="流程：接单 → 进行中 → 提交交付 → 待验收 → 玩家确认 → 已完成（满 7 天自动结算）" />

    <el-table :data="rows" v-loading="loading" @row-click="r => $router.push(`/orders/${r.id}`)"
              style="cursor: pointer">
      <el-table-column prop="order_no" label="委托单号" width="220" />
      <el-table-column label="内容" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ itemsText(row) }}</template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">¥{{ row.total_amount }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="下单时间" width="165">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110">
        <template #default="{ row }">
          <el-button v-if="row.status === '进行中'" size="small" type="primary"
                     :loading="deliveringId === row.id"
                     @click.stop="doDeliver(row)">提交交付</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top: 16px; justify-content: flex-end"
                   layout="total, prev, pager, next" :total="total"
                   v-model:current-page="query.page" :page-size="query.page_size"
                   @current-change="load" />

    <el-empty v-if="!loading && !total" description="还没有接单，去大厅看看" />
  </div>
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
h2 {
  font-weight: 600;
}
</style>
