import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Normalise the backend user payload (snake_case) into the camelCase shape
 * the UI consumes.  The backend is the only source of truth — there is no
 * local fallback profile.
 */
export function normalizeUser(raw) {
  if (!raw) return null;
  const first = raw.first_name ?? raw.firstName ?? '';
  const last  = raw.last_name  ?? raw.lastName  ?? '';
  return {
    id:         raw.id ?? null,
    email:      raw.email ?? '',
    username:   raw.username ?? raw.email ?? '',
    firstName:  first,
    lastName:   last,
    fullName:   raw.full_name ?? (first || last ? `${first} ${last}`.trim() : (raw.email ?? '')),
    role:       raw.role ?? 'researcher',
    isVerified: raw.is_verified ?? raw.isVerified ?? false,
    institution: raw.institution ?? '',
    avatar:     raw.avatar ?? null,
  };
}

/**
 * Role hierarchy.  Admins reach every module; every other role is a peer
 * with its own area of responsibility.
 */
export const ROLE_LABELS = {
  admin:      'Admin',
  researcher: 'Researcher',
  reviewer:   'Reviewer',
  annotator:  'Annotator',
};

export function hasRole(userRole, allowed) {
  if (!allowed) return true;
  const allowedList = Array.isArray(allowed) ? allowed : [allowed];
  if (userRole === 'admin') return true;
  return allowedList.includes(userRole);
}

/**
 * Auth store — persisted to localStorage.
 * Stores the JWT token pair, user profile, and login state.
 */
export const useAuthStore = create(
  persist(
    (set, get) => ({
      /* ── State ── */
      user:         null,
      accessToken:  null,
      refreshToken: null,
      isLoggedIn:   false,

      /* ── Actions ── */
      login: (user, accessToken, refreshToken) =>
        set({
          user: normalizeUser(user),
          accessToken,
          refreshToken,
          isLoggedIn: true,
        }),

      logout: () =>
        set({ user: null, accessToken: null, refreshToken: null, isLoggedIn: false }),

      updateUser: (patch) =>
        set(state => ({ user: { ...state.user, ...patch } })),

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      /* ── Selectors ── */
      getRole:    () => get().user?.role ?? null,
      getHeaders: () => ({
        Authorization: `Bearer ${get().accessToken}`,
        'Content-Type': 'application/json',
      }),
    }),
    {
      name: 'carma-auth',
      partialize: (state) => ({
        user:         state.user,
        accessToken:  state.accessToken,
        refreshToken: state.refreshToken,
        isLoggedIn:   state.isLoggedIn,
      }),
      /* Re-validate the persisted profile against the current shape. */
      onRehydrateStorage: () => (state) => {
        if (state?.user) state.user = normalizeUser(state.user);
      },
    }
  )
);
