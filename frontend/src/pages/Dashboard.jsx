import StatCard from '../components/StatCard'
import NotificationOverview from '../components/NotificationOverview'
import PaymentHistory from '../components/PaymentHistory'

const timeGreeting = hour => {
  if (hour < 5) return '夜深了，订阅支出依然一目了然。'
  if (hour < 12) return '早上好，今天也要精明消费。'
  if (hour < 18) return '下午好，别忘了看看近期续费。'
  return '晚上好，今天的订阅成本都在这里。'
}

export default function Dashboard({ subscriptions, charges, notifications, balance, loading, onNavigate }) {
  const now = new Date()
  const plannedCost = item => item.payment_method === 'bank_card'
    ? (item.cost?.estimated_cny_cost ?? item.cost?.cny_cost)
    : item.cost?.cny_cost
  const monthly = item => {
    const cost = plannedCost(item) || 0
    return item.billing_cycle === 'yearly' ? cost / 12 : item.billing_cycle === 'custom' ? cost * 30 / item.custom_days : cost
  }
  const monthCost = subscriptions.reduce((sum, item) => sum + monthly(item), 0)
  const annualCost = monthCost * 12
  const alipay = subscriptions.filter(item => item.payment_method === 'alipay').reduce((sum, item) => sum + monthly(item), 0)
  const bank = subscriptions.filter(item => item.payment_method === 'bank_card').reduce((sum, item) => sum + monthly(item), 0)
  const incompleteCount = subscriptions.filter(item => item.payment_method === 'bank_card' && item.cost?.coverage_status !== 'sufficient').length
  const upcoming = subscriptions.filter(item => { const days = (new Date(`${item.next_billing_date}T00:00:00`) - now) / 86400000; return days >= -1 && days <= 7 }).slice(0, 5)
  return <main>
    <div className="hero"><div><p className="eyebrow">OVERVIEW</p><h1>{timeGreeting(now.getHours())}</h1><p>一站式掌握所有订阅与支付成本。</p></div><button className="primary" onClick={() => onNavigate('subscriptions')}>＋ 添加订阅</button></div>
    <section className="stats-grid">
      <StatCard label="月均支出" value={loading ? '—' : `¥${monthCost.toFixed(2)}`} hint={`支付宝折算 ¥${alipay.toFixed(0)} · 银行卡预计 ¥${bank.toFixed(0)}`} icon="¥" tone="blue" />
      <StatCard label="预计年支出" value={loading ? '—' : `¥${annualCost.toFixed(2)}`} hint="包含银行卡余额缺口估值" icon="↗" tone="violet" />
      <StatCard label="USDT 余额" value={loading ? '—' : balance.toFixed(2)} hint={balance < 20 ? '余额偏低，请及时充值' : '余额状态良好'} icon="₮" tone={balance < 20 ? 'orange' : 'green'} />
      <StatCard label="活跃订阅" value={loading ? '—' : subscriptions.length} hint={`${upcoming.length} 项将在 7 天内续费`} icon="▦" tone="pink" />
    </section>
    <section className="dashboard-grid">
      <article className="panel upcoming-panel"><div className="section-title"><div><p className="eyebrow">UPCOMING</p><h2>即将续费</h2></div><button className="text-btn" onClick={() => onNavigate('subscriptions')}>查看全部 →</button></div>
        {upcoming.length ? <div className="upcoming-list">{upcoming.map(item => { const days = Math.max(0, Math.ceil((new Date(`${item.next_billing_date}T00:00:00`) - now) / 86400000)); const cost = plannedCost(item); return <div key={item.id}><span className="mini-avatar">{item.name[0]}</span><div><b>{item.name}</b><small>{item.next_billing_date} · {item.payment_method === 'alipay' ? '支付宝' : 'USDT 银行卡'}{item.cost?.shortfall_usdt > 0 ? ` · 缺 ${item.cost.shortfall_usdt.toFixed(2)} USDT` : ''}</small></div><strong>{cost == null ? '—' : `¥${cost.toFixed(2)}`}</strong><em>{days === 0 ? '今天' : `${days}天`}</em></div> })}</div> : <div className="empty compact"><span>✓</span><b>未来 7 天暂无续费</b><p>可以安心享受已订阅的服务。</p></div>}
      </article>
      <article className="panel balance-panel"><p className="eyebrow">BANK CARD</p><h2>USDT 余额</h2><div className="balance-orbit"><span>₮</span><strong>{balance.toFixed(2)}</strong><small>USDT</small></div><div className="balance-warning" data-ok={incompleteCount === 0}>{incompleteCount ? `${incompleteCount} 项订阅余额不足` : '余额可覆盖当前银行卡订阅'}</div><button className="secondary full" onClick={() => onNavigate('bank-card')}>管理银行卡余额</button></article>
    </section>
    <NotificationOverview data={notifications} />
    <PaymentHistory items={charges || []} />
  </main>
}
