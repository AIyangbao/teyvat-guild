<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listAdventurers } from '../api/adventurer'

const router = useRouter()
const rows = ref([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 12 })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listAdventurers(page)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}
onMounted(load)

// rating 在 JSON 里可能是 "5.00" 字符串，el-rate 要 number，显式转一下
// review_count=0 时的 5.00 是模型默认值，不是真实评分 —— 必须显示「暂无评分」
const hasRating = a => a.review_count > 0
const tagsOf = a => (Array.isArray(a.skill_tags) ? a.skill_tags : [])
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>冒险家名录</h2>
      <span class="sub">按在线状态与历史评分排序</span>
    </div>

    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="a in rows" :key="a.id" :span="8" class="col">
        <el-card shadow="hover" class="card" @click="router.push(`/adventurers/${a.id}`)">
          <div class="name">{{ a.game_nickname }}</div>
          <div class="meta">{{ a.server }} · 完成 {{ a.finished_count }} 单</div>
          <div class="rate">
            <el-rate v-if="hasRating(a)" :model-value="Number(a.rating)" disabled show-score />
            <span v-else class="muted">暂无评分</span>
          </div>
          <div class="tags">
            <el-tag v-for="t in tagsOf(a)" :key="t" size="small" type="info">{{ t }}</el-tag>
            <span v-if="!tagsOf(a).length" class="muted small">暂无技能标签</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-pagination style="margin-top: 16px; justify-content: flex-end"
                   layout="total, prev, pager, next" :total="total"
                   v-model:current-page="page.page" :page-size="page.page_size"
                   @current-change="load" />

    <el-empty v-if="!loading && !total" description="还没有冒险家入驻" />
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
.col {
  margin-bottom: 16px;
}
.card {
  cursor: pointer;
  min-height: 132px;
}
.name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}
.meta {
  color: #606266;
  font-size: 13px;
  margin-bottom: 10px;
}
.rate {
  min-height: 22px;
}
.tags {
  margin-top: 10px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.muted {
  color: #c0c4cc;
  font-size: 13px;
}
.small {
  font-size: 12px;
}
</style>
