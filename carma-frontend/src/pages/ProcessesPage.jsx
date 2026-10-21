import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Cpu, Plus, FileText, Layers, Trash2 } from 'lucide-react';
import { processApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, Panel,
  fmtDate, fmtNum,
} from '../components/ui';
import { useAuthStore, hasRole } from '../store/authStore';

const CONSTRAINT_TYPES = [
  'response', 'precedence', 'not_coexistence', 'existence',
  'at_most_one', 'data_based', 'cardinality', 'temporal',
];

export default function ProcessesPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = hasRole(role, ['researcher']);

  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState('');

  const processes = useQuery({
    queryKey: ['processes'],
    queryFn: async () => unwrap((await processApi.list({ page_size: 100 })).data),
  });

  const selected = (processes.data ?? []).find(p => p.id === selectedId)
    ?? (processes.data ?? [])[0]
    ?? null;

  const constraintSets = useQuery({
    queryKey: ['constraint-sets', selected?.id ?? null],
    queryFn: async () => unwrap((await processApi.constraintSets({ process: selected.id, page_size: 50 })).data),
    enabled: Boolean(selected?.id),
  });

  const constraints = useQuery({
    queryKey: ['constraints', selected?.id ?? null],
    queryFn: async () => {
      const sets = constraintSets.data ?? [];
      const all = await Promise.all(sets.map(async (s) => {
        const res = await processApi.constraints({ constraint_set: s.id, page_size: 200 });
        return unwrap(res.data);
      }));
      return all.flat();
    },
    enabled: Boolean((constraintSets.data ?? []).length),
  });

  const corpus = useQuery({
    queryKey: ['corpus', selected?.id ?? null],
    queryFn: async () => unwrap((await processApi.corpus({ process: selected.id, page_size: 100 })).data),
    enabled: Boolean(selected?.id),
  });

  const columns = [
    { key: 'name', header: 'PROCESS',
      render: (row) => (
        <span style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}>
          {row.name}
        </span>
      ) },
    { key: 'model_type', header: 'MODEL',
      render: (row) => <span style={{ color: 'var(--text-muted)' }}>{row.model_type ?? '—'}</span> },
    { key: 'activities', header: 'ACTIVITIES',
      render: (row) => fmtNum((row.activities ?? []).length) },
    { key: 'constraint_count', header: 'CONSTRAINT SETS',
      render: (row) => fmtNum(row.constraint_count) },
    { key: 'created_at', header: 'CREATED',
      render: (row) => <span style={{ color: 'var(--text-muted)' }}>{fmtDate(row.created_at)}</span> },
  ];

  return (
    <div className="page-wrapper">
      <PageHeader
        title="PROCESS FRAMES & CONSTRAINTS"
        subtitle="Process models, constraint sets and the retrieval corpus that the agents reason over."
        actions={canEdit && (
          <button className="btn btn-solid" onClick={() => setError('Process creation requires a BPMN import — use the benchmark importer to register a process.')}>
            <Plus size={13} /> New Process
          </button>
        )}
      />

      {error && (
        <div style={{ marginBottom: 'var(--space-md)', color: 'var(--holo-gold)', fontSize: 12 }}>
          {error}
        </div>
      )}

      {processes.isLoading ? <LoadingState label="Loading processes…" />
        : processes.error ? <ErrorState error={processes.error} onRetry={processes.refetch} />
        : (
        <div className="dashboard-grid">
          <div className="glass-card col-span-5">
            <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
              REGISTERED PROCESSES
            </div>
            <DataTable
              columns={columns}
              rows={processes.data ?? []}
              empty="No process frames registered yet."
            />
          </div>

          <div className="glass-card col-span-7">
            {!selected ? (
              <EmptyState message="Select a process to inspect its constraints and corpus." />
            ) : (
              <>
                <div className="flex items-center justify-between mb-md">
                  <div>
                    <div className="holo-subtitle">{selected.name.toUpperCase()}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {selected.description || 'No description provided.'}
                    </div>
                  </div>
                  <Badge tone="cyan">{selected.model_type ?? 'unknown'}</Badge>
                </div>

                <div style={{ marginBottom: 'var(--space-md)' }}>
                  <div className="holo-subtitle" style={{ marginBottom: 8 }}>ACTIVITIES</div>
                  <div className="flex flex-wrap gap-xs">
                    {(selected.activities ?? []).map((a) => (
                      <Badge key={a} tone="violet" style={{ fontSize: 10 }}>{a}</Badge>
                    ))}
                    {(selected.activities ?? []).length === 0 && (
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>No activities parsed.</span>
                    )}
                  </div>
                </div>

                <div style={{ marginBottom: 'var(--space-md)' }}>
                  <div className="holo-subtitle" style={{ marginBottom: 8 }}>CONSTRAINTS</div>
                  {constraints.isLoading ? <LoadingState /> : (
                    <DataTable
                      columns={[
                        { key: 'type', header: 'TYPE',
                          render: (r) => <Badge tone="cyan">{r.constraint_type}</Badge> },
                        { key: 'a', header: 'A', render: (r) => r.activity_a ?? '—' },
                        { key: 'b', header: 'B', render: (r) => r.activity_b ?? '—' },
                        { key: 'cost', header: 'VIOL. COST',
                          render: (r) => (r.violation_cost ?? 0).toFixed(2) },
                      ]}
                      rows={constraints.data ?? []}
                      empty="No constraints defined for this process."
                    />
                  )}
                </div>

                <div>
                  <div className="holo-subtitle" style={{ marginBottom: 8 }}>
                    RETRIEVAL CORPUS ({fmtNum((corpus.data ?? []).length)})
                  </div>
                  {corpus.isLoading ? <LoadingState /> : (
                    <DataTable
                      columns={[
                        { key: 'title', header: 'DOCUMENT',
                          render: (r) => (
                            <span style={{ fontFamily: 'var(--font-display)' }}>{r.title}</span>
                          ) },
                        { key: 'doc_type', header: 'TYPE', render: (r) => r.doc_type ?? '—' },
                        { key: 'stage', header: 'STAGE', render: (r) => r.stage ?? '—' },
                      ]}
                      rows={corpus.data ?? []}
                      empty="No corpus documents — retrieval will fall back to no evidence."
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
