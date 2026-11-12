<script setup>
import { onMounted, reactive, ref } from 'vue'
import { listMine } from '../api/commission'
import PayDialog from '../components/PayDialog.vue'

// 后端状态机 9 态，玩家视角常用的筛选项
const STATUS = ['待支付', '待接单', '进行中', '已交付', '已完成', '已结算', '已取消', '已关闭']

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ status: '', page: 1, page_size: 10 })

const payVisible = ref(false)
const payingOrderId = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await listMine({
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

const itemsText = o => o.items.map(i => `${i.name}×${i.quantity}`).join('，')
const fmtTime = s => (s || '').slice(0, 19).replace('T', ' ')

const statusTag = s => ({
  待支付: 'warning', 待接单: 'primary', 进行中: 'primary',
  已交付: 'success', 已完成: 'success', 已结算: 'success',
  已取消: 'info', 已关闭: 'info',
}[s] || 'info')

function goPay(orderId) {
  payingOrderId.value = orderId
  payVisible.value = true
}
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>我的委托</h2>
      <el-select v-model="query.status" clearable placeholder="全部状态"
                 style="width: 140px" @change="() => { query.page = 1; load() }">
        <el-option v-for="s in STATUS" :key="s" :label="s" :value="s" />
      </el-select>
    </div>

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
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button v-if="row.status === '待支付'" size="small" type="danger"
                     @click.stop="goPay(row.id)">去支付</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top: 16px; justify-content: flex-end"
                   layout="total, prev, pager, next" :total="total"
                   v-model:current-page="query.page" :page-size="query.page_size"
                   @current-change="load" />

    <el-empty v-if="!loading && !total" description="还没有委托，去大厅发一个" />
  </div>

  <PayDialog v-model="payVisible" :order-id="payingOrderId" @paid="load" />
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
