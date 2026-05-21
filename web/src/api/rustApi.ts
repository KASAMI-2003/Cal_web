import { requestJson } from './http';
import type {
  RustAuthRequest,
  RustAuthResponse,
  RustUserInfoResponse,
  RustUserUpdateRequest,
} from '../types/contracts';

// 开发：直连本机 Rust；生产：默认走当前站点（Nginx 反代 /login 等到 8088）
const rustBaseUrl =
  import.meta.env.VITE_RUST_API_ORIGIN ??
  (import.meta.env.DEV ? 'http://127.0.0.1:8088' : undefined);

export const rustApi = {
  login: (body: RustAuthRequest) =>
    requestJson<RustAuthResponse, RustAuthRequest>('/login', {
      method: 'POST',
      body,
      baseUrl: rustBaseUrl,
    }),
  register: (body: RustAuthRequest) =>
    requestJson<RustAuthResponse, RustAuthRequest>('/register', {
      method: 'POST',
      body,
      baseUrl: rustBaseUrl,
    }),
  userInfo: (username: string) =>
    requestJson<RustUserInfoResponse>(`/users/info?username=${encodeURIComponent(username)}`, {
      baseUrl: rustBaseUrl,
    }),
  updateUser: (body: RustUserUpdateRequest) =>
    requestJson<RustUserInfoResponse, RustUserUpdateRequest>('/users/update', {
      method: 'PUT',
      body,
      baseUrl: rustBaseUrl,
    }),
};
