<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register } from '../api/auth'
import { auth } from '../stores/auth'

const router = useRouter()
const mode = ref('login')          // login | register
const form = reactive({ phone: '', password: '', nickname: '' })
const loading = ref(false)

const rules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1\d{10}$/, message: '手机号格式：1 开头 11 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码 8-64 位', trigger: 'blur' },
  ],
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 50, message: '昵称最长 50 字', trigger: 'blur' },
  ],
}
const formRef = ref()

async function submit() {
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  loading.value = true
  try {
    const data = mode.value === 'login'
      ? await login({ phone: form.phone, password: form.password })
      : await register({ phone: form.phone, password: form.password, nickname: form.nickname })
    auth.setLogin(data)
    ElMessage.success(`欢迎回来，${data.nickname}`)
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2>{{ mode === 'login' ? '登录' : '注册冒险者账号' }}</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="1 开头 11 位" maxlength="11" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="昵称" prop="nickname">
          <el-input v-model="form.nickname" maxlength="50" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password
                    placeholder="8-64 位" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
        <div class="switch">
          <el-link type="primary" :underline="false" @click="mode = mode === 'login' ? 'register' : 'login'">
            {{ mode === 'login' ? '没有账号？注册一个' : '已有账号？去登录' }}
          </el-link>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}
.login-card {
  width: 380px;
}
h2 {
  margin-bottom: 20px;
  text-align: center;
  font-weight: 600;
}
.switch {
  text-align: center;
  margin-top: 12px;
}
</style>
