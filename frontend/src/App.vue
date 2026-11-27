<script setup>
import { useRouter } from 'vue-router'
import { auth } from './stores/auth'

const router = useRouter()

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container>
    <el-header class="topbar">
      <div class="brand" @click="router.push('/')">提瓦特冒险家协会</div>
      <nav class="nav">
        <router-link to="/">委托大厅</router-link>
        <router-link to="/adventurers">冒险家名录</router-link>
        <router-link v-if="auth.token && auth.user?.role === 'player'" to="/orders">我的委托</router-link>
        <router-link v-if="auth.token && auth.user?.role === 'adventurer'" to="/accepted">我的接单</router-link>
        <router-link v-if="auth.token && auth.user?.role === 'admin'" to="/admin/stats">数据看板</router-link>
        <router-link v-if="auth.token && auth.user?.role === 'admin'" to="/admin/audit">审核管理</router-link>
      </nav>
      <div class="user-zone">
        <template v-if="auth.token">
          <span class="nickname">{{ auth.user?.nickname }}</span>
          <el-button size="small" @click="onLogout">退出</el-button>
        </template>
        <el-button v-else size="small" type="primary" @click="router.push('/login')">
          登录 / 注册
        </el-button>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  position: sticky;
  top: 0;
  z-index: 10;
}
.brand {
  font-weight: 700;
  font-size: 17px;
  color: #409eff;
  cursor: pointer;
}
.nav {
  display: flex;
  gap: 16px;
  flex: 1;
}
.nav a {
  color: #606266;
  text-decoration: none;
  padding: 4px 2px;
}
.nav a.router-link-exact-active {
  color: #409eff;
  border-bottom: 2px solid #409eff;
}
.user-zone {
  display: flex;
  align-items: center;
  gap: 10px;
}
.nickname {
  color: #909399;
  font-size: 14px;
}
</style>
