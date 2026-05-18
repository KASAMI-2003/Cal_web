const LOGIN_FLAG = 'is_logged_in';
const LOGIN_USER = 'login_user';

export interface AuthState {
  isLoggedIn: boolean;
  username: string;
}

export function getAuthState(): AuthState {
  return {
    isLoggedIn: localStorage.getItem(LOGIN_FLAG) === '1',
    username: localStorage.getItem(LOGIN_USER) ?? '',
  };
}

export function setAuthState(username: string): void {
  localStorage.setItem(LOGIN_FLAG, '1');
  localStorage.setItem(LOGIN_USER, username);
}

export function clearAuthState(): void {
  localStorage.removeItem(LOGIN_FLAG);
  localStorage.removeItem(LOGIN_USER);
}
