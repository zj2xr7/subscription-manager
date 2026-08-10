import { useEffect, useMemo, useState } from 'react'

const initial = { name: '', price: '', currency: 'USD', billing_cycle: 'monthly', custom_days: '', next_billing_date: new Date().toISOString().slice(0, 10), payment_method: 'alipay' }

export default function SubscriptionForm({ item, onClose, onSave }) {
  const [form, setForm] = useState(initial)
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (item) setForm({ ...item, custom_days: item.custom_days || '' }) }, [item])
  const set = event => setForm(value => ({ ...value, [event.target.name]: event.target.value }))
  const estimate = useMemo(() => {
    const price = Number(form.price) || 0
    const cnyRate = { USD: 7.2, GBP: 9.14, CAD: 5.32, CNY: 1 }[form.currency]
    return form.payment_method === 'alipay' ? price * cnyRate : null
  }, [form])
  const submit = async event => {
    event.preventDefault(); setSaving(true)
    try {
      await onSave({ name: form.name, price: Number(form.price), currency: form.currency, billing_cycle: form.billing_cycle, custom_days: form.billing_cycle === 'custom' ? Number(form.custom_days) : null, next_billing_date: form.next_billing_date, payment_method: form.payment_method, c2c_rate: null })
    } finally { setSaving(false) }
  }
  return <div className="modal-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <form className="modal subscription-modal" onSubmit={submit}>
      <div className="modal-head"><div><p className="eyebrow">SUBSCRIPTION</p><h2>{item ? '编辑订阅' : '添加新订阅'}</h2></div><button type="button" onClick={onClose}>×</button></div>
      <label>订阅名称<input name="name" value={form.name} onChange={set} required autoFocus /></label>
      <div className="form-grid"><label>价格<input name="price" type="number" min="0.01" step="0.01" value={form.price} onChange={set} required /></label><label>货币<select name="currency" value={form.currency} onChange={event => setForm(value => ({ ...value, currency: event.target.value, payment_method: event.target.value === 'CNY' ? 'alipay' : value.payment_method }))}><option value="USD">USD — 美元</option><option value="GBP">GBP — 英镑</option><option value="CAD">CAD — 加拿大元</option><option value="CNY">CNY — 人民币</option></select></label></div>
      <div className="form-grid"><label>计费周期<select name="billing_cycle" value={form.billing_cycle} onChange={set}><option value="monthly">每月</option><option value="yearly">每年</option><option value="custom">自定义</option></select></label><label>{form.billing_cycle === 'custom' ? '周期天数' : '下次续费'}{form.billing_cycle === 'custom' ? <input name="custom_days" type="number" min="1" value={form.custom_days} onChange={set} required /> : <input name="next_billing_date" type="date" value={form.next_billing_date} onChange={set} required />}</label></div>
      {form.billing_cycle === 'custom' && <label>下次续费<input name="next_billing_date" type="date" value={form.next_billing_date} onChange={set} required /></label>}
      <label>支付方式<div className="segmented"><button type="button" className={form.payment_method === 'alipay' ? 'active' : ''} onClick={() => setForm(value => ({ ...value, payment_method: 'alipay' }))}>支付宝</button><button type="button" disabled={form.currency === 'CNY'} className={form.payment_method === 'bank_card' ? 'active' : ''} onClick={() => setForm(value => ({ ...value, payment_method: 'bank_card' }))}>USDT 银行卡</button></div></label>
      <div className="estimate"><span>{estimate == null ? '扣款时按可用充值批次 FIFO 核算' : '预计人民币成本'}</span><strong>{estimate == null ? '真实批次成本' : `¥${estimate.toFixed(2)}`}</strong><small>{estimate == null ? '不再使用预设 C2C 单价' : '保存后将使用最新汇率重新计算'}</small></div>
      <div className="modal-actions"><button type="button" className="secondary compact-button" onClick={onClose}>取消</button><button className="primary compact-button" disabled={saving}>{saving ? '保存中…' : '保存订阅'}</button></div>
    </form>
  </div>
}
