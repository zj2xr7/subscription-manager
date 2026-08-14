import CostBreakdown from './CostBreakdown'

const currencySymbols = { USD: '$', GBP: '£', CAD: 'C$', CNY: '¥' }
const cycleNames = { monthly: '每月', yearly: '每年', custom: '自定义' }

export default function SubscriptionCard({ item, onEdit, onDelete, onCharge }) {
  const days = Math.ceil((new Date(`${item.next_billing_date}T00:00:00`) - new Date()) / 86400000)
  const dueText = days < 0 ? `已逾期 ${Math.abs(days)} 天` : days === 0 ? '今天续费' : `${days} 天后续费`
  const bank = item.payment_method === 'bank_card'
  const insufficient = bank && item.cost?.coverage_status !== 'sufficient'
  const shownCost = item.cost?.estimated_cny_cost ?? item.cost?.cny_cost ?? item.cost?.covered_cny_cost
  return <article className="subscription-card">
    <div className="card-top"><div className="service-avatar">{item.name.slice(0, 1).toUpperCase()}</div><div className="card-actions"><button title="编辑" onClick={() => onEdit(item)}>✎</button><button title="删除" onClick={() => onDelete(item)}>×</button></div></div>
    <h3>{item.name}</h3>
    <p className="price">{currencySymbols[item.currency]}{item.price.toFixed(2)} <small>{item.currency} · {cycleNames[item.billing_cycle]}</small></p>
    <div className="tag-row"><span className={`method-tag ${item.payment_method}`}>{bank ? 'USDT 银行卡' : '支付宝'}</span><span className={days <= 7 ? 'due-tag urgent' : 'due-tag'}>{dueText}</span></div>
    <div className="card-cost"><span>预计成本</span><strong>¥{shownCost?.toFixed(2) || '0.00'}</strong></div>
    {insufficient && <div className="inline-warning">{item.cost.reserved_before_usdt > 0 && `前序账单已预留 ${item.cost.reserved_before_usdt.toFixed(2)} USDT，`}还缺 {item.cost.shortfall_usdt.toFixed(2)} USDT，请先充值</div>}
    <details><summary>查看计算明细</summary><CostBreakdown cost={item.cost} /></details>
    <button className="charge-btn" disabled={insufficient} onClick={() => onCharge(item)}>{insufficient ? '余额不足' : '确认本期扣款'}</button>
  </article>
}
