<script setup>
import { computed, onMounted, ref } from 'vue'
import { getStatsOverview } from '../api/admin'

const days = ref(7)
const data = ref(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await getStatsOverview(days.value)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// 金额：后端传 Decimal 序列化后的字符串，转成两位小数再显示
const money = v => `¥${Number(v || 0).toFixed(2)}`
const int = v => Number(v || 0).toLocaleString()

// ---- SVG 折线几何：纯计算，不依赖图表库 ----
const W = 720, H = 220, PAD = { l: 52, r: 16, t: 16, b: 28 }
const innerW = computed(() => W - PAD.l - PAD.r)
const innerH = computed(() => H - PAD.t - PAD.b)

const maxAmount = computed(() => {
  const vals = (data.value?.trend || []).map(t => Number(t.amount))
  return Math.max(1, ...vals)   // 全 0 时用 1 当尺子，避免除零
})
// x 等距铺满；y 按金额比例映射到画布（顶部留白 PAD.t）
const points = computed(() => (data.value?.trend || []).map((t, i, arr) => ({
  ...t,
  x: PAD.l + (arr.length === 1 ? innerW.value / 2 : innerW.value * i / (arr.length - 1)),
  y: PAD.t + innerH.value * (1 - Number(t.amount) / maxAmount.value),
})))
const linePath = computed(() =>
  points.value.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))
const areaPath = computed(() => {
  const ps = points.value
  if (!ps.length) return ''
  const base = PAD.t + innerH.value
  return `${linePath.value} L${ps[ps.length - 1].x.toFixed(1)},${base} L${ps[0].x.toFixed(1)},${base} Z`
})
// Y 轴 4 条刻度线（0 / 1/3 / 2/3 / max）
const gridLines = computed(() => [0, 1, 2, 3].map(i => ({
  y: PAD.t + innerH.value * i / 3,
  label: money(maxAmount.value * (3 - i) / 3),
})))

// 状态分布 / 服务器分布：算占比给 CSS 横条用
const maxStatus = computed(() =>
  Math.max(1, ...(data.value?.status_breakdown || []).map(s => s.count)))
const maxServer = computed(() =>
  Math.max(1, ...(data.value?.server_breakdown || []).map(s => s.count)))
const totalOrders = computed(() => data.value?.total_orders || 1)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="board-head">
      <div>
        <h2>经营数据看板</h2>
        <p class="sub">营业额按支付成功口径统计，趋势按支付日期归档</p>
      </div>
      <div class="days-switch">
        <el-button v-for="n in [7, 30, 90]" :key="n" size="small"
                   :type="days === n ? 'primary' : 'default'"
                   @click="days = n; load()">{{ n }} 天</el-button>
      </div>
    </div>

    <template v-if="data">
      <!-- 4 个 KPI -->
      <div class="kpi-grid">
        <div class="kpi">
          <div class="kpi-label">累计营业额</div>
          <div class="kpi-value revenue">{{ money(data.total_revenue) }}</div>
          <div class="kpi-foot">{{ int(data.paid_orders) }} 笔成功支付</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">委托总量</div>
          <div class="kpi-value">{{ int(data.total_orders) }}</div>
          <div class="kpi-foot">含未支付 / 已取消</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">支付转化率</div>
          <div class="kpi-value">{{ (data.total_orders ? (data.paid_orders / data.total_orders * 100).toFixed(1) : 0) }}%</div>
          <div class="kpi-foot">成功支付 / 全部委托</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">全站平均评分</div>
          <div class="kpi-value">{{ data.avg_rating == null ? '—' : Number(data.avg_rating).toFixed(2) }}</div>
          <div class="kpi-foot">{{ data.avg_rating == null ? '暂无评价' : '基于全部评价' }}</div>
        </div>
      </div>

      <!-- 趋势折线（SVG 手绘） -->
      <div class="panel">
        <div class="panel-title">近 {{ days }} 天收款趋势</div>
        <svg class="trend" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none">
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#409eff" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#409eff" stop-opacity="0" />
            </linearGradient>
          </defs>
          <!-- 网格 + Y 轴刻度 -->
          <g v-for="(g, i) in gridLines" :key="i">
            <line :x1="PAD.l" :x2="W - PAD.r" :y1="g.y" :y2="g.y"
                  stroke="#ebeef5" stroke-width="1" />
            <text :x="PAD.l - 8" :y="g.y + 4" text-anchor="end"
                  fill="#909399" font-size="11">{{ g.label }}</text>
          </g>
          <!-- 面积 + 折线 -->
          <path v-if="areaPath" :d="areaPath" fill="url(#areaGrad)" />
          <path v-if="linePath" :d="linePath" fill="none" stroke="#409eff" stroke-width="2" />
          <!-- 数据点 + X 轴标签（每隔几个显示，防挤） -->
          <g v-for="(p, i) in points" :key="p.date">
            <circle :cx="p.x" :cy="p.y" r="3.5" fill="#fff" stroke="#409eff" stroke-width="2">
              <title>{{ p.date }} · {{ money(p.amount) }} · {{ p.orders }} 笔</title>
            </circle>
            <text v-if="points.length <= 10 || i % Math.ceil(points.length / 8) === 0"
                  :x="p.x" :y="H - 8" text-anchor="middle"
                  fill="#909399" font-size="10">{{ p.date.slice(5) }}</text>
          </g>
        </svg>
        <div v-if="!points.some(p => Number(p.amount) > 0)" class="empty-hint">
          所选区间暂无成功支付记录
        </div>
      </div>

      <!-- 两个分布面板 -->
      <div class="two-col">
        <div class="panel">
          <div class="panel-title">订单状态分布</div>
          <div v-for="s in data.status_breakdown" :key="s.name" class="bar-row">
            <span class="bar-label">{{ s.name }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: (s.count / maxStatus * 100) + '%' }" />
            </div>
            <span class="bar-value">{{ s.count }}</span>
          </div>
          <div v-if="!data.status_breakdown.length" class="empty-hint">暂无订单</div>
        </div>
        <div class="panel">
          <div class="panel-title">服务器分布</div>
          <div v-for="s in data.server_breakdown" :key="s.name" class="bar-row">
            <span class="bar-label">{{ s.name }}</span>
            <div class="bar-track">
              <div class="bar-fill alt" :style="{ width: (s.count / maxServer * 100) + '%' }" />
            </div>
            <span class="bar-value">{{ s.count }} · {{ money(s.amount) }}</span>
          </div>
          <div v-if="!data.server_breakdown.length" class="empty-hint">暂无订单</div>
        </div>
      </div>

      <!-- Top 冒险家 -->
      <div class="panel">
        <div class="panel-title">完成数 Top 5</div>
        <el-table :data="data.top_adventurers" size="small">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="game_nickname" label="冒险家" min-width="140" />
          <el-table-column prop="finished_count" label="完成单数" width="100" />
          <el-table-column label="评分" width="120">
            <template #default="{ row }">
              <span v-if="row.review_count > 0">{{ Number(row.rating).toFixed(2) }} ({{ row.review_count }})</span>
              <span v-else class="muted">暂无评分</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!data.top_adventurers.length" class="empty-hint">暂无冒险家</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.board-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.board-head h2 { margin: 0; font-weight: 600; }
.sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.days-switch { display: flex; gap: 6px; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: #fff; border: 1px solid #e4e7ed; border-radius: 10px; padding: 18px; }
.kpi-label { color: #909399; font-size: 13px; }
.kpi-value { font-size: 28px; font-weight: 700; margin: 8px 0 4px; }
.kpi-value.revenue { color: #f56c6c; }
.kpi-foot { color: #c0c4cc; font-size: 12px; }
.panel { background: #fff; border: 1px solid #e4e7ed; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.panel-title { font-weight: 600; color: #303133; margin-bottom: 12px; }
.trend { width: 100%; height: 240px; display: block; }
.empty-hint { text-align: center; color: #c0c4cc; font-size: 13px; padding: 12px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.bar-label { width: 70px; flex-shrink: 0; color: #606266; font-size: 13px; }
.bar-track { flex: 1; height: 12px; background: #f5f7fa; border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg, #409eff, #79bbff); border-radius: 6px; transition: width .3s; }
.bar-fill.alt { background: linear-gradient(90deg, #67c23a, #95d475); }
.bar-value { width: 110px; text-align: right; color: #606266; font-size: 12px; flex-shrink: 0; }
.muted { color: #c0c4cc; }
</style>
