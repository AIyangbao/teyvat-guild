<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { payOrder } from '../api/commission'
import { mockCallback } from '../api/payment'

// 模拟收银台：发起支付拿 out_trade_no，再点按钮模拟第三方回调。
// 真实环境回调来自支付服务商服务器，前端只做轮询订单状态。
const props = defineProps({ modelValue: Boolean, orderId: Number })
const emit = defineEmits(['update:modelValue', 'paid'])

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const payInfo = ref(null)   // { out_trade_no, amount, channel }
const loading = ref(false)
const paying = ref(false)

watch(visible, async v => {
  payInfo.value = null
  if (v && props.orderId) {
    loading.value = true
    try {
      payInfo.value = await payOrder(props.orderId)
    } finally {
      loading.value = false
    }
  }
})

async function doPay() {
  paying.value = true
  try {
    const r = await mockCallback(payInfo.value.out_trade_no, payInfo.value.amount)
    if (r.first_time) {
      ElMessage.success('支付成功，委托已进入大厅等待冒险者接单')
    } else {
      ElMessage.info('该支付单已处理过（幂等生效），无需重复支付')
    }
    emit('paid')
    visible.value = false
  } finally {
    paying.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="支付" width="400px">
    <div v-loading="loading">
      <template v-if="payInfo">
        <div class="amount">¥{{ payInfo.amount }}</div>
        <div class="meta">
          <div>支付单号：{{ payInfo.out_trade_no }}</div>
          <div>渠道：{{ payInfo.channel === 'mock' ? '模拟收银台' : payInfo.channel }}</div>
        </div>
        <el-alert type="info" :closable="false" show-icon
                  title="模拟环境：点击下方按钮即触发第三方回调（真实场景由支付服务商发起）" />
        <el-button type="primary" :loading="paying" style="width: 100%; margin-top: 16px"
                   @click="doPay">
          确认支付
        </el-button>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.amount {
  font-size: 34px;
  font-weight: 700;
  color: #f56c6c;
  text-align: center;
  margin-bottom: 12px;
}
.meta {
  color: #909399;
  font-size: 13px;
  line-height: 22px;
  margin-bottom: 16px;
  word-break: break-all;
}
</style>
