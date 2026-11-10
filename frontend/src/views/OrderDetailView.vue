<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getOrder } from '../api/commission'
import PayDialog from '../components/PayDialog.vue'

const route = useRoute()
const detail = ref(null)
const loading = ref(false)
const payVisible = ref(false)

async function load() {
  loading.value = true
  try {
    detail.value = await getOrder(route.params.id)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const fmtTime = s => (s || '—').slice(0, 19).replace('T', ' ')

const statusTag = s => ({
  待支付: 'warning', 待接单: 'primary', 进行中: 'primary',
  已交付: 'success', 已完成: 'success', 已结算: 'success',
  已取消: 'info', 已关闭: 'info',
}[s] || 'info')

const timeline = ref([])
function buildTimeline() {
  if (!detail.value) return []
  return [...detail.value.timeline].reverse()   // 最新在前
}
</script>

<template>
  <div class="page" v-loading="loading">
    <el-page-header @back="$router.back()" :title="'我的委托'"
                    :content="detail?.order_no || ''" style="margin-bottom: 16px" />

    <template v-if="detail">
      <div class="header">
        <h2>
          <el-tag :type="statusTag(detail.status)">{{ detail.status }}</el-tag>
          <span class="amount">¥{{ detail.total_amount }}</span>
        </h2>
        <el-button v-if="detail.status === '待支付'" type="danger"
                   @click="payVisible = true">去支付</el-button>
      </div>

      <el-descriptions :column="2" border style="margin-bottom: 20px">
        <el-descriptions-item label="游戏 UID">{{ detail.game_uid }}</el-descriptions-item>
        <el-descriptions-item label="服务器">{{ detail.server }}</el-descriptions-item>
        <el-descriptions-item label="下单时间">{{ fmtTime(detail.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="支付期限">{{ fmtTime(detail.pay_deadline) }}</el-descriptions-item>
        <el-descriptions-item label="接单期限">{{ fmtTime(detail.accept_deadline) }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ detail.remark || '—' }}</el-descriptions-item>
      </el-descriptions>

      <h3>服务明细</h3>
      <el-table :data="detail.items" size="small" style="margin-bottom: 20px">
        <el-table-column prop="name" label="服务" min-width="160" />
        <el-table-column prop="quantity" label="数量" width="80" />
        <el-table-column label="单价（快照）" width="140">
          <template #default="{ row }">¥{{ row.snapshot_price }}</template>
        </el-table-column>
      </el-table>

      <h3>流转记录</h3>
      <el-timeline style="margin-top: 12px; padding-left: 4px">
        <el-timeline-item v-for="(t, i) in buildTimeline()" :key="i"
                          :timestamp="fmtTime(t.created_at)" placement="top">
          <el-tag size="small" type="info">{{ t.from_status }}</el-tag>
          <span class="arrow">→</span>
          <el-tag size="small" type="success">{{ t.to_status }}</el-tag>
          <span class="event">{{ t.event }}</span>
          <span class="role">（{{ t.operator_role }}）</span>
        </el-timeline-item>
      </el-timeline>
    </template>
  </div>

  <PayDialog v-model="payVisible" :order-id="detail?.id" @paid="load" />
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.amount {
  color: #f56c6c;
  font-size: 24px;
  margin-left: 12px;
}
h2, h3 {
  font-weight: 600;
}
h3 {
  margin: 16px 0 8px;
  color: #606266;
}
.arrow {
  margin: 0 6px;
  color: #909399;
}
.event {
  margin-left: 10px;
  font-weight: 600;
}
.role {
  color: #c0c4cc;
  font-size: 12px;
}
</style>
