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
    if (err.response?.status === 401 && !original._retry) {
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
