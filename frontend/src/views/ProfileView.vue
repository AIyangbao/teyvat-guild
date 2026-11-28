<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auth } from '../stores/auth'
import {
  getMyProfile, updateMyNickname, uploadAvatar, updateMyAdventurer,
} from '../api/user'

const profile = ref(null)
const loading = ref(false)
const uploading = ref(false)
const savingBase = ref(false)
const savingAdv = ref(false)

// 文件名固定为 {user_id}.{ext}，覆盖上传后 URL 不变；加时间戳逼浏览器重新取图
const stamp = ref(0)
const avatarSrc = computed(() =>
  profile.value?.avatar ? `${profile.value.avatar}?t=${stamp.value}` : '')

const baseRef = ref()
const base = reactive({ nickname: '' })
const advRef = ref()
const adv = reactive({ game_nickname: '', skill_tags: [], online_status: 'online' })

const tagSuggestions = ['风元素', '火元素', '雷元素', '治疗', '护盾', '采集', '战斗', '探索']
const roleLabel = r => ({ player: '玩家', adventurer: '冒险家', admin: '管理员' }[r] || r)

async function load() {
  loading.value = true
  try {
    const data = await getMyProfile()
    profile.value = data
    base.nickname = data.nickname
    adv.game_nickname = data.game_nickname || ''
    adv.skill_tags = data.skill_tags || []
    adv.online_status = data.online_status || 'offline'
  } finally {
    loading.value = false
  }
}
onMounted(load)

// 前端只做体验层拦截，真正的魔数校验在后端 storage_service
function beforeAvatarUpload(file) {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    ElMessage.error('仅支持 JPG / PNG / WEBP 格式')
    return false
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('头像不能超过 2MB')
    return false
  }
  return true
}

async function doUpload({ file }) {
  uploading.value = true
  try {
    profile.value = await uploadAvatar(file)
    stamp.value = Date.now()
    ElMessage.success('头像已更新')
  } finally {
    uploading.value = false
  }
}

async function saveNickname() {
  const ok = await baseRef.value.validate().catch(() => false)
  if (!ok) return
  savingBase.value = true
  try {
    profile.value = await updateMyNickname(base.nickname.trim())
    // 顶栏昵称来自登录时的本地缓存，不回填会显示旧名字
    if (auth.user) {
      auth.user.nickname = profile.value.nickname
      localStorage.setItem('user', JSON.stringify(auth.user))
    }
    ElMessage.success('昵称已更新')
  } finally {
    savingBase.value = false
  }
}

async function saveAdventurer() {
  const ok = await advRef.value.validate().catch(() => false)
  if (!ok) return
  savingAdv.value = true
  try {
    profile.value = await updateMyAdventurer({
      game_nickname: adv.game_nickname.trim(),
      skill_tags: adv.skill_tags,
      online_status: adv.online_status,
    })
    ElMessage.success('冒险家资料已更新')
  } finally {
    savingAdv.value = false
  }
}
</script>

<template>
  <div class="page" v-loading="loading">
    <h2>个人中心</h2>
    <p class="sub">身份取自登录凭证，这里只能看到和修改自己的资料</p>

    <template v-if="profile">
      <div class="two-col">
        <div class="panel">
          <div class="panel-title">头像</div>
          <div class="avatar-zone">
            <el-avatar :size="96" :src="avatarSrc || undefined" class="avatar">
              {{ profile.nickname.slice(0, 1) }}
            </el-avatar>
            <el-upload :show-file-list="false" :before-upload="beforeAvatarUpload"
                       :http-request="doUpload" accept="image/jpeg,image/png,image/webp">
              <el-button size="small" type="primary" :loading="uploading">更换头像</el-button>
            </el-upload>
            <div class="tip">JPG / PNG / WEBP，不超过 2MB</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">账号资料</div>
          <el-form ref="baseRef" :model="base" label-position="top" @submit.prevent>
            <el-form-item label="手机号">
              <el-input :model-value="profile.phone" disabled />
            </el-form-item>
            <el-form-item label="身份">
              <el-tag size="small">{{ roleLabel(profile.role) }}</el-tag>
            </el-form-item>
            <el-form-item label="昵称" prop="nickname"
                          :rules="[
                            { required: true, message: '请输入昵称', trigger: 'blur' },
                            { min: 1, max: 50, message: '昵称 1-50 字', trigger: 'blur' },
                          ]">
              <el-input v-model="base.nickname" maxlength="50" @keyup.enter="saveNickname" />
            </el-form-item>
            <el-button type="primary" size="small" :loading="savingBase"
                       @click="saveNickname">保存昵称</el-button>
          </el-form>
        </div>
      </div>

      <div v-if="profile.role === 'adventurer'" class="panel">
        <div class="panel-title">冒险家资料</div>
        <el-form ref="advRef" :model="adv" label-position="top" @submit.prevent>
          <el-form-item label="游戏昵称" prop="game_nickname"
                        :rules="[
                          { required: true, message: '请输入游戏昵称', trigger: 'blur' },
                          { min: 1, max: 50, message: '游戏昵称 1-50 字', trigger: 'blur' },
                        ]">
            <el-input v-model="adv.game_nickname" maxlength="50" />
          </el-form-item>
          <el-form-item label="服务器">
            <el-input :model-value="profile.server || '—'" disabled />
            <div class="tip">服务器注册后固定，暂不支持修改</div>
          </el-form-item>
          <el-form-item label="技能标签（最多 10 个，可直接输入后回车）">
            <el-select v-model="adv.skill_tags" multiple filterable allow-create
                       default-first-option :multiple-limit="10" placeholder="选择或输入标签"
                       style="width: 100%">
              <el-option v-for="t in tagSuggestions" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="接单状态">
            <el-switch v-model="adv.online_status" active-value="online"
                       inactive-value="offline" active-text="在线接单" inactive-text="离线" />
          </el-form-item>
          <el-button type="primary" size="small" :loading="savingAdv"
                     @click="saveAdventurer">保存冒险家资料</el-button>
        </el-form>
      </div>
    </template>
  </div>
</template>

<style scoped>
h2 { font-weight: 600; }
.sub { color: #909399; font-size: 12px; margin: 4px 0 16px; }
.panel { background: #fff; border: 1px solid #e4e7ed; border-radius: 10px;
         padding: 16px; margin-bottom: 16px; }
.panel-title { font-weight: 600; color: #303133; margin-bottom: 12px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.avatar-zone { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 8px 0; }
.avatar { background: #409eff; font-size: 32px; }
.tip { color: #c0c4cc; font-size: 12px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
</style>
