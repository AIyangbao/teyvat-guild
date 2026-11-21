import request from './request'

export const listHall = params => request.get('/commissions/hall', { params })
export const listMine = params => request.get('/commissions/mine', { params })
export const listAccepted = params => request.get('/commissions/accepted', { params })
export const getOrder = id => request.get(`/commissions/${id}`)
export const createOrder = data => request.post('/commissions/create_order', data)
export const payOrder = id => request.post(`/commissions/${id}/pay`)
export const acceptOrder = id => request.post(`/commissions/${id}/accept`)
export const deliverOrder = id => request.post(`/commissions/${id}/deliver`)
export const confirmOrder = id => request.post(`/commissions/${id}/confirm`)
export const createReview = (id, data) => request.post(`/commissions/${id}/review`, data)