<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getAdventurer, listAdventurerReviews } from '../api/adventurer'

const route = useRoute()
const profile = ref(null)
const reviews = ref([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 10 })
const loading = ref(false)
const reviewLoading = ref(false)

async function loadProfile() {
  loading.value = true
  try {
    profile.value = await getAdventurer(route.params.id)
  } finally {
    loading.value = false
  }
}

async function loadReviews() {
  reviewLoading.value = true
  try {
    const data = await listAdventurerReviews(route.params.id, page)
    reviews.value = data.items
    total.value = data.total
  } finally {
    reviewLoading.value = false
  }
}

// 两个接口互不依赖：分开加载，档案先出来，评价表格随后填充
onMounted(() => {
  loadProfile()
  loadReviews()
})

const fmtTime = s => (s || '').slice(0, 19).replace('T', ' ')
</script>

<template>
  <div class="page" v-loading="loading">
    <el-page-header @back="$router.back()" title="冒险家档案"
                    :content="profile?.game_nickname || ''" style="margin-bottom: 16px" />

    <template v-if="profile">
      <el-descriptions :column="3" border style="margin-bottom: 24px">
        <el-descriptions-item label="游戏昵称">{{ profile.game_nickname }}</el-descriptions-item>
        <el-descriptions-item label="服务器">{{ profile.server }}</el-descriptions-item>
        <el-descriptions-item label="完成委托">{{ profile.finished_count }} 单</el-descriptions-item>
        <el-descriptions-item label="历史评分">
          <el-rate v-if="profile.review_count > 0"
                   :model-value="Number(profile.rating)" disabled show-score />
          <span v-else class="muted">暂无评分</span>
        </el-descriptions-item>
        <el-descriptions-item label="评价数">{{ profile.review_count }} 条</el-descriptions-item>
        <el-descriptions-item label="技能标签">
          <template v-if="profile.skill_tags?.length">
            <el-tag v-for="t in profile.skill_tags" :key="t" size="small" type="info"
                    style="margin-right: 4px">{{ t }}</el-tag>
          </template>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
      </el-descriptions>

      <h3>收到的评价（{{ total }}）</h3>
      <el-table :data="reviews" v-loading="reviewLoading" size="small" style="margin-top: 12px">
        <el-table-column label="评分" width="130">
          <template #default="{ row }">
            <el-rate :model-value="row.score" disabled />
          </template>
        </el-table-column>
        <el-table-column prop="order_no" label="委托单号" width="220" />
        <el-table-column prop="content" label="评价内容" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ row.content || '（未填写）' }}</template>
        </el-table-column>
        <el-table-column label="评价时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <el-pagination style="margin-top: 16px; justify-content: flex-end"
                     layout="total, prev, pager, next" :total="total"
                     v-model:current-page="page.page" :page-size="page.page_size"
                     @current-change="loadReviews" />
    </template>
  </div>
</template>

<style scoped>
h3 {
  font-weight: 600;
  color: #606266;
}
.muted {
  color: #c0c4cc;
  font-size: 13px;
}
</style>
