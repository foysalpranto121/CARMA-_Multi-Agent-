import { AlertCircle, Inbox, Loader2 } from 'lucide-react';

/* ── Formatting helpers ──────────────────────────────────────── */
export const fmtNum = (value, digits = 0) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : Number(value).toLocaleString(undefined, {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
      });

export const fmtPct = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : `${(Number(value) * 100).toFixed(digits)}%`;

export const fmtPctValue = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : `${Number(value).toFixed(digits)}%`;

export const fmtDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toISOString().slice(0, 19).replace('T', ' ');
};

export const fmtTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toISOString().slice(11, 19);
};

/* ── Status → colour mapping ─────────────────────────────────── */
const TONES = {
  success: 'green', completed: 'green', resolved: 'green', approved: 'green',
  ok: 'green', active: 'green', running: 'cyan', info: 'cyan',
  pending: 'gold', assigned: 'gold', escalated: 'gold', repair: 'gold',
  violation: 'rose', failed: 'rose', rejected: 'rose', error: 'rose',
  critical: 'rose', unreachable: 'rose', degraded: 'gold',
  cancelled: 'violet', paused: 'violet', deferred: 'violet',
  modified: 'violet', validated: 'violet',
};

export const toneFor = (status) => TONES[String(status ?? '').toLowerCase()] ?? 'cyan';

export const Badge = ({ children, tone = 'cyan', style }) => (
  <span className={`badge badge-${tone}`} style={style}>{children}</span>
);

/* ── Layout blocks ───────────────────────────────────────────── */
export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex items-center justify-between mb-lg">
      <div>
        <div className="holo-subtitle" style={{ marginBottom: 6 }}>{title}</div>
        {subtitle && (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{subtitle}</div>
        )}
      </div>
      {actions && <div className="flex items-center gap-sm">{actions}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, actions, children, className = '', style }) {
  return (
    <div className={`glass-card ${className}`} style={style}>
      {(title || actions) && (
        <div className="flex items-center justify-between mb-md">
          <div>
            {title && <div className="holo-subtitle">{title}</div>}
            {subtitle && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                {subtitle}
              </div>
            )}
          </div>
          {actions && <div className="flex items-center gap-sm">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

/* ── Data table ──────────────────────────────────────────────── */
export function DataTable({ columns, rows, empty = 'No records yet.', rowKey }) {
  if (!rows || rows.length === 0) return <EmptyState message={empty} />;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="holo-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={col.headerStyle}>{col.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey ? rowKey(row, index) : (row.id ?? index)}>
              {columns.map((col) => (
                <td key={col.key} style={col.cellStyle}>{col.render(row, index)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── States ──────────────────────────────────────────────────── */
export const LoadingState = ({ label = 'Loading…' }) => (
  <div className="flex items-center justify-center gap-sm"
       style={{ padding: 'var(--space-xl)', color: 'var(--text-muted)', fontSize: 12 }}>
    <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> {label}
  </div>
);

export const EmptyState = ({ message = 'Nothing here yet.', hint }) => (
  <div style={{
    padding: 'var(--space-xl)', textAlign: 'center',
    color: 'var(--text-muted)', fontSize: 12,
  }}>
    <Inbox size={20} style={{ opacity: 0.5, marginBottom: 8 }} />
    <div>{message}</div>
    {hint && (
      <div style={{ marginTop: 6, fontSize: 11, opacity: 0.75 }}>{hint}</div>
    )}
  </div>
);

export const ErrorState = ({ error, onRetry }) => (
  <div style={{
    padding: 'var(--space-lg)', display: 'flex', gap: 10, alignItems: 'flex-start',
    border: '1px solid rgba(255,61,110,0.3)', borderRadius: 'var(--radius-md)',
    background: 'rgba(255,61,110,0.06)', color: 'var(--holo-rose)', fontSize: 12,
  }}>
    <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
    <div style={{ flex: 1 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Could not load data</div>
      <div style={{ color: 'var(--text-secondary)' }}>
        {error?.response?.data?.detail
          ?? error?.message
          ?? 'The API request failed.'}
      </div>
    </div>
    {onRetry && (
      <button className="btn btn-ghost" onClick={onRetry}>RETRY</button>
    )}
  </div>
);

/* ── Metric bar ──────────────────────────────────────────────── */
export const MetricBar = ({ label, value, display, color = 'cyan' }) => {
  const pct = value === null || value === undefined ? 0
    : Math.max(0, Math.min(100, Number(value)));
  return (
    <div className="metric-bar-wrap">
      <div className="metric-bar-label">
        <span>{label}</span>
        <span className="mono-text">{display}</span>
      </div>
      <div className="metric-bar-track">
        <div className={`metric-bar-fill ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};
