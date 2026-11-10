import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  { path: '/', name: 'hall', component: () => import('../views/HallView.vue') },
  { path: '/orders', name: 'orders', component: () => import('../views/OrdersView.vue'), meta: { auth: true } },
  { path: '/orders/:id', name: 'orderDetail', component: () => import('../views/OrderDetailView.vue'), meta: { auth: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(to => {
  if (to.meta.auth && !auth.token) return '/login'
})

export default router
