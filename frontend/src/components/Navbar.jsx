const navItems = [
  ['dashboard', '概览', '⌂'],
  ['subscriptions', '订阅管理', '▦'],
  ['bank-card', '银行卡', '◫'],
  ['settings', '设置', '⚙'],
]

export default function Navbar({ page, onNavigate }) {
  return <header className="navbar">
    <button className="brand" onClick={() => onNavigate('dashboard')}>
      <span className="brand-mark">S</span><span>SubManager</span>
    </button>
    <nav>{navItems.map(([id, label, icon]) =>
      <button key={id} className={page === id ? 'active' : ''} onClick={() => onNavigate(id)}>
        <span>{icon}</span>{label}
      </button>
    )}</nav>
  </header>
}
