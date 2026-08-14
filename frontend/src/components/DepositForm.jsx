import { useEffect, useMemo, useState } from 'react'

export default function DepositForm({
  balance,
  subscriptions,
  pendingPurchases,
  onQuote,
  onCreatePurchase,
  onDeletePurchase,
  onTransfer,
}) {
  const [cnyAmount, setCnyAmount] = useState('')
  const [rate, setRate] = useState('7.2')
  const [chainFee, setChainFee] = useState('0.01')
  const [selectedSubscriptions, setSelectedSubscriptions] = useState([])
  const [selectedPurchases, setSelectedPurchases] = useState([])
  const [quote, setQuote] = useState(null)
  const [savingPurchase, setSavingPurchase] = useState(false)
  const [transferring, setTransferring] = useState(false)
  const bankSubscriptions = subscriptions.filter(item => item.payment_method === 'bank_card')

  useEffect(() => {
    let active = true
    if (!Number(rate)) return undefined
    onQuote({
      subscription_ids: selectedSubscriptions,
      c2c_rate: Number(rate),
      chain_fee: Math.max(0, Number(chainFee) || 0),
    }).then(result => active && setQuote(result)).catch(() => active && setQuote(null))
    return () => { active = false }
  }, [selectedSubscriptions, rate, chainFee, onQuote, pendingPurchases])

  useEffect(() => {
    const ids = new Set(pendingPurchases.map(item => item.id))
    setSelectedPurchases(values => values.filter(id => ids.has(id)))
  }, [pendingPurchases])

  const purchasePreview = useMemo(() => {
    const purchased = Number(cnyAmount) > 0 && Number(rate) > 0 ? Number(cnyAmount) / Number(rate) : 0
    return { purchased }
  }, [cnyAmount, rate])

  const transferPreview = useMemo(() => {
    const gross = pendingPurchases
      .filter(item => selectedPurchases.includes(item.id))
      .reduce((sum, item) => sum + item.purchased_usdt, 0)
    const fee = Math.max(0, Number(chainFee) || 0)
    return { gross, fee, received: Math.max(0, gross - fee) }
  }, [pendingPurchases, selectedPurchases, chainFee])

  const toggleSubscription = id => setSelectedSubscriptions(values => values.includes(id) ? values.filter(value => value !== id) : [...values, id])
  const togglePurchase = id => setSelectedPurchases(values => values.includes(id) ? values.filter(value => value !== id) : [...values, id])

  const savePurchase = async event => {
    event.preventDefault()
    setSavingPurchase(true)
    try {
      await onCreatePurchase({ cny_amount: Number(cnyAmount), c2c_rate: Number(rate) })
      setCnyAmount('')
    } finally {
      setSavingPurchase(false)
    }
  }

  const transfer = async () => {
    setTransferring(true)
    try {
      await onTransfer({ purchase_ids: selectedPurchases, chain_fee: Number(chainFee) })
      setSelectedPurchases([])
    } finally {
      setTransferring(false)
    }
  }

  return <section className="panel deposit-form">
    <div className="section-title"><div><p className="eyebrow">TOP UP</p><h2>C2C 买入与提链</h2></div></div>

    <form className="purchase-entry" onSubmit={savePurchase}>
      <div className="picker-head"><b>记录 C2C 买入</b><small>买入后先进入待提链池，不计入银行卡余额</small></div>
      <div className="deposit-fields">
        <label>买入人民币<input type="number" min="0.01" step="0.01" value={cnyAmount} onChange={event => setCnyAmount(event.target.value)} required placeholder="0.00" /></label>
        <label>C2C 单价（CNY/USDT）<input type="number" min="0.0001" step="0.0001" value={rate} onChange={event => setRate(event.target.value)} required /></label>
      </div>
      <div className="purchase-preview"><span>预计买入</span><b>{purchasePreview.purchased.toFixed(2)} USDT</b></div>
      <button className="secondary full" disabled={savingPurchase || purchasePreview.purchased <= 0}>{savingPurchase ? '保存中…' : '加入待提链池'}</button>
    </form>

    {bankSubscriptions.length > 0 && <div className="subscription-picker"><div className="picker-head"><b>按订阅估算</b><small>待提链资金会优先抵扣建议购买量</small></div>{bankSubscriptions.map(item => <label className="check-row" key={item.id}><input type="checkbox" checked={selectedSubscriptions.includes(item.id)} onChange={() => toggleSubscription(item.id)} /><span><b>{item.name}</b><small>{item.cost.required_usdt.toFixed(2)} USDT</small></span></label>)}</div>}
    {selectedSubscriptions.length > 0 && quote && <div className="topup-suggestion">
      <div><span>所选服务需要</span><b>{quote.required_usdt.toFixed(2)} USDT</b></div>
      <div><span>银行卡当前覆盖</span><b>{quote.covered_usdt.toFixed(2)} USDT</b></div>
      {quote.reserved_usdt > 0 && <div><span>更早账单已预留</span><b>{quote.reserved_usdt.toFixed(2)} USDT</b></div>}
      <div><span>银行卡余额缺口</span><b>{quote.shortfall_usdt.toFixed(2)} USDT</b></div>
      <div><span>待提链买入</span><b>{quote.pending_usdt.toFixed(2)} USDT</b></div>
      <div><span>本次提链费</span><b>{quote.transfer_fee.toFixed(2)} USDT</b></div>
      <div><span>仍需额外购买</span><b>{quote.additional_purchase_usdt.toFixed(2)} USDT</b></div>
      <div className="suggestion-total"><span>建议再买入</span><strong>¥{quote.suggested_cny_amount.toFixed(2)}</strong></div>
      <button type="button" className="text-fill" disabled={!quote.suggested_cny_amount} onClick={() => setCnyAmount(quote.suggested_cny_amount.toFixed(2))}>填入建议金额</button>
    </div>}

    <div className="pending-purchases">
      <div className="picker-head"><b>待提链买入</b><small>{pendingPurchases.length} 笔 · 选择整笔合并提链</small></div>
      {pendingPurchases.length ? pendingPurchases.map(item => <div className={`pending-purchase-row ${selectedPurchases.includes(item.id) ? 'selected' : ''}`} key={item.id}>
        <label><input type="checkbox" checked={selectedPurchases.includes(item.id)} onChange={() => togglePurchase(item.id)} /><span><b>¥{item.cny_amount.toFixed(2)}</b><small>{item.purchased_usdt.toFixed(2)} USDT · ¥{item.c2c_rate.toFixed(2)}/USDT</small></span></label>
        <button type="button" className="danger-link" onClick={() => confirm('确定删除这笔尚未提链的 C2C 买入吗？') && onDeletePurchase(item.id)}>删除</button>
      </div>) : <p className="muted-copy">暂无待提链买入</p>}
    </div>

    <div className="transfer-box">
      <label>本次提链费（USDT）<input type="number" min="0" step="0.0001" value={chainFee} onChange={event => setChainFee(event.target.value)} /></label>
      <div className="deposit-preview">
        <div><span>所选买入</span><b>{transferPreview.gross.toFixed(2)} USDT</b></div>
        <div><span>单次提链费</span><b>{transferPreview.fee.toFixed(2)} USDT</b></div>
        <div><span>实际到账</span><b>{transferPreview.received.toFixed(2)} USDT</b></div>
      </div>
      <button type="button" className="primary full deposit-submit" disabled={transferring || !selectedPurchases.length || transferPreview.received <= 0} onClick={transfer}>{transferring ? '提链中…' : `确认合并提链（${selectedPurchases.length} 笔）`}</button>
    </div>
  </section>
}
