import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Auth store — persisted to localStorage.
 * Stores the JWT token pair, user profile, and login state.
 */
export const useAuthStore = create(
  persist(
    (set, get) => ({
      /* ── State ── */
      user:         null,   // { id, username, email, role, firstName, lastName }
      accessToken:  null,
      refreshToken: null,
      isLoggedIn:   false,

      /* ── Actions ── */
      login: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isLoggedIn: true }),

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
    }
  )
);
