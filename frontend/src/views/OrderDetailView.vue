<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getOrder, createReview, confirmOrder, deliverOrder } from '../api/commission'
import PayDialog from '../components/PayDialog.vue'
import { ElMessage } from 'element-plus'
import { auth } from '../stores/auth'

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
const reviewVisible = ref(false)
const reviewForm = reactive({ score: 5, content: '' })
const submitting = ref(false)
const reviewed = ref(false)
const newRating = ref(null)

// 三个条件同时满足才显示按钮：状态对 + 是本单玩家 + 本地未评价过
const canReview = computed(() =>
  detail.value &&
  ['已完成', '已结算'].includes(detail.value.status) &&
  auth.user?.id === detail.value.player_id &&
  !reviewed.value
)

// 前端只能判断「角色 + 状态」：auth.user.id 是 User.id，而 detail.adventurer_id
// 是 Adventurer.id（FK adventurer.id），两者不同源，前端拿不到自己的档案 id，
// 因此无法校验「本人」。真归属校验在后端 deliver_by_adventurer（不符 → 403），
// 与项目既有「前端体验层 / 后端真闸门」约定一致；403 由 request.js 统一弹。
const canDeliver = computed(() =>
  detail.value && detail.value.status === '进行中' &&
  auth.user?.role === 'adventurer' &&
  detail.value.adventurer_id != null
)
const delivering = ref(false)

async function submitDeliver() {
  delivering.value = true
  try {
    await deliverOrder(detail.value.id)
    ElMessage.success('已提交交付，等待玩家验收')
    await load()
  } catch (e) {
    // request.js 已统一弹错；409 = 状态被别处推进过，刷新拿最新状态即可
    if (e.response?.status === 409) await load()
  } finally {
    delivering.value = false
  }
}

// 冒险家「提交交付」后状态变为「待验收」，只有本单玩家能确认推进到「已完成」
const canConfirm = computed(() =>
  detail.value && detail.value.status === '待验收' &&
  auth.user?.id === detail.value.player_id
)
const confirming = ref(false)

async function submitConfirm() {
  confirming.value = true
  try {
    await confirmOrder(detail.value.id)
    ElMessage.success('已确认验收，现在可以评价了')
    await load()
  } catch (e) {
    // 409 = 状态已被超时扫描/别处推进过，刷新拿最新状态
    if (e.response?.status === 409) await load()
  } finally {
    confirming.value = false
  }
}

async function submitReview() {
  submitting.value = true
  try {
    const res = await createReview(detail.value.id, {
      score: reviewForm.score, content: reviewForm.content,
    })
    ElMessage.success('评价成功')
    reviewed.value = true
    newRating.value = res.adventurer_rating
    reviewVisible.value = false
  } catch (e) {
    // request.js 拦截器已统一弹错，这里只收 UI 状态、不重复弹
    if (e.response?.status === 409) reviewed.value = true
  } finally {
    submitting.value = false
  }
}
const fmtTime = s => (s || '—').slice(0, 19).replace('T', ' ')

const statusTag = s => ({
  待支付: 'warning', 待接单: 'primary', 进行中: 'primary',
  待验收: 'warning', 已完成: 'success', 已结算: 'success',
  已取消: 'info', 已关闭: 'info', 争议中: 'danger',
}[s] || 'info')

const timeline = ref([])
function buildTimeline() {
  if (!detail.value) return []
  return [...detail.value.timeline].reverse()   // 最新在前
}
</script>

<template>
  <div class="page" v-loading="loading">
    <el-page-header @back="$router.back()" title="委托详情"
                    :content="detail?.order_no || ''" style="margin-bottom: 16px" />

    <template v-if="detail">
      <div class="header">
        <h2>
          <el-tag :type="statusTag(detail.status)">{{ detail.status }}</el-tag>
          <span class="amount">¥{{ detail.total_amount }}</span>
        </h2>
        <el-button v-if="detail.status === '待支付'" type="danger"
                   @click="payVisible = true">去支付</el-button>
        <el-button v-if="canDeliver" type="primary" :loading="delivering"
                   @click="submitDeliver">提交交付</el-button>
        <el-button v-if="canConfirm" type="primary" :loading="confirming"
                   @click="submitConfirm">确认验收</el-button>
        <el-button v-if="canReview" type="primary"
                   @click="reviewVisible = true">评价</el-button>
        <el-tag v-if="reviewed" type="success" style="margin-left:8px">
          已评价 · 冒险家评分 {{ newRating }}
        </el-tag>
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

  <el-dialog v-model="reviewVisible" title="评价本次委托" width="440px">
    <el-form label-width="76px">
      <el-form-item label="评分">
        <el-rate v-model="reviewForm.score" :max="5" />
      </el-form-item>
      <el-form-item label="评价内容">
        <el-input v-model="reviewForm.content" type="textarea" :rows="4"
                  maxlength="500" show-word-limit
                  placeholder="说说这次委托的体验（选填）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting"
                 @click="submitReview">提交评价</el-button>
    </template>
  </el-dialog>
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
