import { useMemo, useState } from 'react'
import DepositForm from '../components/DepositForm'

const filters = [['all', '全部'], ['deposit', '充值'], ['charge', '订阅扣款'], ['adjustment', '历史调整']]

export default function BankCard({ balance, lots, transactions, subscriptions, onQuote, onDeposit }) {
  const [filter, setFilter] = useState('all')
  const shown = filter === 'all' ? transactions : transactions.filter(item => item.type === filter)
  const costBasis = useMemo(() => lots.reduce((sum, lot) => sum + lot.remaining_usdt * lot.c2c_rate, 0), [lots])
  const averageRate = balance > 0 ? costBasis / balance : 0
  return <main>
    <div className="page-head"><div><p className="eyebrow">BANK FUNDS</p><h1>USDT 资金</h1><p>按充值批次管理余额，逐笔追踪订阅的真实人民币成本。</p></div></div>
    <section className="bank-layout">
      <div className="balance-overview panel"><div className="balance-heading"><div><span>可用余额</span><strong>{balance.toFixed(4)} <small>USDT</small></strong></div><span className={`balance-badge ${balance < 20 ? 'low' : ''}`}>{balance < 20 ? '余额偏低' : '余额充足'}</span></div><div className="balance-metrics"><div><span>剩余批次</span><b>{lots.length} 个</b></div><div><span>余额成本</span><b>¥{costBasis.toFixed(2)}</b></div><div><span>平均成本</span><b>¥{averageRate.toFixed(4)}</b></div></div><div className="lot-list"><div className="picker-head"><b>可用批次</b><small>扣款按先进先出</small></div>{lots.length ? lots.map(lot => <div className="lot-row" key={lot.id}><span>批次 #{lot.id}<small>{new Date(lot.created_at).toLocaleDateString('zh-CN')}</small></span><b>{lot.remaining_usdt.toFixed(4)} USDT<small>¥{lot.c2c_rate.toFixed(4)} / USDT</small></b></div>) : <p className="muted-copy">暂无可用充值批次</p>}</div></div>
      <DepositForm balance={balance} subscriptions={subscriptions} onQuote={onQuote} onSubmit={onDeposit} />
    </section>
    <section className="panel history"><div className="section-title"><div><p className="eyebrow">LEDGER</p><h2>资金流水</h2></div><span>{shown.length} 笔</span></div><div className="ledger-filters">{filters.map(([id, label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}</button>)}</div>
      {shown.length ? <div className="transaction-list">{shown.map(item => <details className="transaction-row" key={item.id}><summary><span className={`transaction-icon ${item.type}`}>{item.usdt_delta > 0 ? '+' : '−'}</span><span className="transaction-main"><b>{item.title}</b><small>{new Date(item.created_at).toLocaleString('zh-CN')}</small></span><span className="transaction-cost"><b className={item.usdt_delta > 0 ? 'positive' : 'negative'}>{item.usdt_delta > 0 ? '+' : ''}{item.usdt_delta.toFixed(4)} USDT</b><small>¥{item.cny_amount.toFixed(2)}</small></span><span className="expand-mark">⌄</span></summary><div className="transaction-detail">{item.type === 'deposit' ? <><div><span>买入数量</span><b>{item.details.purchased_usdt.toFixed(4)} USDT</b></div><div><span>上链费</span><b>{item.details.chain_fee.toFixed(4)} USDT</b></div><div><span>剩余批次</span><b>{item.details.remaining_usdt.toFixed(4)} USDT</b></div></> : <><div><span>扣款后余额</span><b>{item.balance_after.toFixed(4)} USDT</b></div>{item.details.original_price != null && <div><span>订阅原价</span><b>{item.details.original_price.toFixed(2)} {item.details.original_currency}</b></div>}{item.allocations.map(allocation => <div key={`${item.id}-${allocation.deposit_id}`}><span>使用批次 #{allocation.deposit_id}</span><b>{allocation.usdt_amount.toFixed(4)} × ¥{allocation.c2c_rate.toFixed(4)} = ¥{allocation.cny_cost.toFixed(2)}</b></div>)}</>}</div></details>)}</div> : <div className="empty compact"><span>₮</span><b>暂无相关流水</b><p>充值或订阅扣款后，明细会显示在这里。</p></div>}
    </section>
  </main>
}
