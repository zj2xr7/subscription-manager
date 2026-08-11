import { useEffect, useState } from 'react'

const currencyNames = { USD: '美元', GBP: '英镑', CAD: '加拿大元' }

export default function Settings({ settings, exchangeQuotes, onSaveNotification, onSaveExchange, onTest, onRefreshRates }) {
  const [notificationForm, setNotificationForm] = useState({ server_chan_key: '', notification_days_before: [7] })
  const [dayDraft, setDayDraft] = useState(1)
  const [exchangeKey, setExchangeKey] = useState('')
  const [savingNotification, setSavingNotification] = useState(false)
  const [savingExchange, setSavingExchange] = useState(false)
  const [testing, setTesting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => setNotificationForm({
    server_chan_key: settings.server_chan_key || '',
    notification_days_before: settings.notification_days_before ?? [7],
  }), [settings.server_chan_key, settings.notification_days_before])
  useEffect(() => setExchangeKey(settings.exchange_rate_api_key || ''), [settings.exchange_rate_api_key])

  const notificationDirty = notificationForm.server_chan_key.trim() !== (settings.server_chan_key || '')
    || notificationForm.notification_days_before.join(',') !== (settings.notification_days_before ?? [7]).join(',')
  const exchangeDirty = exchangeKey.trim() !== (settings.exchange_rate_api_key || '')
  const sourceLabel = exchangeQuotes?.source === 'api' ? '实时 API 汇率' : '内置参考汇率'

  const saveNotification = async () => {
    setSavingNotification(true)
    try { await onSaveNotification({ ...notificationForm, server_chan_key: notificationForm.server_chan_key.trim() }) }
    finally { setSavingNotification(false) }
  }
  const saveExchange = async () => {
    setSavingExchange(true)
    try { await onSaveExchange(exchangeKey.trim()) }
    finally { setSavingExchange(false) }
  }
  const addNotificationDay = () => {
    const day = Number(dayDraft)
    if (!Number.isInteger(day) || day < 0 || day > 90) return
    setNotificationForm(value => ({ ...value, notification_days_before: [...new Set([...value.notification_days_before, day])].sort((a, b) => b - a) }))
  }
  const removeNotificationDay = day => setNotificationForm(value => ({ ...value, notification_days_before: value.notification_days_before.filter(item => item !== day) }))

  return <main className="settings-page"><div className="page-head"><div><p className="eyebrow">PREFERENCES</p><h1>设置</h1><p>管理续费通知与货币换算数据。</p></div></div>
    <section className="panel settings-section"><div className="setting-section-head"><div className="setting-icon purple">♢</div><div><h2>Server 酱通知</h2><p>订阅到期前，通过微信接收续费提醒。</p></div></div><div className="setting-fields notification-setting-fields"><label><span>SendKey</span><small>用于向你的 Server 酱账号发送消息</small><input type="password" name="server_chan_key" value={notificationForm.server_chan_key} onChange={event => setNotificationForm(value => ({ ...value, server_chan_key: event.target.value }))} placeholder="SCT..." /></label><div className="notification-days-field"><span>提前通知天数</span><small>可添加多个节点，0 表示续费当天</small><div className="notification-day-entry"><input type="number" value={dayDraft} onChange={event => setDayDraft(event.target.value)} min="0" max="90" /><button type="button" className="secondary" onClick={addNotificationDay}>添加</button></div><div className="notification-day-tags">{notificationForm.notification_days_before.map(day => <button type="button" key={day} disabled={notificationForm.notification_days_before.length === 1} onClick={() => removeNotificationDay(day)}>{day === 0 ? '当天' : `${day} 天前`}<span>×</span></button>)}</div></div></div><div className="setting-actions split-actions"><button type="button" className="secondary compact-button" disabled={testing || savingNotification || notificationDirty || !settings.server_chan_key} onClick={async () => { setTesting(true); try { await onTest() } finally { setTesting(false) } }}>{testing ? '发送中…' : '发送测试通知'}</button><button type="button" className="primary compact-button" disabled={savingNotification || !notificationDirty || notificationForm.notification_days_before.length === 0} onClick={saveNotification}>{savingNotification ? '保存中…' : '保存通知设置'}</button></div></section>
    <section className="panel settings-section"><div className="setting-section-head"><div className="setting-icon blue">↔</div><div><h2>实时汇率</h2><p>订阅成本统一换算为人民币；汇率缓存一小时。</p></div></div><div className="setting-fields single"><label><span>ExchangeRate-API Key</span><small>留空并保存时切换为内置参考汇率</small><input type="password" name="exchange_rate_api_key" value={exchangeKey} onChange={event => setExchangeKey(event.target.value)} placeholder="输入 API Key" /></label></div>
      <div className="rates-head"><div><b>{sourceLabel}</b><small>{exchangeQuotes?.updated_at ? `更新于 ${new Date(exchangeQuotes.updated_at).toLocaleString('zh-CN')}` : '正在读取汇率'}</small></div></div>
      <div className="rate-grid">{Object.entries(exchangeQuotes?.quotes || {}).map(([currency, rate]) => <article key={currency}><span>{currencyNames[currency]}</span><b>1 {currency}</b><strong>¥{rate.toFixed(4)}</strong></article>)}</div>
      {exchangeQuotes?.source === 'reference' && <div className="rate-notice">当前展示参考汇率；保存有效 API Key 后即可切换到实时数据。</div>}
      <div className="setting-actions split-actions rate-actions"><button type="button" className="secondary compact-button" disabled={refreshing || savingExchange || exchangeDirty || !settings.exchange_rate_api_key} onClick={async () => { setRefreshing(true); try { await onRefreshRates() } finally { setRefreshing(false) } }}>{refreshing ? '刷新中…' : '验证并刷新'}</button><button type="button" className="primary compact-button" disabled={savingExchange || !exchangeDirty} onClick={saveExchange}>{savingExchange ? '验证并保存中…' : '保存汇率设置'}</button></div>
    </section>
  </main>
}
