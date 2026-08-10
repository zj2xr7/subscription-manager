import { useCallback, useEffect, useState } from 'react'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Subscriptions from './pages/Subscriptions'
import BankCard from './pages/BankCard'
import Settings from './pages/Settings'
import { api } from './services/api'

const validPages = ['dashboard', 'subscriptions', 'bank-card', 'settings']

export default function App() {
  const [page, setPage] = useState(() => validPages.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'dashboard')
  const [subscriptions, setSubscriptions] = useState([])
  const [balance, setBalance] = useState(0)
  const [deposits, setDeposits] = useState([])
  const [lots, setLots] = useState([])
  const [transactions, setTransactions] = useState([])
  const [exchangeQuotes, setExchangeQuotes] = useState(null)
  const [settings, setSettings] = useState({ server_chan_key: '', exchange_rate_api_key: '', notification_days_before: 7 })
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)
  const notify = (message, type = 'success') => { setToast({ message, type }); setTimeout(() => setToast(null), 3200) }
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, b, d, availableLots, ledger, config, quotes] = await Promise.all([
        api.subscriptions(), api.balance(), api.deposits(), api.lots(), api.transactions(), api.settings(), api.exchangeQuotes(),
      ])
      setSubscriptions(s); setBalance(b.balance); setDeposits(d); setLots(availableLots)
      setTransactions(ledger); setSettings(config); setExchangeQuotes(quotes)
    } catch (error) { notify(error.message, 'error') } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const handler = () => setPage(validPages.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'dashboard')
    addEventListener('hashchange', handler)
    return () => removeEventListener('hashchange', handler)
  }, [])
  const navigate = target => { location.hash = target; setPage(target) }
  const action = async (promise, message) => {
    try { await promise; await load(); notify(message) }
    catch (error) { notify(error.message, 'error'); throw error }
  }
  const pages = {
    dashboard: <Dashboard subscriptions={subscriptions} balance={balance} lots={lots} loading={loading} onNavigate={navigate} />,
    subscriptions: <Subscriptions items={subscriptions} onCreate={data => action(api.createSubscription(data), '订阅已添加')} onUpdate={(id, data) => action(api.updateSubscription(id, data), '订阅已更新')} onDelete={item => confirm(`确定删除“${item.name}”吗？`) && action(api.deleteSubscription(item.id), '订阅已删除')} onCharge={item => confirm(`确认处理“${item.name}”本期扣款并推进续费日期？`) && action(api.chargeSubscription(item.id), '扣款已完成')} />,
    'bank-card': <BankCard balance={balance} deposits={deposits} lots={lots} transactions={transactions} subscriptions={subscriptions} onQuote={api.topUpQuote} onDeposit={data => action(api.deposit(data), '充值已记录')} />,
    settings: <Settings settings={settings} exchangeQuotes={exchangeQuotes} onRefreshRates={async key => { const quotes = await api.exchangeQuotes(true, key); setExchangeQuotes(quotes); notify(quotes.source === 'api' ? '实时汇率已更新' : 'Key 校验未通过，当前继续显示参考汇率', quotes.source === 'api' ? 'success' : 'error') }} onSave={async data => { await action(api.saveSettings(data), '设置已保存'); const quotes = await api.exchangeQuotes(true, data.exchange_rate_api_key || ''); setExchangeQuotes(quotes) }} onTest={async key => { try { await api.testNotification(key); notify('测试通知已发送') } catch (error) { notify(error.message, 'error'); throw error } }} />,
  }
  return <><Navbar page={page} onNavigate={navigate} />{loading && <div className="loading-line" />}{pages[page]}{toast && <div className={`toast ${toast.type}`}>{toast.type === 'success' ? '✓' : '!'} {toast.message}</div>}<footer>看清每一笔订阅，掌握每一分成本。</footer></>
}
