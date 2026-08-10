export default function CostBreakdown({ cost }) {
  if (!cost) return null
  const bank = cost.payment_method === 'bank_card'
  return <div className="cost-breakdown">
    <div><span>原价</span><b>{cost.original_price.toFixed(2)} {cost.original_currency}</b></div>
    <div><span>换算汇率</span><b>{cost.conversion_rate.toFixed(4)}</b></div>
    {bank && <>
      <div><span>3% 手续费后</span><b>{cost.required_usdt.toFixed(4)} USDT</b></div>
      <div><span>续费队列</span><b>第 {cost.queue_position} 项</b></div>
      <div><span>前序账单预留</span><b>{cost.reserved_before_usdt.toFixed(4)} USDT</b></div>
      <div><span>当前可用</span><b>{cost.available_for_charge_usdt.toFixed(4)} USDT</b></div>
      <div><span>当前覆盖</span><b>{cost.covered_usdt.toFixed(4)} USDT</b></div>
      {cost.allocations.map(allocation => <div className="allocation-row" key={allocation.deposit_id}><span>批次 #{allocation.deposit_id}</span><b>{allocation.usdt_amount.toFixed(4)} × ¥{allocation.c2c_rate.toFixed(4)} = ¥{allocation.cny_cost.toFixed(2)}</b></div>)}
      {cost.shortfall_usdt > 0 && <div className="cost-shortfall"><span>余额缺口</span><b>{cost.shortfall_usdt.toFixed(4)} USDT</b></div>}
    </>}
    <div className="cost-total"><span>{bank && cost.cny_cost == null ? '当前批次已覆盖成本' : '预计人民币成本'}</span><b>¥{(cost.cny_cost ?? cost.covered_cny_cost ?? 0).toFixed(2)}</b></div>
    <code>按续费日期共享余额预演：{cost.formula}</code>
  </div>
}
