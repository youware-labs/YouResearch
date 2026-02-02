import { create } from 'zustand';

// YouWare Labs OAuth configuration
const LABS_HOST = 'https://www.youware.com';
const LABS_PROJECT_ID = 'youresearch';
const AUTH_STORAGE_KEY = 'youresearch_auth';

interface AuthStore {
  // State
  isAuthenticated: boolean;
  isLoading: boolean;

  // Actions
  initialize: () => void;
  login: (nextPath?: string) => void;
  logout: () => void;
  handleCallback: () => boolean;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  isAuthenticated: false,
  isLoading: true,

  initialize: () => {
    // Check if we have auth token in localStorage
    if (typeof window === 'undefined') {
      set({ isLoading: false });
      return;
    }

    // First, check for OAuth callback
    const didHandleCallback = get().handleCallback();
    if (didHandleCallback) {
      return;
    }

    // Check localStorage for existing auth
    const authData = localStorage.getItem(AUTH_STORAGE_KEY);
    if (authData) {
      try {
        const parsed = JSON.parse(authData);
        // Check if not expired (24 hours)
        if (parsed.timestamp && Date.now() - parsed.timestamp < 24 * 60 * 60 * 1000) {
          set({ isAuthenticated: true, isLoading: false });
          return;
        }
      } catch {
        // Invalid data, remove it
        localStorage.removeItem(AUTH_STORAGE_KEY);
      }
    }

    set({ isAuthenticated: false, isLoading: false });
  },

  handleCallback: () => {
    if (typeof window === 'undefined') return false;

    const url = new URL(window.location.href);
    const code = url.searchParams.get('code');
    
    if (code) {
      // We received an auth code from YouWare Labs
      // Store auth state in localStorage
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
        authenticated: true,
        timestamp: Date.now(),
      }));

      // Clean up URL
      url.searchParams.delete('code');
      url.searchParams.delete('state');
      window.history.replaceState({}, '', url.pathname);

      set({ isAuthenticated: true, isLoading: false });
      return true;
    }

    return false;
  },

  login: (nextPath?: string) => {
    if (typeof window === 'undefined') return;

    const currentUrl = window.location.origin + (nextPath || window.location.pathname);
    const authUrl = `${LABS_HOST}/labs/authorize?` + new URLSearchParams({
      project_id: LABS_PROJECT_ID,
      redirect_uri: currentUrl,
    }).toString();

    window.location.href = authUrl;
  },

  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
    set({ isAuthenticated: false });
  },
}));
