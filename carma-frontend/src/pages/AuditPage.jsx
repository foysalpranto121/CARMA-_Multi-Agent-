import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, ShieldX, ListTree } from 'lucide-react';
import { auditApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader,
  fmtDate, fmtTime, toneFor,
} from '../components/ui';

export default function AuditPage() {
  const [entryType, setEntryType] = useState('');
  const [replayId, setReplayId] = useState('');

  const entries = useQuery({
    queryKey: ['audit-entries', entryType],
    queryFn: async () => unwrap((await auditApi.entries({
      page_size: 100,
      ordering: '-sequence_num',
      ...(entryType ? { entry_type: entryType } : {}),
    })).data),
    refetchInterval: 15_000,
  });

  const chain = useQuery({
    queryKey: ['audit-chain'],
    queryFn: async () => (await auditApi.verifyChain()).data,
  });

  const replay = useQuery({
    queryKey: ['audit-replay', replayId],
    queryFn: async () => (await auditApi.replay(replayId)).data,
    enabled: Boolean(replayId),
  });

  const types = ['retrieval', 'plan', 'scv', 'action', 'escalation', 'repair', 'experiment'];

  return (
    <div className="page-wrapper">
      <PageHeader
        title="AUDIT LOG"
        subtitle="Append-only SHA-256 hash chain. Every retrieval, plan, verdict and action is tamper-evident."
        actions={(
          <div className="flex items-center gap-sm">
            {chain.isLoading ? <Badge tone="cyan">checking…</Badge>
              : chain.data?.valid
                ? <Badge tone="green"><ShieldCheck size={10} /> chain intact</Badge>
                : <Badge tone="rose"><ShieldX size={10} /> chain broken</Badge>}
          </div>
        )}
      />

      {chain.data && !chain.data.valid && (
        <div className="glass-card" style={{ marginBottom: 'var(--space-md)',
                 borderColor: 'rgba(255,61,110,0.4)' }}>
          <div style={{ fontSize: 12, color: 'var(--holo-rose)' }}>{chain.data.message}</div>
        </div>
      )}

      <div className="dashboard-grid">
        <div className="glass-card col-span-8">
          <div className="flex items-center justify-between mb-md">
            <div className="holo-subtitle">CHAIN ENTRIES</div>
            <div className="flex items-center gap-sm">
              <select className="holo-select" value={entryType}
                      onChange={(e) => setEntryType(e.target.value)}
                      aria-label="Filter by entry type">
                <option value="">All types</option>
                {types.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          {entries.isLoading ? <LoadingState label="Loading audit entries…" />
            : entries.error ? <ErrorState error={entries.error} onRetry={entries.refetch} />
            : (
            <DataTable
              columns={[
                { key: 'seq', header: '#', render: (r) => r.sequence_num },
                { key: 'time', header: 'TIMESTAMP',
                  render: (r) => (
                    <span style={{ color: 'var(--text-muted)' }}>{fmtTime(r.timestamp)}</span>
                  ) },
                { key: 'type', header: 'TYPE',
                  render: (r) => <Badge tone="cyan">{r.entry_type}</Badge> },
                { key: 'actor', header: 'ACTOR',
                  render: (r) => r.actor_name ?? r.actor_agent ?? 'system' },
                { key: 'hash', header: 'ENTRY HASH',
                  render: (r) => (
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      {String(r.entry_hash ?? '').slice(0, 16)}…
                    </span>
                  ) },
                { key: 'replay', header: '',
                  render: (r) => (r.adaptation_id
                    ? (
                      <button className="btn btn-ghost" style={{ fontSize: 9 }}
                              onClick={() => setReplayId(r.adaptation_id)}>
                        <ListTree size={10} /> replay
                      </button>
                    ) : null) },
              ]}
              rows={entries.data ?? []}
              empty="No audit entries yet."
            />
          )}
        </div>

        <div className="glass-card col-span-4">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            {replayId ? 'REPLAY' : 'CHAIN PROPERTIES'}
          </div>

          {replayId ? (
            <>
              <button className="btn btn-ghost" style={{ marginBottom: 'var(--space-md)', fontSize: 10 }}
                      onClick={() => setReplayId('')}>
                ← back to chain
              </button>
              {replay.isLoading ? <LoadingState /> : (
                <div className="log-terminal">
                  {(replay.data?.entries ?? []).map((entry) => (
                    <div key={entry.id} className="log-entry">
                      <span className="log-time">#{entry.sequence_num}</span>
                      <span className="log-type">{String(entry.entry_type ?? '').toUpperCase().slice(0, 8)}</span>
                      <span className="log-msg">
                        {entry.payload ? JSON.stringify(entry.payload).slice(0, 90) : '—'}
                      </span>
                    </div>
                  ))}
                  {(replay.data?.entries ?? []).length === 0 && (
                    <div style={{ color: 'var(--text-muted)' }}>No entries for this adaptation.</div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
              <div>
                <div className="kpi-label">ENTRIES</div>
                <div className="kpi-value cyan">{(entries.data ?? []).length}</div>
              </div>
              <div>
                <div className="kpi-label">CHAIN STATE</div>
                <div style={{ marginTop: 6 }}>
                  {chain.isLoading ? <Badge tone="cyan">checking…</Badge>
                    : chain.data?.valid
                      ? <Badge tone="green">intact</Badge>
                      : <Badge tone="rose">broken at #{chain.data?.broken_at}</Badge>}
                </div>
              </div>
              <div>
                <div className="kpi-label">VERIFICATION</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.6 }}>
                  Each entry stores the SHA-256 hash of the previous entry. Modifying
                  or removing any entry breaks every hash after it, which the
                  verification endpoint reports with the exact sequence number.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
