import { useEffect, useMemo, useState } from 'react'

export default function DepositForm({ balance, subscriptions, onQuote, onSubmit }) {
  const [cnyAmount, setCnyAmount] = useState('')
  const [rate, setRate] = useState('7.2')
  const [selected, setSelected] = useState([])
  const [quote, setQuote] = useState(null)
  const [saving, setSaving] = useState(false)
  const bankSubscriptions = subscriptions.filter(item => item.payment_method === 'bank_card')
  useEffect(() => {
    let active = true
    if (!Number(rate)) return undefined
    onQuote({ subscription_ids: selected, c2c_rate: Number(rate) }).then(result => active && setQuote(result)).catch(() => active && setQuote(null))
    return () => { active = false }
  }, [selected, rate, onQuote])
  const preview = useMemo(() => {
    const purchased = Number(cnyAmount) > 0 && Number(rate) > 0 ? Number(cnyAmount) / Number(rate) : 0
    return { purchased, received: Math.max(0, purchased - .01) }
  }, [cnyAmount, rate])
  const toggle = id => setSelected(values => values.includes(id) ? values.filter(value => value !== id) : [...values, id])
  return <form className="panel deposit-form" onSubmit={async event => { event.preventDefault(); setSaving(true); try { await onSubmit({ cny_amount: Number(cnyAmount), c2c_rate: Number(rate) }); setCnyAmount(''); setSelected([]) } finally { setSaving(false) } }}>
    <div className="section-title"><div><p className="eyebrow">TOP UP</p><h2>C2C 充值</h2></div></div>
    <div className="deposit-fields"><label>充值人民币<input type="number" min="0.01" step="0.01" value={cnyAmount} onChange={event => setCnyAmount(event.target.value)} required placeholder="0.00" /></label><label>C2C 单价（CNY/USDT）<input type="number" min="0.01" step="0.01" value={rate} onChange={event => setRate(event.target.value)} required /></label></div>
    {bankSubscriptions.length > 0 && <div className="subscription-picker"><div className="picker-head"><b>按订阅估算</b><small>每项计算下一期一次</small></div>{bankSubscriptions.map(item => <label className="check-row" key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} /><span><b>{item.name}</b><small>{item.cost.required_usdt.toFixed(2)} USDT</small></span></label>)}</div>}
    {selected.length > 0 && quote && <div className="topup-suggestion"><div><span>所选服务需要</span><b>{quote.required_usdt.toFixed(2)} USDT</b></div><div><span>钱包总余额</span><b>{balance.toFixed(2)} USDT</b></div>{quote.reserved_usdt > 0 && <div><span>更早账单已预留</span><b>{quote.reserved_usdt.toFixed(2)} USDT</b></div>}<div><span>当前已覆盖</span><b>{quote.covered_usdt.toFixed(2)} USDT</b></div><div><span>余额缺口</span><b>{quote.shortfall_usdt.toFixed(2)} USDT</b></div><div className="suggestion-total"><span>建议充值</span><strong>¥{quote.suggested_cny_amount.toFixed(2)}</strong></div><button type="button" className="text-fill" disabled={!quote.suggested_cny_amount} onClick={() => setCnyAmount(quote.suggested_cny_amount.toFixed(2))}>填入建议金额</button></div>}
    <div className="deposit-preview"><div><span>预计买入</span><b>{preview.purchased.toFixed(2)} USDT</b></div><div><span>上链费</span><b>0.01 USDT</b></div><div><span>实际到账</span><b>{preview.received.toFixed(2)} USDT</b></div></div>
    <button className="primary full deposit-submit" disabled={saving || preview.purchased <= .01}>{saving ? '处理中…' : '确认充值'}</button>
  </form>
}
