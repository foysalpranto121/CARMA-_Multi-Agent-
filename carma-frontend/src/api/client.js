import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const BASE = import.meta.env.VITE_API_URL ?? '/api/v1';

export const apiClient = axios.create({ baseURL: BASE });

/* Attach token on every request */
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/* Auto-refresh on 401 */
apiClient.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const refresh = useAuthStore.getState().refreshToken;
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE}/auth/token/refresh/`, { refresh });
          useAuthStore.getState().setTokens(data.access, data.refresh ?? refresh);
          original.headers.Authorization = `Bearer ${data.access}`;
          return apiClient(original);
        } catch {
          useAuthStore.getState().logout();
        }
      }
    }
    return Promise.reject(err);
  }
);

/**
 * DRF returns either a bare list or a paginated envelope.
 * Normalise both to a plain array.
 */
export function unwrap(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.results)) return payload.results;
  return [];
}

/* ── Auth endpoints ── */
export const authApi = {
  login:    (email, password) =>
    apiClient.post('/auth/token/', { email, password }),

  register: (payload) =>
    apiClient.post('/users/register/', payload),

  me:       () =>
    apiClient.get('/users/me/'),

  logout:   (refreshToken) =>
    apiClient.post('/auth/token/blacklist/', { refresh: refreshToken }),
};

/* ── Process frames & constraints ── */
export const processApi = {
  list:      (params)            => apiClient.get('/processes/', { params }),
  get:       (id)                => apiClient.get(`/processes/${id}/`),
  create:    (payload)           => apiClient.post('/processes/', payload),
  update:    (id, payload)       => apiClient.patch(`/processes/${id}/`, payload),
  remove:    (id)                => apiClient.delete(`/processes/${id}/`),

  constraintSets:  (params)      => apiClient.get('/constraint-sets/', { params }),
  createConstraintSet: (payload)  => apiClient.post('/constraint-sets/', payload),
  constraints:     (params)      => apiClient.get('/constraints/', { params }),
  createConstraint: (payload)     => apiClient.post('/constraints/', payload),

  corpus:          (params)      => apiClient.get('/corpus/', { params }),
  createCorpusDoc: (payload)     => apiClient.post('/corpus/', payload),
};

/* ── WF-Adapt benchmark ── */
export const benchmarkApi = {
  scenarios:  (params)   => apiClient.get('/benchmark/scenarios/', { params }),
  cases:      (params)   => apiClient.get('/benchmark/cases/', { params }),
  case:       (id)       => apiClient.get(`/benchmark/cases/${id}/`),
  stats:      ()         => apiClient.get('/benchmark/cases/stats/'),
  eventLogs:  (params)   => apiClient.get('/event-logs/', { params }),
  casesRaw:   (params)   => apiClient.get('/cases/', { params }),
  importLog:  (payload)  => apiClient.post('/benchmark/import-log/', payload),
};

/* ── Experiments ── */
export const experimentApi = {
  runs:        (params)  => apiClient.get('/experiments/', { params }),
  run:         (id)      => apiClient.get(`/experiments/${id}/`),
  createRun:   (payload) => apiClient.post('/experiments/', payload),
  start:       (id)      => apiClient.post(`/experiments/${id}/start/`),
  pause:       (id)      => apiClient.post(`/experiments/${id}/pause/`),
  exportUrl:   (id)      => `${BASE}/experiments/${id}/export/`,
  matrix:      ()        => apiClient.get('/experiments/matrix/'),
  configurations: (params) => apiClient.get('/run-configs/', { params }),
  results:     (params)  => apiClient.get('/run-results/', { params }),
  adaptations: (params)  => apiClient.get('/adaptations/', { params }),
};

/* ── Metrics & statistics ── */
export const metricsApi = {
  runMetrics:       (params) => apiClient.get('/metrics/', { params }),
  statisticalTests: (params) => apiClient.get('/metrics/statistical-tests/', { params }),
  costBreakdown:    (params) => apiClient.get('/metrics/cost-breakdown/', { params }),
  scenarioBreakdown:(params) => apiClient.get('/metrics/scenario-breakdown/', { params }),
};

/* ── Human review ── */
export const reviewApi = {
  escalations:  (params) => apiClient.get('/escalations/', { params }),
  assign:       (id)     => apiClient.post(`/escalations/${id}/assign/`),
  reviews:      (params) => apiClient.get('/reviews/', { params }),
  createReview: (payload)=> apiClient.post('/reviews/', payload),
};

/* ── Audit log ── */
export const auditApi = {
  entries:     (params) => apiClient.get('/audit/', { params }),
  verifyChain: (params) => apiClient.get('/audit/verify-chain/', { params }),
  replay:      (id)     => apiClient.get(`/audit/replay/${id}/`),
};

/* ── Platform status (lives outside /api/v1) ── */
export const systemApi = {
  status: () => apiClient.get('/system/status/'),
  health: () => axios.get('/health/'),
};
