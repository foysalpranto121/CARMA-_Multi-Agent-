import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Play, Pause, Download } from 'lucide-react';
import { auditApi, experimentApi, metricsApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, Panel,
  fmtDate, fmtNum, fmtPctValue, fmtTime, toneFor,
} from '../components/ui';
import { useAuthStore, hasRole } from '../store/authStore';
import { useRunStream } from '../hooks/useRunStream';

export default function ExperimentDetailPage() {
  const { id } = useParams();
  const role = useAuthStore((s) => s.user?.role);
  const canRun = hasRole(role, ['researcher']);
  const queryClient = useQueryClient();

  // Every finished case arrives over the socket; the queries are refreshed
  // from it, and only poll while the socket is down.
  const stream = useRunStream(id, {
    onEvent: (message) => {
      if (message.type === 'case_complete') {
        queryClient.invalidateQueries({ queryKey: ['adaptations', id] });
        queryClient.invalidateQueries({ queryKey: ['run', id] });
      }
      if (message.type === 'progress' && message.status === 'completed') {
        ['run', 'run-result', 'run-audit', 'adaptations'].forEach((key) =>
          queryClient.invalidateQueries({ queryKey: [key, id] }));
      }
    },
  });
  const poll = (interval) => (stream.connected ? false : interval);

  const run = useQuery({
    queryKey: ['run', id],
    queryFn: async () => (await experimentApi.run(id)).data,
    refetchInterval: poll(10_000),
  });

  const result = useQuery({
    queryKey: ['run-result', id],
    queryFn: async () => {
      const res = await experimentApi.results({ run: id, page_size: 1 });
      return unwrap(res.data)[0] ?? null;
    },
  });

  const adaptations = useQuery({
    queryKey: ['adaptations', id],
    queryFn: async () => unwrap((await experimentApi.adaptations({ run: id, page_size: 50 })).data),
    refetchInterval: poll(15_000),
  });

  const audit = useQuery({
    queryKey: ['run-audit', id],
    queryFn: async () => unwrap((await auditApi.entries({ run_id: id, page_size: 50 })).data),
  });

  const action = useMutation({
    mutationFn: ({ verb }) => verb === 'start' ? experimentApi.start(id) : experimentApi.pause(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['run', id] }),
  });

  const data = run.data;

  if (run.isLoading) {
    return <div className="page-wrapper"><LoadingState label="Loading run…" /></div>;
  }
  if (run.error) {
    return <div className="page-wrapper"><ErrorState error={run.error} onRetry={run.refetch} /></div>;
  }
  if (!data) {
    return (
      <div className="page-wrapper">
        <EmptyState message="This run does not exist." />
      </div>
    );
  }

  const res = result.data;
  const adaptationsRows = adaptations.data ?? [];
  const live = stream.progress;
  const progressPct = live ? live.pct : (data.progress_pct ?? 0);
  const doneCases = live ? live.completed : data.completed_cases;
  const totalCases = live ? live.total : data.total_cases;

  return (
    <div className="page-wrapper">
      <div className="mb-md">
        <Link to="/experiments" style={{ display: 'inline-flex', alignItems: 'center',
                                         gap: 6, fontSize: 11, color: 'var(--text-muted)',
                                         textDecoration: 'none' }}>
          <ArrowLeft size={12} /> Back to runs
        </Link>
      </div>

      <PageHeader
        title={`RUN ${data.config_code} · SEED ${data.seed}`}
        subtitle={data.created_by_name ? `Created by ${data.created_by_name}` : 'Experiment run'}
        actions={(
          <div className="flex items-center gap-sm">
            {canRun && data.status === 'pending' && (
              <button className="btn btn-solid" disabled={action.isPending}
                      onClick={() => action.mutate({ verb: 'start' })}>
                <Play size={13} /> Start
              </button>
            )}
            {canRun && data.status === 'running' && (
              <button className="btn btn-primary" disabled={action.isPending}
                      onClick={() => action.mutate({ verb: 'pause' })}>
                <Pause size={13} /> Pause
              </button>
            )}
            <a className="btn btn-ghost" style={{ textDecoration: 'none' }}
               href={experimentApi.exportUrl(data.id)}>
              <Download size={13} /> Export CSV
            </a>
          </div>
        )}
      />

      <div className="kpi-row" style={{ marginBottom: 'var(--space-lg)', gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Status</span>
          <div style={{ marginTop: 8 }}>
            <Badge tone={toneFor(data.status)}>{data.status}</Badge>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>
            {fmtDate(data.started_at ?? data.created_at)}
          </div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">
            Progress {stream.connected && <Badge tone="green" style={{ marginLeft: 6 }}>live</Badge>}
          </span>
          <div className="kpi-value cyan">{progressPct}%</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            {fmtNum(doneCases)}/{fmtNum(totalCases)} cases ·
            {' '}{fmtNum(data.failed_cases)} failed
          </div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Task Success</span>
          <div className="kpi-value green">
            {res?.task_success_rate === null || res?.task_success_rate === undefined
              ? '—' : fmtPctValue(res.task_success_rate * 100)}
          </div>
        </div>
        <div className="glass-card kpi-tile">
          <span className="kpi-label">Violation Rate</span>
          <div className="kpi-value rose">
            {res?.constraint_viol_rate === null || res?.constraint_viol_rate === undefined
              ? '—' : fmtPctValue(res.constraint_viol_rate * 100)}
          </div>
        </div>
      </div>

      {data.error_log && (
        <div className="glass-card" style={{ marginBottom: 'var(--space-lg)',
                 borderColor: 'rgba(255,61,110,0.3)' }}>
          <div className="holo-subtitle" style={{ color: 'var(--holo-rose)', marginBottom: 8 }}>
            ERROR LOG
          </div>
          <pre className="mono-text" style={{ whiteSpace: 'pre-wrap', fontSize: 11,
                                              color: 'var(--text-secondary)' }}>
            {data.error_log}
          </pre>
        </div>
      )}

      {stream.cases.length > 0 && (
        <div className="glass-card" style={{ marginBottom: 'var(--space-lg)' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            LIVE STREAM ({fmtNum(stream.cases.length)} cases this session)
          </div>
          <div className="log-terminal">
            {stream.cases.slice(0, 30).map((event) => (
              <div key={event.adaptation_id} className="log-entry">
                <span className="log-time">{fmtTime(event.ts)}</span>
                <span className="log-type">{event.scenario}</span>
                <span className="log-msg">
                  <Badge tone={toneFor(event.status)}>{event.status}</Badge>
                  {' '}{event.case_id}
                  {event.task_success ? ' · goal reached' : ''}
                  {event.hard_violation ? ' · hard violation' : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="dashboard-grid">
        <div className="glass-card col-span-7">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            ADAPTATIONS ({fmtNum(adaptationsRows.length)})
          </div>
          {adaptations.isLoading ? <LoadingState /> : (
            <DataTable
              columns={[
                { key: 'status', header: 'STATUS',
                  render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
                { key: 'success', header: 'SUCCESS',
                  render: (r) => (r.task_success === null ? '—'
                    : r.task_success ? 'yes' : 'no') },
                { key: 'gold', header: 'GOLD',
                  render: (r) => (r.gold_similarity === null || r.gold_similarity === undefined
                    ? '—' : r.gold_exact_match ? 'exact' : r.gold_similarity.toFixed(2)) },
                { key: 'hard', header: 'HARD VIOL.',
                  render: (r) => (r.hard_violation === null || r.hard_violation === undefined
                    ? '—' : r.hard_violation ? 'yes' : 'no') },
                { key: 'scv', header: 'SCV',
                  render: (r) => (r.scv_approved === null ? '—'
                    : r.scv_approved ? 'approved' : 'violation') },
                { key: 'viol', header: 'VIOL. COST',
                  render: (r) => (r.viol_cost ?? 0).toFixed(2) },
                { key: 'fitness', header: 'FITNESS',
                  render: (r) => (r.conformance_fitness === null ? '—'
                    : r.conformance_fitness.toFixed(3)) },
                { key: 'latency', header: 'LATENCY',
                  render: (r) => (r.latency_s === null ? '—' : `${r.latency_s.toFixed(2)}s`) },
                { key: 'tokens', header: 'TOKENS',
                  render: (r) => fmtNum(r.llm_tokens) },
                { key: 'cost', header: 'COST',
                  render: (r) => (r.usd_cost === null || r.usd_cost === undefined
                    ? '—' : `$${r.usd_cost.toFixed(3)}`) },
              ]}
              rows={adaptationsRows}
              empty="No adaptations recorded for this run yet."
            />
          )}
        </div>

        <div className="glass-card col-span-5">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            AUDIT CHAIN ({fmtNum((audit.data ?? []).length)} entries)
          </div>
          {audit.isLoading ? <LoadingState /> : (
            <div className="log-terminal">
              {(audit.data ?? []).slice(0, 30).map((entry) => (
                <div key={entry.id} className="log-entry">
                  <span className="log-time">#{entry.sequence_num}</span>
                  <span className="log-type">{String(entry.entry_type ?? '').toUpperCase().slice(0, 8)}</span>
                  <span className="log-msg">
                    {entry.actor_name ?? entry.actor_agent ?? 'system'}
                  </span>
                </div>
              ))}
              {(audit.data ?? []).length === 0 && (
                <div style={{ color: 'var(--text-muted)' }}>
                  No audit entries for this run yet.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
