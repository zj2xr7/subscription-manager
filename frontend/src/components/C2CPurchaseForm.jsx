import { useEffect, useMemo, useState } from 'react'

const ESTIMATED_CHAIN_FEE = 0.01

export default function C2CPurchaseForm({ subscriptions, pendingPurchases, onQuote, onCreatePurchase }) {
  const [cnyAmount, setCnyAmount] = useState('')
  const [rate, setRate] = useState('7.2')
  const [selectedSubscriptions, setSelectedSubscriptions] = useState([])
  const [quote, setQuote] = useState(null)
  const [saving, setSaving] = useState(false)
  const bankSubscriptions = subscriptions.filter(item => item.payment_method === 'bank_card')

  useEffect(() => {
    let active = true
    if (!Number(rate)) return undefined
    onQuote({
      subscription_ids: selectedSubscriptions,
      c2c_rate: Number(rate),
      chain_fee: ESTIMATED_CHAIN_FEE,
    }).then(result => active && setQuote(result)).catch(() => active && setQuote(null))
    return () => { active = false }
  }, [selectedSubscriptions, rate, onQuote, pendingPurchases])

  const purchased = useMemo(() => (
    Number(cnyAmount) > 0 && Number(rate) > 0 ? Number(cnyAmount) / Number(rate) : 0
  ), [cnyAmount, rate])

  const toggleSubscription = id => setSelectedSubscriptions(values => (
    values.includes(id) ? values.filter(value => value !== id) : [...values, id]
  ))

  const submit = async event => {
    event.preventDefault()
    setSaving(true)
    try {
      await onCreatePurchase({ cny_amount: Number(cnyAmount), c2c_rate: Number(rate) })
      setCnyAmount('')
    } finally {
      setSaving(false)
    }
  }

  return <form className="panel fund-action-card purchase-card" onSubmit={submit}>
    <div className="fund-action-head">
      <div><p className="eyebrow">C2C PURCHASE</p><h2>C2C 买入</h2></div>
      <span className="action-step">01</span>
    </div>
    <p className="fund-action-copy">记录币安 C2C 买入，资金先进入待提链池，不计入银行卡余额。</p>

    <div className="deposit-fields">
      <label>买入人民币<input type="number" min="0.01" step="0.01" value={cnyAmount} onChange={event => setCnyAmount(event.target.value)} required placeholder="0.00" /></label>
      <label>C2C 单价（CNY/USDT）<input type="number" min="0.0001" step="0.0001" value={rate} onChange={event => setRate(event.target.value)} required /></label>
    </div>
    <div className="purchase-preview"><span>预计买入</span><b>{purchased.toFixed(2)} USDT</b></div>

    {bankSubscriptions.length > 0 && <div className="subscription-picker">
      <div className="picker-head"><b>按订阅估算</b><small>已计入银行卡余额与待提链资金</small></div>
      {bankSubscriptions.map(item => <label className="check-row" key={item.id}><input type="checkbox" checked={selectedSubscriptions.includes(item.id)} onChange={() => toggleSubscription(item.id)} /><span><b>{item.name}</b><small>{item.cost.required_usdt.toFixed(2)} USDT</small></span></label>)}
    </div>}

    {selectedSubscriptions.length > 0 && quote && <div className="topup-suggestion">
      <div><span>所选服务需要</span><b>{quote.required_usdt.toFixed(2)} USDT</b></div>
      <div><span>银行卡当前覆盖</span><b>{quote.covered_usdt.toFixed(2)} USDT</b></div>
      {quote.reserved_usdt > 0 && <div><span>更早账单已预留</span><b>{quote.reserved_usdt.toFixed(2)} USDT</b></div>}
      <div><span>银行卡余额缺口</span><b>{quote.shortfall_usdt.toFixed(2)} USDT</b></div>
      <div><span>待提链买入</span><b>{quote.pending_usdt.toFixed(2)} USDT</b></div>
      <div><span>预计提链费</span><b>{quote.transfer_fee.toFixed(2)} USDT</b></div>
      <div><span>仍需额外购买</span><b>{quote.additional_purchase_usdt.toFixed(2)} USDT</b></div>
      <div className="suggestion-total"><span>建议再买入</span><strong>¥{quote.suggested_cny_amount.toFixed(2)}</strong></div>
      <button type="button" className="text-fill" disabled={!quote.suggested_cny_amount} onClick={() => setCnyAmount(quote.suggested_cny_amount.toFixed(2))}>填入建议金额</button>
    </div>}

    <button className="secondary full fund-action-submit" disabled={saving || purchased <= 0}>{saving ? '保存中…' : '加入待提链池'}</button>
  </form>
}
