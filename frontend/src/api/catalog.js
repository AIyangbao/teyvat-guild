import request from './request'

// 复用管理端的公开 GET 拉服务目录（后端未拆独立的玩家 catalog 路由）
export const listCategories = () => request.get('/admin/categories')
export const listItems = params => request.get('/admin/items', { params })
