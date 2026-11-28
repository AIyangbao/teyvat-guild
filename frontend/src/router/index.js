import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  { path: '/', name: 'hall', component: () => import('../views/HallView.vue') },
  { path: '/orders', name: 'orders', component: () => import('../views/OrdersView.vue'), meta: { auth: true, player: true } },
  // 详情页不设角色守卫：详情接口公开，冒险家也要从「我的接单」点进来看自己接的单
  { path: '/orders/:id', name: 'orderDetail', component: () => import('../views/OrderDetailView.vue'), meta: { auth: true } },
  { path: '/accepted', name: 'accepted', component: () => import('../views/AcceptedView.vue'), meta: { auth: true, adventurer: true } },
  // 名录与档案是公开读侧：不设 auth，游客也能看评价（后端接口同样免登录）
  { path: '/adventurers', name: 'adventurers', component: () => import('../views/AdventurersView.vue') },
  { path: '/adventurers/:id', name: 'adventurerProfile', component: () => import('../views/AdventurerProfileView.vue') },
  // 个人中心：三种角色都能进，角色差异由页面内 v-if 处理
  { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { auth: true } },
  { path: '/admin/audit', name: 'adminAudit', component: () => import('../views/AdminAuditView.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/stats', name: 'adminStats', component: () => import('../views/AdminStatsView.vue'), meta: { auth: true, admin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(to => {
  if (to.meta.auth && !auth.token) return '/login'
  // 前端只做体验层拦截（别让人看到进不去的入口）；
  // 真正的角色校验在后端 get_current_player / get_current_adventurer
  if (to.meta.player && auth.user?.role !== 'player') return '/'
  if (to.meta.adventurer && auth.user?.role !== 'adventurer') return '/'
  if (to.meta.admin && auth.user?.role !== 'admin') return '/'
})

export default router
