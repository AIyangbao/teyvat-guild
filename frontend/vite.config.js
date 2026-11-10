import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 开发期用 vite proxy 转发到 FastAPI，避免后端配 CORS；
// 生产由 nginx 同时托管前端静态文件并反代 /api。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: p => p.replace(/^\/api/, ''),
      },
    },
  },
})
