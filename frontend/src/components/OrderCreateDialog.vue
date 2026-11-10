<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listCategories, listItems } from '../api/catalog'
import { createOrder } from '../api/commission'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const categories = ref([])
const items = ref([])
const form = reactive({ game_uid: '', server: '天空岛', remark: '' })
const loading = ref(false)

// 数量表：{ [service_item_id]: 数量 }
const qtyMap = reactive({})

async function loadCatalog() {
  const [cats, its] = await Promise.all([
    listCategories(),
    listItems({ status: 1 }),
  ])
  categories.value = cats.filter(c => c.status === 1)
  // 只展示上架且有有效分类的商品
  const validCatIds = new Set(categories.value.map(c => c.id))
  items.value = its.filter(i => i.status === 1 && validCatIds.has(i.category_id))
}

watch(visible, v => { if (v) loadCatalog() })

const selected = computed(() =>
  items.value.filter(i => (qtyMap[i.id] || 0) > 0)
    .map(i => ({ ...i, qty: qtyMap[i.id] })))

const total = computed(() =>
  selected.value.reduce((s, i) => s + Number(i.price) * i.qty, 0).toFixed(2))

const catName = id => categories.value.find(c => c.id === id)?.name || '-'

async function submit() {
  if (!selected.value.length) return ElMessage.warning('先选服务项目')
  if (!/^1\d{10}$|^9\d{8}$/.test(form.game_uid)) return ElMessage.warning('游戏 UID 格式不对')
  loading.value = true
  try {
    const order = await createOrder({
      items: selected.value.map(i => ({ service_item_id: i.id, qty: i.qty })),
      game_uid: form.game_uid,
      server: form.server,
      remark: form.remark,
    })
    ElMessage.success(`委托已创建，应付 ${order.total_amount}`)
    emit('created', order)
    visible.value = false
    Object.keys(qtyMap).forEach(k => delete qtyMap[k])
    form.game_uid = ''
    form.remark = ''
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="发起委托" width="680px" top="6vh">
    <el-table :data="items" size="small" max-height="320">
      <el-table-column label="分类" width="90">
        <template #default="{ row }">{{ catName(row.category_id) }}</template>
      </el-table-column>
      <el-table-column prop="name" label="服务" min-width="140" show-overflow-tooltip />
      <el-table-column label="价格" width="90">
        <template #default="{ row }">¥{{ row.price }}</template>
      </el-table-column>
      <el-table-column label="数量" width="130">
        <template #default="{ row }">
          <el-input-number v-model="qtyMap[row.id]" :min="0" :max="10" size="small" />
        </template>
      </el-table-column>
    </el-table>

    <el-form label-width="90px" style="margin-top: 16px">
      <el-form-item label="游戏 UID">
        <el-input v-model="form.game_uid" placeholder="9 开头 9 位" style="width: 200px" />
      </el-form-item>
      <el-form-item label="服务器">
        <el-select v-model="form.server" style="width: 200px">
          <el-option value="天空岛" />
          <el-option value="世界树" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" maxlength="255" show-word-limit />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="total">共 {{ selected.length }} 项 · 合计 ¥{{ total }}</span>
      <el-button :loading="loading" type="primary" @click="submit">提交委托</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.total {
  margin-right: 16px;
  color: #f56c6c;
  font-weight: 600;
}
</style>
