import { useMemo, useState } from 'react'
import C2CPurchaseForm from '../components/C2CPurchaseForm'
import TransferForm from '../components/TransferForm'

const filters = [['all', '全部'], ['deposit', '提链到账'], ['charge', '订阅扣款']]

export default function BankCard({
  balance,
  lots,
  transactions,
  subscriptions,
  pendingPurchases,
  onQuote,
  onCreatePurchase,
  onDeletePurchase,
  onTransfer,
  onDeleteTransfer,
}) {
  const [filter, setFilter] = useState('all')
  const shown = filter === 'all' ? transactions : transactions.filter(item => item.type === filter)
  const costBasis = useMemo(() => lots.reduce((sum, lot) => sum + lot.remaining_usdt * lot.c2c_rate, 0), [lots])
  const averageRate = balance > 0 ? costBasis / balance : 0
  const pendingUsdt = useMemo(() => pendingPurchases.reduce((sum, item) => sum + item.purchased_usdt, 0), [pendingPurchases])
  const removeTransfer = item => {
    if (confirm('该次提链尚未参与订阅扣款。删除后，关联 C2C 买入会退回待提链池，银行卡余额同步减少。\n\n确定删除吗？')) onDeleteTransfer(item.transfer_id)
  }

  return <main>
    <div className="page-head"><div><p className="eyebrow">BANK FUNDS</p><h1>USDT 资金</h1><p>分开记录 C2C 买入与实际提链，逐笔追踪订阅的真实人民币成本。</p></div></div>
    <section className="balance-overview panel bank-summary">
        <div className="balance-heading"><div><span>可用余额</span><strong>{balance.toFixed(2)} <small>USDT</small></strong></div><span className={`balance-badge ${balance < 20 ? 'low' : ''}`}>{balance < 20 ? '余额偏低' : '余额充足'}</span></div>
        <div className="balance-metrics"><div><span>剩余批次</span><b>{lots.length} 个</b></div><div><span>余额成本</span><b>¥{costBasis.toFixed(2)}</b></div><div><span>平均成本</span><b>¥{averageRate.toFixed(2)}</b></div><div><span>待提链记录</span><b>{pendingPurchases.length} 笔</b></div><div><span>待提链资金</span><b>{pendingUsdt.toFixed(2)} USDT</b></div></div>
        <div className="lot-list"><div className="picker-head"><b>可用批次</b><small>订阅扣款按先进先出</small></div>{lots.length ? lots.map(lot => <div className="lot-row" key={lot.id}><span>批次 #{lot.id}<small>{new Date(lot.created_at).toLocaleDateString('zh-CN')}</small></span><b>{lot.remaining_usdt.toFixed(2)} USDT<small>¥{lot.c2c_rate.toFixed(2)} / USDT</small></b></div>) : <p className="muted-copy">暂无可用到账批次</p>}</div>
    </section>
    <section className="fund-actions-grid">
      <C2CPurchaseForm subscriptions={subscriptions} pendingPurchases={pendingPurchases} onQuote={onQuote} onCreatePurchase={onCreatePurchase} />
      <TransferForm pendingPurchases={pendingPurchases} onDeletePurchase={onDeletePurchase} onTransfer={onTransfer} />
    </section>

    <section className="panel history">
      <div className="section-title"><div><p className="eyebrow">LEDGER</p><h2>资金流水</h2></div><span>{shown.length} 笔</span></div>
      <div className="ledger-filters">{filters.map(([id, label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}</button>)}</div>
      {shown.length ? <div className="transaction-list">{shown.map(item => <details className="transaction-row" key={item.id}>
        <summary><span className={`transaction-icon ${item.type}`}>{item.usdt_delta > 0 ? '+' : '−'}</span><span className="transaction-main"><b>{item.title}</b><small>{new Date(item.created_at).toLocaleString('zh-CN')}</small></span><span className="transaction-cost"><b className={item.usdt_delta > 0 ? 'positive' : 'negative'}>{item.usdt_delta > 0 ? '+' : ''}{item.usdt_delta.toFixed(2)} USDT</b><small>¥{item.cny_amount.toFixed(2)}</small></span><span className="expand-mark">⌄</span></summary>
        <div className="transaction-detail">{item.type === 'deposit' ? <>
          <div><span>合并买入</span><b>{item.details.purchased_usdt.toFixed(2)} USDT</b></div>
          <div><span>单次提链费</span><b>{item.details.chain_fee.toFixed(2)} USDT</b></div>
          <div><span>实际到账</span><b>{item.details.actual_received.toFixed(2)} USDT</b></div>
          <div><span>已用于扣款</span><b>{item.used_usdt.toFixed(2)} USDT</b></div>
          {item.details.items.map(part => <div className="transfer-item" key={part.deposit_id}><span>买入 #{part.purchase_id}<small>¥{part.cny_amount.toFixed(2)} · ¥{part.c2c_rate.toFixed(2)}/USDT</small></span><b>{part.purchased_usdt.toFixed(2)} − {part.fee_allocated.toFixed(2)} = {part.actual_received.toFixed(2)} USDT</b></div>)}
          <div className="transaction-danger"><span>{item.deletable ? '删除后关联买入将退回待提链池' : '已有批次参与扣款，整笔提链记录受保护'}</span>{item.deletable && <button type="button" className="danger-button" onClick={() => removeTransfer(item)}>删除提链记录</button>}</div>
        </> : <>
          <div><span>扣款后余额</span><b>{item.balance_after.toFixed(2)} USDT</b></div>
          {item.details.original_price != null && <div><span>订阅原价</span><b>{item.details.original_price.toFixed(2)} {item.details.original_currency}</b></div>}
          {item.allocations.map(allocation => <div key={`${item.id}-${allocation.deposit_id}`}><span>使用批次 #{allocation.deposit_id}</span><b>{allocation.usdt_amount.toFixed(2)} × ¥{allocation.c2c_rate.toFixed(2)} = ¥{allocation.cny_cost.toFixed(2)}</b></div>)}
        </>}</div>
      </details>)}</div> : <div className="empty compact"><span>₮</span><b>暂无相关流水</b><p>完成提链到账或订阅扣款后，明细会显示在这里。</p></div>}
    </section>
  </main>
}
