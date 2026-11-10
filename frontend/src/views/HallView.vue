<script setup>
import { onMounted, reactive, ref } from 'vue'
import { listHall } from '../api/commission'
import { auth } from '../stores/auth'
import OrderCreateDialog from '../components/OrderCreateDialog.vue'
import PayDialog from '../components/PayDialog.vue'

const hall = ref([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 10 })
const loading = ref(false)

const createVisible = ref(false)
const payVisible = ref(false)
const payingOrderId = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await listHall(page)
    total.value = data.total
    hall.value = data.items
  } finally {
    loading.value = false
  }
}
onMounted(load)

const itemsText = o => o.items.map(i => `${i.name}×${i.qty}`).join('，')
const fmtTime = s => (s || '').slice(0, 19).replace('T', ' ')

function onCreated(order) {
  payingOrderId.value = order.order_id
  payVisible.value = true
  load()
}
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>委托大厅</h2>
      <el-button type="primary" @click="createVisible = true">发起委托</el-button>
    </div>

    <el-table :data="hall" v-loading="loading" @row-click="r => $router.push(`/orders/${r.id}`)"
              style="cursor: pointer">
      <el-table-column prop="order_no" label="委托单号" width="220" />
      <el-table-column label="内容" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ itemsText(row) }}</template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">¥{{ row.total_amount }}</template>
      </el-table-column>
      <el-table-column label="备注" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || '—' }}</template>
      </el-table-column>
      <el-table-column label="发布时间" width="165">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top: 16px; justify-content: flex-end"
                   layout="total, prev, pager, next" :total="total"
                   v-model:current-page="page.page" :page-size="page.page_size"
                   @current-change="load" />

    <el-empty v-if="!loading && !total" description="大厅空空如也，发个委托试试" />

    <p v-if="!auth.token" class="hint">
      游客模式：浏览无需登录，
      <router-link to="/login">登录</router-link> 后可下单
    </p>
  </div>

  <OrderCreateDialog v-model="createVisible" @created="onCreated" />
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
.hint {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin-top: 12px;
}
</style>
