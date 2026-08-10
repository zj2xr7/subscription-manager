export default function StatCard({ label, value, hint, icon, tone = 'blue' }) {
  return <article className="stat-card">
    <div className={`stat-icon ${tone}`}>{icon}</div>
    <div><p>{label}</p><strong>{value}</strong><small>{hint}</small></div>
  </article>
}
