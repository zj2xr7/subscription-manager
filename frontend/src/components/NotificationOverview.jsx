const statusText = { never: '尚未执行', running: '检查中', success: '检查完成', failed: '检查异常', disabled: '通道未启用' }

const localTime = value => new Date(value && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? `${value}Z` : value)
const formatTime = value => value ? localTime(value).toLocaleString('zh-CN') : '暂无记录'

export default function NotificationOverview({ data }) {
  const scheduler = data?.scheduler
  const deliveries = data?.recent_deliveries || []
  const reminders = data?.next_reminders || []
  const resultText = !scheduler ? '—' : scheduler.status === 'running' ? '正在检查' : scheduler.due_count === 0
    ? '本次无需发送' : `${scheduler.sent_count} 成功 · ${scheduler.failed_count} 失败 · ${scheduler.due_count} 应发送`
  return <section className="panel notification-panel">
    <div className="section-title"><div><p className="eyebrow">NOTIFICATIONS</p><h2>通知状态</h2></div><span className={`notification-state ${data?.health || 'waiting'}`}>{data?.health_message || '正在读取通知状态'}</span></div>
    <div className="notification-metrics">
      <div><span>提醒节点</span><b>{data?.notification_days_before?.map(day => day === 0 ? '当天' : `${day} 天前`).join(' · ') || '—'}</b></div>
      <div><span>执行计划</span><b>每天 09:00 · Asia/Shanghai</b></div>
      <div><span>最近检查</span><b>{statusText[scheduler?.status] || '读取中'} · {formatTime(scheduler?.last_completed_at)}</b></div>
      <div><span>本次结果</span><b>{resultText}</b></div>
    </div>
    {scheduler?.error_message && <div className="notification-error"><b>{scheduler.error_message}</b><span>请重新启动应用；如仍异常，可在设置中发送测试通知。</span></div>}
    <div className="notification-columns">
      <div><div className="notification-subhead"><b>下一批提醒</b><span>{reminders.length} 项</span></div>
        {reminders.length ? <div className="notification-list">{reminders.slice(0, 6).map(item => <div key={`${item.subscription_id}-${item.billing_date}-${item.lead_days}`}><span><b>{item.subscription_name}</b><small>{item.billing_date} 续费 · 提前 {item.lead_days} 天</small></span><time>{item.scheduled_for}</time></div>)}</div> : <p className="notification-empty">暂无待发送提醒</p>}
      </div>
      <div><div className="notification-subhead"><b>最近发送</b><span>{deliveries.length} 条</span></div>
        {deliveries.length ? <div className="notification-list">{deliveries.slice(0, 6).map(item => <div key={item.id}><span><b>{item.subscription_name}</b><small>{item.kind === 'test' ? '测试通知' : `${item.billing_date} · ${item.is_catch_up ? '延迟补发' : `提前 ${item.lead_days} 天`}`}{item.error_message ? ` · ${item.error_message}` : ''}</small></span><em className={item.status}>{item.status === 'sent' ? '成功' : item.status === 'failed' ? '失败' : '发送中'}</em></div>)}</div> : <p className="notification-empty">暂无发送记录</p>}
      </div>
    </div>
  </section>
}
