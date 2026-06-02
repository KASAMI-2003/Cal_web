const LOGIN_FLAG = 'is_logged_in';
const LOGIN_USER = 'login_user';
const AUTH_TOKEN = 'auth_token';

export interface AuthState {
  isLoggedIn: boolean;
  username: string;
  token: string;
}

export function getAuthState(): AuthState {
  return {
    isLoggedIn: localStorage.getItem(LOGIN_FLAG) === '1',
    username: localStorage.getItem(LOGIN_USER) ?? '',
    token: localStorage.getItem(AUTH_TOKEN) ?? '',
  };
}

export function getAuthToken(): string {
  return localStorage.getItem(AUTH_TOKEN) ?? '';
}

export function setAuthState(username: string, token?: string): void {
  localStorage.setItem(LOGIN_FLAG, '1');
  localStorage.setItem(LOGIN_USER, username);
  if (token) {
    localStorage.setItem(AUTH_TOKEN, token);
  }
}

export function clearAuthState(): void {
  localStorage.removeItem(LOGIN_FLAG);
  localStorage.removeItem(LOGIN_USER);
  localStorage.removeItem(AUTH_TOKEN);
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
