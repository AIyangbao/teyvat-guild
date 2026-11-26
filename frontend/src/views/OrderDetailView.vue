<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getOrder, getOrderReview, createReview, confirmOrder, deliverOrder, getRecommendations } from '../api/commission'
import PayDialog from '../components/PayDialog.vue'
import { ElMessage } from 'element-plus'
import { auth } from '../stores/auth'

const route = useRoute()
const detail = ref(null)
const myReview = ref(null)   // 后端读回来的评价；刷新页面靠它恢复「已评价」状态
const reviewed = ref(false)  // 由 myReview 派生：有评价就是已评价
const recommendations = ref([])
const loading = ref(false)
const payVisible = ref(false)

// 推荐分拆解的中文标签和颜色，纯展示映射。顺序即展示顺序。
const REASON_LABELS = {
  same_server: { label: '同服', type: 'success' },
  online: { label: '在线', type: 'success' },
  rating: { label: '评分', type: 'warning' },
  experience: { label: '经验', type: 'warning' },
  load: { label: '负载', type: 'danger' },
}

// 只展示非 0 的拆解项：0 分项是噪音，让它占了卡片反而看不清加分来源
const nonZeroReasons = r =>
  Object.entries(REASON_LABELS)
    .filter(([key]) => r.reasons[key] !== 0)
    .map(([key, meta]) => ({
      ...meta,
      // 负载是负分，其余是正分；+/- 号让「为什么是这个总分」一眼可对账
      text: `${meta.label} ${r.reasons[key] > 0 ? '+' : ''}${r.reasons[key]}`,
    }))

async function load() {
  loading.value = true
  try {
    // 三个请求互不依赖，并行发。评价不存在返回 200 + null；推荐是增强信息，
    // 它挂了不该拖垮详情页，所以单独 catch 吞掉并给空列表。
    const [d, r, recs] = await Promise.all([
      getOrder(route.params.id),
      getOrderReview(route.params.id),
      getRecommendations(route.params.id).catch(() => []),
    ])
    detail.value = d
    myReview.value = r
    reviewed.value = !!r
    recommendations.value = recs
  } finally {
    loading.value = false
  }
}
onMounted(load)
const reviewVisible = ref(false)
const reviewForm = reactive({ score: 5, content: '' })
const submitting = ref(false)

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
    await createReview(detail.value.id, {
      score: reviewForm.score, content: reviewForm.content,
    })
    ElMessage.success('评价成功')
    reviewVisible.value = false
    // 写完立刻回读：状态以服务端为准，不在前端手工拼 newRating / reviewed
    await load()
  } catch (e) {
    // request.js 拦截器已统一弹错，这里只收 UI 状态、不重复弹
    // 409 = 已经评价过（并发提交/别处已提交），回读拿真实评价内容
    if (e.response?.status === 409) await load()
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

// 纯展示派生数据用 computed：detail 变化时自动重算，不需要手动维护一份 ref
const timeline = computed(() =>
  detail.value ? [...detail.value.timeline].reverse() : []   // 最新在前
)
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
          已评价 · {{ myReview?.score }} 星
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

      <!-- 派单推荐：只在待接单时有意义。已接单后再列候选人只会误导 -->
      <template v-if="detail.status === '待接单'">
        <div class="rec-header">
          <h3>推荐冒险家</h3>
          <span class="rec-hint">按同服 / 在线 / 真实评分 / 经验 / 负载综合排序，点昵称看档案</span>
        </div>
        <div v-if="recommendations.length" class="rec-grid">
          <el-card v-for="r in recommendations" :key="r.adventurer_id"
                   shadow="hover" class="rec-card">
            <div class="rec-top">
              <router-link :to="`/adventurers/${r.adventurer_id}`" class="rec-name">
                {{ r.game_nickname }}
              </router-link>
              <span class="rec-score">推荐分 {{ r.score }}</span>
            </div>
            <div class="rec-facts">
              <el-tag size="small" :type="r.same_server ? 'success' : 'info'">
                {{ r.same_server ? '同服' : r.server }}
              </el-tag>
              <el-tag size="small" :type="r.online_status === 'online' ? 'success' : 'info'">
                {{ r.online_status === 'online' ? '在线' : '离线' }}
              </el-tag>
              <span class="rec-metric">
                评分 <el-rate v-if="r.review_count > 0" :model-value="Number(r.rating)"
                             disabled size="small" />
                <span v-else class="rec-na">暂无评分</span>
              </span>
            </div>
            <div class="rec-counts">
              完成 {{ r.finished_count }} 单 · 在途 {{ r.active_count }} 单
            </div>
            <div class="rec-reasons">
              <el-tag v-for="(part, i) in nonZeroReasons(r)" :key="i"
                      size="small" :type="part.type" effect="plain">
                {{ part.text }}
              </el-tag>
            </div>
          </el-card>
        </div>
        <el-empty v-else description="暂无符合条件的冒险家" :image-size="60" />
      </template>

      <!-- 读侧拉回的评价：刷新页面、换浏览器、靠链接分享都能看到，不依赖本地状态 -->
      <template v-if="myReview">
        <h3>本次委托评价</h3>
        <el-descriptions :column="1" border style="margin-bottom: 20px">
          <el-descriptions-item label="评分">
            <el-rate :model-value="myReview.score" disabled />
          </el-descriptions-item>
          <el-descriptions-item label="内容">{{ myReview.content || '（未填写）' }}</el-descriptions-item>
          <el-descriptions-item label="评价时间">{{ fmtTime(myReview.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </template>

      <h3>流转记录</h3>
      <el-timeline style="margin-top: 12px; padding-left: 4px">
        <el-timeline-item v-for="(t, i) in timeline" :key="i"
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

.rec-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.rec-hint {
  color: #909399;
  font-size: 12px;
}
.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 8px;
  margin-bottom: 20px;
}
.rec-card {
  border-radius: 8px;
}
.rec-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.rec-name {
  font-weight: 600;
  font-size: 15px;
  color: #409eff;
  text-decoration: none;
}
.rec-name:hover { text-decoration: underline; }
.rec-score {
  color: #f56c6c;
  font-weight: 600;
}
.rec-facts {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.rec-metric {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #606266;
}
.rec-na {
  color: #c0c4cc;
}
.rec-counts {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}
.rec-reasons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}
</style>
