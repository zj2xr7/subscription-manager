const request = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (response.status === 204) return null
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || '请求失败，请稍后重试')
  return body
}

export const api = {
  subscriptions: () => request('/subscriptions'),
  subscriptionCharges: (type = 'all') => request(`/subscriptions/charges?type=${type}`),
  createSubscription: data => request('/subscriptions', { method: 'POST', body: JSON.stringify(data) }),
  updateSubscription: (id, data) => request(`/subscriptions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSubscription: id => request(`/subscriptions/${id}`, { method: 'DELETE' }),
  chargeSubscription: id => request(`/subscriptions/${id}/charge`, { method: 'POST' }),
  balance: () => request('/bank-card/balance'),
  deposits: () => request('/bank-card/deposits'),
  lots: () => request('/bank-card/lots'),
  transactions: (type = 'all') => request(`/bank-card/transactions?type=${type}`),
  topUpQuote: data => request('/bank-card/top-up-quote', { method: 'POST', body: JSON.stringify(data) }),
  deposit: data => request('/bank-card/deposit', { method: 'POST', body: JSON.stringify(data) }),
  deleteDeposit: id => request(`/bank-card/deposits/${id}`, { method: 'DELETE' }),
  exchangeQuotes: (refresh = false, apiKey = null) => apiKey === null
    ? request(`/exchange/quotes${refresh ? '?refresh=true' : ''}`)
    : request('/exchange/quotes', { method: 'POST', body: JSON.stringify({ api_key: apiKey, refresh }) }),
  settings: () => request('/settings'),
  saveSettings: data => request('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  saveNotificationSettings: data => request('/settings/notification', { method: 'PUT', body: JSON.stringify(data) }),
  saveExchangeRateSettings: exchange_rate_api_key => request('/settings/exchange-rate', { method: 'PUT', body: JSON.stringify({ exchange_rate_api_key }) }),
  testNotification: () => request('/settings/test-notification', { method: 'POST', body: '{}' }),
}
