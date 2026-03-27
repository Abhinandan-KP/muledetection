import './SummaryStats.css'

const CARDS = [
  {
    key: 'total',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
    label: 'Accounts Analyzed',
    getValue: s => s.total_accounts_analyzed.toLocaleString(),
    theme: 'default',
  },
  {
    key: 'flagged',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    label: 'Suspicious Accounts',
    getValue: s => s.suspicious_accounts_flagged.toLocaleString(),
    theme: 'danger',
  },
  {
    key: 'rings',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="10"/>
        <circle cx="12" cy="12" r="6"/>
        <circle cx="12" cy="12" r="2"/>
      </svg>
    ),
    label: 'Fraud Rings Detected',
    getValue: s => s.fraud_rings_detected.toLocaleString(),
    theme: 'accent',
  },
  {
    key: 'time',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
    ),
    label: 'Processing Time',
    getValue: s => `${s.processing_time_seconds}s`,
    theme: 'teal',
  },
]

const NET_STATS = [
  { key: 'total_nodes',   label: 'Total Nodes',      format: v => v?.toLocaleString() ?? '—' },
  { key: 'total_edges',   label: 'Total Edges',      format: v => v?.toLocaleString() ?? '—' },
  { key: 'graph_density', label: 'Graph Density',     format: v => v != null ? v.toFixed(4) : '—' },
  { key: 'avg_degree',    label: 'Avg Degree',        format: v => v != null ? v.toFixed(2) : '—' },
  { key: 'connected_components', label: 'Connected Components', format: v => v?.toLocaleString() ?? '—' },
  { key: 'avg_clustering', label: 'Avg Clustering',   format: v => v != null ? v.toFixed(4) : '—' },
]

export default function SummaryStats({ summary }) {
  const net = summary?.network_statistics

  return (
    <div className="stats-section">
      <div className="stats-grid">
        {CARDS.map((card, i) => (
          <div
            key={card.key}
            className={`stat-card ${card.theme}`}
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <div className="stat-icon-wrap">
              {card.icon}
            </div>
            <div className="stat-content">
              <div className="stat-value">{card.getValue(summary)}</div>
              <div className="stat-label">{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      {net && (
        <div className="net-stats-bar">
          <div className="net-stats-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/>
              <line x1="9" y1="6" x2="15" y2="6"/><line x1="6" y1="9" x2="6" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/><line x1="9" y1="18" x2="15" y2="18"/>
            </svg>
            <span>Network Statistics</span>
          </div>
          <div className="net-stats-items">
            {NET_STATS.map(s => (
              <div key={s.key} className="net-stat-item">
                <span className="net-stat-value">{s.format(net[s.key])}</span>
                <span className="net-stat-label">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
