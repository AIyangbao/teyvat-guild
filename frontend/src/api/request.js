import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',   // 开发期走 vite proxy，生产走 nginx 反代
  timeout: 10000,
})

// 请求拦截：自动带 token
request.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// 响应拦截：统一弹错；401 清登录态并跳登录页
request.interceptors.response.use(
  resp => resp.data,   // 直接返回 body，调用处少写一层 .data
  err => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    let message
    if (Array.isArray(detail)) {           // pydantic 422 校验错误是数组
      message = detail.map(d => d.msg).join('; ')
    } else if (typeof detail === 'object' && detail) {
      message = detail.message || JSON.stringify(detail)
    } else {
      message = detail || err.message
    }
    if (status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (location.pathname !== '/login') location.href = '/login'
    } else {
      ElMessage.error(message || `请求失败(${status})`)
    }
    return Promise.reject(err)
  },
)

export default request
