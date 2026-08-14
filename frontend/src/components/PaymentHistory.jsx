import { useState } from 'react'

const filters = [['all', '全部'], ['alipay', '支付宝'], ['bank_card', 'USDT 银行卡']]

export default function PaymentHistory({ items }) {
  const [filter, setFilter] = useState('all')
  const shown = filter === 'all' ? items : items.filter(item => item.payment_method === filter)
  return <section className="panel payment-history"><div className="section-title"><div><p className="eyebrow">PAYMENTS</p><h2>扣款记录</h2></div><span>{shown.length} 笔</span></div><div className="ledger-filters">{filters.map(([id, label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}</button>)}</div>
    {shown.length ? <div className="transaction-list">{shown.map(item => <details className="transaction-row" key={item.id}><summary><span className={`transaction-icon payment-${item.payment_method}`}>{item.payment_method === 'alipay' ? '支' : '₮'}</span><span className="transaction-main"><b>{item.subscription_name}</b><small>{new Date(item.created_at).toLocaleString('zh-CN')} · {item.payment_method === 'alipay' ? '支付宝' : 'USDT 银行卡'}</small></span><span className="transaction-cost"><b>¥{item.cny_cost.toFixed(2)}</b><small>{item.charged_usdt == null ? `${item.original_price.toFixed(2)} ${item.original_currency}` : `${item.charged_usdt.toFixed(2)} USDT`}</small></span><span className="expand-mark">⌄</span></summary><div className="transaction-detail"><div><span>账期</span><b>{item.billing_date} → {item.next_billing_date}</b></div><div><span>订阅原价</span><b>{item.original_price.toFixed(2)} {item.original_currency}</b></div>{item.payment_method === 'alipay' ? <div><span>换算汇率</span><b>{item.conversion_rate.toFixed(2)}</b></div> : item.allocations.map(allocation => <div key={`${item.id}-${allocation.deposit_id}`}><span>使用批次 #{allocation.deposit_id}</span><b>{allocation.usdt_amount.toFixed(2)} × ¥{allocation.c2c_rate.toFixed(2)} = ¥{allocation.cny_cost.toFixed(2)}</b></div>)}</div></details>)}</div> : <div className="empty compact"><span>✓</span><b>暂无扣款记录</b><p>确认订阅扣款后，支付明细会显示在这里。</p></div>}
  </section>
}
