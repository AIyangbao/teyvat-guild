import request from './request'

export const listHall = params => request.get('/commissions/hall', { params })
export const listMine = params => request.get('/commissions/mine', { params })
export const getOrder = id => request.get(`/commissions/${id}`)
export const createOrder = data => request.post('/commissions/create_order', data)
export const payOrder = id => request.post(`/commissions/${id}/pay`)
