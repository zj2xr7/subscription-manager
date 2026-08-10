import { useEffect, useState } from 'react'

const currencyNames = { USD: '美元', GBP: '英镑', CAD: '加拿大元' }

export default function Settings({ settings, exchangeQuotes, onSave, onTest, onRefreshRates }) {
  const [form, setForm] = useState(settings)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  useEffect(() => setForm(settings), [settings])
  const change = event => setForm(value => ({ ...value, [event.target.name]: event.target.name === 'notification_days_before' ? Number(event.target.value) : event.target.value }))
  const sourceLabel = exchangeQuotes?.source === 'api' ? '实时 API 汇率' : '内置参考汇率'
  return <main className="settings-page"><div className="page-head"><div><p className="eyebrow">PREFERENCES</p><h1>设置</h1><p>管理续费通知与货币换算数据。</p></div></div>
    <form onSubmit={async event => { event.preventDefault(); setSaving(true); try { await onSave(form) } finally { setSaving(false) } }}>
      <section className="panel settings-section"><div className="setting-section-head"><div className="setting-icon purple">♢</div><div><h2>Server 酱通知</h2><p>订阅到期前，通过微信接收续费提醒。</p></div></div><div className="setting-fields"><label><span>SendKey</span><small>用于向你的 Server 酱账号发送消息</small><input type="password" name="server_chan_key" value={form.server_chan_key || ''} onChange={change} placeholder="SCT..." /></label><label><span>提前通知天数</span><small>到期前多少天发送一次提醒</small><input type="number" name="notification_days_before" value={form.notification_days_before ?? 7} onChange={change} min="0" max="90" /></label></div><div className="setting-actions"><button type="button" className="secondary compact-button" disabled={testing || !form.server_chan_key} onClick={async () => { setTesting(true); try { await onTest(form.server_chan_key) } finally { setTesting(false) } }}>{testing ? '发送中…' : '发送测试通知'}</button></div></section>
      <section className="panel settings-section"><div className="setting-section-head"><div className="setting-icon blue">↔</div><div><h2>实时汇率</h2><p>订阅成本统一换算为人民币；汇率缓存一小时。</p></div></div><div className="setting-fields single"><label><span>ExchangeRate-API Key</span><small>留空时继续使用内置参考汇率</small><input type="password" name="exchange_rate_api_key" value={form.exchange_rate_api_key || ''} onChange={change} placeholder="输入 API Key" /></label></div>
        <div className="rates-head"><div><b>{sourceLabel}</b><small>{exchangeQuotes?.updated_at ? `更新于 ${new Date(exchangeQuotes.updated_at).toLocaleString('zh-CN')}` : '正在读取汇率'}</small></div><button type="button" className="secondary compact-button" disabled={refreshing} onClick={async () => { setRefreshing(true); try { await onRefreshRates() } finally { setRefreshing(false) } }}>{refreshing ? '刷新中…' : '刷新汇率'}</button></div>
        <div className="rate-grid">{Object.entries(exchangeQuotes?.quotes || {}).map(([currency, rate]) => <article key={currency}><span>{currencyNames[currency]}</span><b>1 {currency}</b><strong>¥{rate.toFixed(4)}</strong></article>)}</div>
        {exchangeQuotes?.source === 'reference' && <div className="rate-notice">当前展示参考汇率；配置有效 API Key 后刷新即可切换到实时数据。</div>}
      </section>
      <div className="save-bar"><span>配置保存在本机数据库中</span><button className="primary compact-button" disabled={saving}>{saving ? '保存中…' : '保存设置'}</button></div>
    </form>
  </main>
}
