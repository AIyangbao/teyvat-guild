import request from './request'

// 模拟收银台：真实环境这一步发生在第三方支付服务器（带商户密钥签名），
// 我们直接打自己的回调接口完成链路闭环。
const PAY_SIGN = 'mock-callback-secret-change-me'

export const mockCallback = (outTradeNo, amount) =>
  request.post(`/payments/${outTradeNo}/callback`,
    { amount },
    { headers: { 'X-Pay-Sign': PAY_SIGN } })
