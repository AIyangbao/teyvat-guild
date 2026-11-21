<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register } from '../api/auth'
import { auth } from '../stores/auth'

const router = useRouter()
const mode = ref('login')          // login | register
const form = reactive({
  phone: '', password: '', nickname: '',
  role: 'player',                 // 与后端 RegisterIn 默认值一致
  game_uid: '', server: '', game_nickname: '',
})
const loading = ref(false)

// 只在「注册 + 冒险家」时必填；每次 validate() 都执行，能读到最新 role
const requiredForAdventurer = (rule, value, callback) => {
  if (mode.value === 'register' && form.role === 'adventurer' && !value?.trim()) {
    callback(new Error(rule.message))
  } else {
    callback()
  }
}

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
  game_uid:      [{ validator: requiredForAdventurer, message: '请输入游戏 UID', trigger: 'blur' }],
  server:        [{ validator: requiredForAdventurer, message: '请填写服务器', trigger: 'blur' }],
  game_nickname: [{ validator: requiredForAdventurer, message: '请填写游戏昵称', trigger: 'blur' }],
}
const formRef = ref()

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  formRef.value?.clearValidate()      // 切模式丢掉上一个模式的红字
}
function onRoleChange() {
  // 冒险家→玩家时，三件套已标红的错要清掉
  formRef.value?.clearValidate(['game_uid', 'server', 'game_nickname'])
}

async function submit() {
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  loading.value = true
  try {
    if (mode.value === 'login') {
      const data = await login({ phone: form.phone, password: form.password })
      auth.setLogin(data)
      ElMessage.success(`欢迎回来，${data.nickname}`)
    } else {
      // 按角色裁剪 payload：玩家不带三件套
      const payload = {
        phone: form.phone, password: form.password,
        nickname: form.nickname, role: form.role,
      }
      if (form.role === 'adventurer') {
        payload.game_uid = form.game_uid.trim()
        payload.server = form.server.trim()
        payload.game_nickname = form.game_nickname.trim()
      }
      const data = await register(payload)
      auth.setLogin(data)
      ElMessage.success(form.role === 'adventurer'
        ? `欢迎加入，冒险家 ${data.nickname}`
        : `欢迎，${data.nickname}`)
    }
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2>{{ mode === 'login' ? '登录' : '注册账号' }}</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="1 开头 11 位" maxlength="11" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="昵称" prop="nickname">
          <el-input v-model="form.nickname" maxlength="50" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="注册身份">
          <el-radio-group v-model="form.role" @change="onRoleChange">
            <el-radio value="player">玩家（发布委托）</el-radio>
            <el-radio value="adventurer">冒险家（接委托）</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="mode === 'register' && form.role === 'adventurer'">
          <el-form-item label="游戏 UID" prop="game_uid">
            <el-input v-model="form.game_uid" maxlength="20" placeholder="9 位数字" />
          </el-form-item>
          <el-form-item label="服务器" prop="server">
            <el-input v-model="form.server" maxlength="20" placeholder="如 cn_gf01 / cn_qd01" />
          </el-form-item>
          <el-form-item label="游戏昵称" prop="game_nickname">
            <el-input v-model="form.game_nickname" maxlength="50" />
          </el-form-item>
        </template>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password
                    placeholder="8-64 位" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
        <div class="switch">
          <el-link type="primary" :underline="false" @click="switchMode">
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
