import { useEffect, useMemo, useState } from 'react'

export default function TransferForm({ pendingPurchases, onDeletePurchase, onTransfer }) {
  const [selectedPurchases, setSelectedPurchases] = useState([])
  const [chainFee, setChainFee] = useState('0.01')
  const [transferring, setTransferring] = useState(false)

  useEffect(() => {
    const ids = new Set(pendingPurchases.map(item => item.id))
    setSelectedPurchases(values => values.filter(id => ids.has(id)))
  }, [pendingPurchases])

  const preview = useMemo(() => {
    const gross = pendingPurchases
      .filter(item => selectedPurchases.includes(item.id))
      .reduce((sum, item) => sum + item.purchased_usdt, 0)
    const fee = Math.max(0, Number(chainFee) || 0)
    return { gross, fee, received: Math.max(0, gross - fee) }
  }, [pendingPurchases, selectedPurchases, chainFee])

  const togglePurchase = id => setSelectedPurchases(values => (
    values.includes(id) ? values.filter(value => value !== id) : [...values, id]
  ))
  const selectAll = () => setSelectedPurchases(pendingPurchases.map(item => item.id))
  const clearAll = () => setSelectedPurchases([])

  const transfer = async () => {
    setTransferring(true)
    try {
      await onTransfer({ purchase_ids: selectedPurchases, chain_fee: Number(chainFee) })
      setSelectedPurchases([])
    } finally {
      setTransferring(false)
    }
  }

  return <section className="panel fund-action-card transfer-card">
    <div className="fund-action-head">
      <div><p className="eyebrow">ON-CHAIN TRANSFER</p><h2>USDT 提链</h2></div>
      <span className="action-step">02</span>
    </div>
    <p className="fund-action-copy">选择本次需要提链的 C2C 买入，多笔合并后只扣一次提链费。</p>

    <div className="pending-picker-head">
      <div><b>待提链买入</b><small>{pendingPurchases.length} 笔可选 · 已选 {selectedPurchases.length} 笔</small></div>
      <div><button type="button" disabled={!pendingPurchases.length || selectedPurchases.length === pendingPurchases.length} onClick={selectAll}>全选</button><button type="button" disabled={!selectedPurchases.length} onClick={clearAll}>清空</button></div>
    </div>

    <div className="pending-purchase-list">
      {pendingPurchases.length ? pendingPurchases.map(item => <div className={`pending-purchase-row ${selectedPurchases.includes(item.id) ? 'selected' : ''}`} key={item.id}>
        <label><input type="checkbox" checked={selectedPurchases.includes(item.id)} onChange={() => togglePurchase(item.id)} /><span><b>¥{item.cny_amount.toFixed(2)}</b><small>{new Date(item.created_at).toLocaleString('zh-CN')}</small><small>{item.purchased_usdt.toFixed(2)} USDT · ¥{item.c2c_rate.toFixed(2)}/USDT</small></span></label>
        <button type="button" className="danger-link" onClick={() => confirm('确定删除这笔尚未提链的 C2C 买入吗？') && onDeletePurchase(item.id)}>删除</button>
      </div>) : <div className="pending-empty"><span>✓</span><b>暂无待提链买入</b><small>先在左侧记录一笔 C2C 买入。</small></div>}
    </div>

    <label className="chain-fee-field">本次提链费（USDT）<input type="number" min="0" step="0.0001" value={chainFee} onChange={event => setChainFee(event.target.value)} /></label>
    <div className="deposit-preview transfer-preview">
      <div><span>所选买入</span><b>{preview.gross.toFixed(2)} USDT</b></div>
      <div><span>单次提链费</span><b>{preview.fee.toFixed(2)} USDT</b></div>
      <div><span>实际到账</span><b>{preview.received.toFixed(2)} USDT</b></div>
    </div>
    <button type="button" className="primary full fund-action-submit" disabled={transferring || !selectedPurchases.length || preview.received <= 0} onClick={transfer}>{transferring ? '提链中…' : `确认提链（${selectedPurchases.length} 笔）`}</button>
  </section>
}
