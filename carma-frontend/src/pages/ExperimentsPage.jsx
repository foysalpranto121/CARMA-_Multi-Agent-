import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plus, Play, Pause, Download, FlaskConical } from 'lucide-react';
import { experimentApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader,
  fmtDate, fmtNum, toneFor,
} from '../components/ui';
import { useAuthStore, hasRole } from '../store/authStore';

export default function ExperimentsPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canRun = hasRole(role, ['researcher']);
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [notice, setNotice] = useState('');

  const runs = useQuery({
    queryKey: ['runs', 'list', statusFilter],
    queryFn: async () => unwrap((await experimentApi.runs({
      page_size: 100,
      ...(statusFilter ? { status: statusFilter } : {}),
    })).data),
    refetchInterval: 15_000,
  });

  const action = useMutation({
    mutationFn: ({ id, verb }) =>
      verb === 'start' ? experimentApi.start(id) : experimentApi.pause(id),
    onSuccess: (res) => {
      setNotice(res.data?.detail ?? 'Done.');
      queryClient.invalidateQueries({ queryKey: ['runs'] });
    },
    onError: (err) => setNotice(err?.response?.data?.detail ?? 'Action failed.'),
  });

  return (
    <div className="page-wrapper">
      <PageHeader
        title="EXPERIMENT RUNS"
        subtitle="8 configurations B0–B7 × 3 LLMs × 3 seeds. Each run replays the benchmark through one configuration."
        actions={canRun && (
          <Link to="/experiments/new" className="btn btn-solid" style={{ textDecoration: 'none' }}>
            <Plus size={13} /> New Run
          </Link>
        )}
      />

      <div className="flex items-center justify-between mb-md">
        <div className="flex items-center gap-sm">
          {['running', 'completed', 'failed', 'pending'].map(s => (
            <button
              key={s}
              className={`btn ${statusFilter === s ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: 10, textTransform: 'uppercase' }}
              onClick={() => setStatusFilter(statusFilter === s ? '' : s)}
            >
              {s}
            </button>
          ))}
        </div>
        {notice && (
          <span style={{ fontSize: 11, color: 'var(--holo-cyan)' }}>{notice}</span>
        )}
      </div>

      <div className="glass-card">
        {runs.isLoading ? <LoadingState label="Loading runs…" />
          : runs.error ? <ErrorState error={runs.error} onRetry={runs.refetch} />
          : (
          <DataTable
            columns={[
              { key: 'config', header: 'CONFIG',
                render: (r) => (
                  <Link to={`/experiments/${r.id}`}
                        style={{ color: 'var(--holo-cyan)', textDecoration: 'none',
                                 fontFamily: 'var(--font-display)' }}>
                    {r.config_code}
                  </Link>
                ) },
              { key: 'seed', header: 'SEED', render: (r) => r.seed },
              { key: 'status', header: 'STATUS',
                render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
              { key: 'progress', header: 'PROGRESS',
                render: (r) => (
                  <div style={{ minWidth: 110 }}>
                    <div className="metric-bar-track">
                      <div className="metric-bar-fill cyan" style={{ width: `${r.progress_pct ?? 0}%` }} />
                    </div>
                    <span className="mono-text" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      {r.completed_cases}/{r.total_cases}
                    </span>
                  </div>
                ) },
              { key: 'created_by', header: 'OWNER',
                render: (r) => r.created_by_name ?? '—' },
              { key: 'created', header: 'CREATED',
                render: (r) => <span style={{ color: 'var(--text-muted)' }}>{fmtDate(r.created_at)}</span> },
              { key: 'actions', header: 'ACTIONS',
                render: (r) => (
                  <div className="flex items-center gap-xs">
                    {canRun && r.status === 'pending' && (
                      <button className="btn btn-ghost" style={{ fontSize: 9 }}
                              disabled={action.isPending}
                              onClick={() => action.mutate({ id: r.id, verb: 'start' })}>
                        <Play size={10} /> start
                      </button>
                    )}
                    {canRun && r.status === 'running' && (
                      <button className="btn btn-ghost" style={{ fontSize: 9 }}
                              disabled={action.isPending}
                              onClick={() => action.mutate({ id: r.id, verb: 'pause' })}>
                        <Pause size={10} /> pause
                      </button>
                    )}
                    <a className="btn btn-ghost" style={{ fontSize: 9, textDecoration: 'none' }}
                       href={experimentApi.exportUrl(r.id)}>
                      <Download size={10} /> csv
                    </a>
                  </div>
                ) },
            ]}
            rows={runs.data ?? []}
            empty="No experiment runs yet. Create one to start collecting results."
          />
        )}
      </div>
    </div>
  );
}
