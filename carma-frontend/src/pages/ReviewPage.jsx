import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert, UserCheck, CheckCircle } from 'lucide-react';
import { reviewApi, unwrap } from '../api/client';
import {
  Badge, DataTable, EmptyState, ErrorState, LoadingState, PageHeader,
  fmtDate, fmtNum, toneFor,
} from '../components/ui';

const DECISIONS = [
  { value: 'approved', label: 'Approved as-is' },
  { value: 'modified', label: 'Approved with modification' },
  { value: 'rejected', label: 'Rejected — restart' },
  { value: 'deferred', label: 'Deferred for later' },
];

export default function ReviewPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [selected, setSelected] = useState(null);
  const [decision, setDecision] = useState('approved');
  const [justification, setJustification] = useState('');
  const [notice, setNotice] = useState('');

  const escalations = useQuery({
    queryKey: ['escalations', statusFilter],
    queryFn: async () => unwrap((await reviewApi.escalations({
      page_size: 50,
      ...(statusFilter ? { status: statusFilter } : {}),
    })).data),
    refetchInterval: 20_000,
  });

  const reviews = useQuery({
    queryKey: ['reviews'],
    queryFn: async () => unwrap((await reviewApi.reviews({ page_size: 50 })).data),
  });

  const assign = useMutation({
    mutationFn: (id) => reviewApi.assign(id).then(r => r.data),
    onSuccess: (data) => {
      setNotice(data?.detail ?? 'Assigned.');
      queryClient.invalidateQueries({ queryKey: ['escalations'] });
    },
    onError: (err) => setNotice(err?.response?.data?.detail ?? 'Could not assign the escalation.'),
  });

  const submit = useMutation({
    mutationFn: (payload) => reviewApi.createReview(payload).then(r => r.data),
    onSuccess: () => {
      setNotice('Review recorded.');
      setSelected(null);
      setJustification('');
      queryClient.invalidateQueries({ queryKey: ['escalations'] });
      queryClient.invalidateQueries({ queryKey: ['reviews'] });
    },
    onError: (err) => setNotice(err?.response?.data?.detail ?? 'Could not record the review.'),
  });

  const current = (escalations.data ?? []).find(e => e.id === selected) ?? null;

  return (
    <div className="page-wrapper">
      <PageHeader
        title="ESCALATION QUEUE"
        subtitle="Plans the agent team could not verify with sufficient confidence. A human decides."
        actions={(
          <div className="flex items-center gap-sm">
            {['', 'pending', 'assigned', 'resolved'].map(s => (
              <button key={s || 'all'}
                      className={`btn ${statusFilter === s ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ fontSize: 10, textTransform: 'uppercase' }}
                      onClick={() => setStatusFilter(s)}>
                {s || 'all'}
              </button>
            ))}
          </div>
        )}
      />

      {notice && (
        <div style={{ marginBottom: 'var(--space-md)', fontSize: 12, color: 'var(--holo-cyan)' }}>
          {notice}
        </div>
      )}

      <div className="dashboard-grid">
        <div className="glass-card col-span-7">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            ESCALATIONS ({fmtNum((escalations.data ?? []).length)})
          </div>
          {escalations.isLoading ? <LoadingState label="Loading escalations…" />
            : escalations.error ? <ErrorState error={escalations.error} onRetry={escalations.refetch} />
            : (
            <DataTable
              columns={[
                { key: 'case', header: 'CASE',
                  render: (r) => r.case_id ?? '—' },
                { key: 'scenario', header: 'SCENARIO',
                  render: (r) => (r.scenario_code
                    ? <Badge tone="violet">{r.scenario_code}</Badge> : '—') },
                { key: 'reason', header: 'REASON',
                  render: (r) => <Badge tone={toneFor(r.status)}>{r.reason}</Badge> },
                { key: 'conf', header: 'CONF.',
                  render: (r) => (r.confidence === null || r.confidence === undefined
                    ? '—' : r.confidence.toFixed(2)) },
                { key: 'viol', header: 'VIOL. COST',
                  render: (r) => (r.viol_cost ?? 0).toFixed(2) },
                { key: 'status', header: 'STATUS',
                  render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
                { key: 'actions', header: '',
                  render: (r) => (
                    <div className="flex items-center gap-xs">
                      <button className="btn btn-ghost" style={{ fontSize: 9 }}
                              onClick={() => setSelected(r.id)}>
                        review
                      </button>
                      {r.status === 'pending' && (
                        <button className="btn btn-ghost" style={{ fontSize: 9 }}
                                disabled={assign.isPending}
                                onClick={() => assign.mutate(r.id)}>
                          <UserCheck size={10} /> assign
                        </button>
                      )}
                    </div>
                  ) },
              ]}
              rows={escalations.data ?? []}
              empty="No escalations in this state."
            />
          )}
        </div>

        <div className="glass-card col-span-5">
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>
            {current ? 'REVIEW DECISION' : 'RECENT REVIEWS'}
          </div>

          {!current ? (
            reviews.isLoading ? <LoadingState /> : (
              <DataTable
                columns={[
                  { key: 'decision', header: 'DECISION',
                    render: (r) => <Badge tone={toneFor(r.decision)}>{r.decision}</Badge> },
                  { key: 'reviewer', header: 'REVIEWER',
                    render: (r) => r.reviewer_name ?? '—' },
                  { key: 'at', header: 'REVIEWED',
                    render: (r) => <span style={{ color: 'var(--text-muted)' }}>{fmtDate(r.reviewed_at)}</span> },
                ]}
                rows={reviews.data ?? []}
                empty="Select an escalation to record a decision."
              />
            )
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
              <div>
                <div className="kpi-label">CASE</div>
                <div className="mono-text" style={{ fontSize: 12 }}>{current.case_id ?? '—'}</div>
              </div>
              <div>
                <div className="kpi-label">REASON</div>
                <div style={{ marginTop: 4 }}>
                  <Badge tone={toneFor(current.status)}>{current.reason}</Badge>
                </div>
              </div>
              {current.reason_detail && (
                <div>
                  <div className="kpi-label">DETAIL</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {current.reason_detail}
                  </div>
                </div>
              )}
              <div>
                <label className="form-label" htmlFor="decision">Decision</label>
                <select id="decision" className="holo-select" value={decision}
                        onChange={(e) => setDecision(e.target.value)}>
                  {DECISIONS.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="form-label" htmlFor="justification">Justification</label>
                <textarea id="justification" className="holo-input" rows={4}
                          value={justification}
                          onChange={(e) => setJustification(e.target.value)}
                          placeholder="Why is this the correct decision?" />
              </div>
              <div className="flex items-center gap-sm">
                <button className="btn btn-solid" style={{ flex: 1, justifyContent: 'center' }}
                        disabled={submit.isPending}
                        onClick={() => submit.mutate({
                          escalation: current.id,
                          decision,
                          justification,
                        })}>
                  <CheckCircle size={13} /> Record review
                </button>
                <button className="btn btn-ghost" onClick={() => setSelected(null)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
