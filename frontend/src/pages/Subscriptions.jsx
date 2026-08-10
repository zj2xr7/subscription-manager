import { useMemo, useState } from 'react'
import SubscriptionCard from '../components/SubscriptionCard'
import SubscriptionForm from '../components/SubscriptionForm'
import PaymentHistory from '../components/PaymentHistory'

export default function Subscriptions({ items, charges, onCreate, onUpdate, onDelete, onCharge }) {
  const [modal, setModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [filter, setFilter] = useState('all')
  const shown = useMemo(() => items.filter(x => filter === 'all' || x.payment_method === filter), [items, filter])
  const save = async data => { editing ? await onUpdate(editing.id, data) : await onCreate(data); setModal(false); setEditing(null) }
  return <main>
    <div className="page-head"><div><p className="eyebrow">SUBSCRIPTIONS</p><h1>订阅管理</h1><p>追踪每一项服务，清晰了解真实支付成本。</p></div><button className="primary" onClick={() => setModal(true)}>＋ 添加订阅</button></div>
    <div className="toolbar"><div className="filter-tabs">{[['all','全部'],['alipay','支付宝'],['bank_card','USDT 银行卡']].map(([id,label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}<small>{id === 'all' ? items.length : items.filter(x => x.payment_method === id).length}</small></button>)}</div><span>共 {shown.length} 项</span></div>
    {shown.length ? <section className="subscription-grid">{shown.map(item => <SubscriptionCard key={item.id} item={item} onEdit={x => { setEditing(x); setModal(true) }} onDelete={onDelete} onCharge={onCharge} />)}</section> : <div className="empty"><span>＋</span><b>还没有订阅</b><p>添加第一项订阅，开始统一管理支出。</p><button className="primary" onClick={() => setModal(true)}>添加订阅</button></div>}
    <PaymentHistory items={charges} />
    {modal && <SubscriptionForm item={editing} onClose={() => { setModal(false); setEditing(null) }} onSave={save} />}
  </main>
}
