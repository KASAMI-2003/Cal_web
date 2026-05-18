export type ApiStatus = 'success' | 'error';

export interface ApiDataResponse {
  message: string[];
}

export interface ApiSubmitRequest {
  element: string;
  num_element: number;
}

export interface DataInputApplication {
  id: string;
  username: string;
  data: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  reviewed_at?: string;
  target_db?: 'element_inf' | 'materials';
}

export interface DataInputListResponse {
  success: boolean;
  message?: string;
  data?: DataInputApplication[];
}

export interface DataFitRequest {
  x_data: number[];
  y_data: number[];
  fit_type: 'Polynomial' | 'Exponential' | 'Logarithmic' | 'Sine';
  degree?: number;
}

export interface DataFitResponse {
  status: ApiStatus;
  message?: string;
  fit_func?: string;
  r_squared?: number;
  coeffs?: number[];
  x_fit?: number[];
  y_fit?: number[];
}

export interface TwinPropertyResponse {
  T_K: number;
  P_GPa: number;
  bulk_modulus_GPa?: number;
  shear_modulus_GPa?: number;
  young_modulus_GPa?: number;
  volume_scale?: number;
  model?: string;
}

export interface TwinCapabilitiesResponse {
  [key: string]: unknown;
}

export interface TwinDatListResponse {
  files: Array<Record<string, unknown>>;
}

export interface UploadDatRequest {
  username: string;
  filename: string;
  content_base64: string;
}

export interface UploadDatResponse {
  success: boolean;
  message?: string;
  id?: string;
  kind?: string;
  probe?: Record<string, unknown>;
}

export interface ActivateDatRequest {
  username: string;
  twin_file?: string;
}

export interface ActivateDatResponse {
  success: boolean;
  message?: string;
  mode?: string;
  kind?: string;
  twin_file?: string;
}

export interface TerminalReachableRequest {
  host: string;
  port: number;
  timeout?: number;
}

export interface TerminalReachableResponse {
  ok: boolean;
  reachable: boolean;
  code?: string;
  message?: string;
  latency_ms?: number;
}

export interface RustAuthRequest {
  username: string;
  password: string;
  email?: string;
}

export interface RustAuthResponse {
  success: boolean;
  message: string;
}

export interface RustUserInfoResponse {
  success: boolean;
  message?: string;
  user?: {
    username: string;
    email?: string;
    phone?: string;
    create_time?: number;
  };
}

export interface RustUserUpdateRequest {
  username: string;
  email: string;
  phone: string;
}
