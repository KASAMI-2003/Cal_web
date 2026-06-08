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
  source_type?: 'vasp_import' | 'manual';
  method?: string;
  cij?: Record<string, number>;
  moduli?: Record<string, number>;
  stability?: VaspStabilityReport;
  calc_meta?: Record<string, unknown>;
  quality?: VaspImportQualityFields;
  suggested_target_db?: 'element_inf' | 'materials';
}

/** VASP 入库质量/收敛预留字段（与 POST /api/vasp/import 一致） */
export interface VaspImportQualityFields {
  /** 应变拟合残差，如 RMSE、R² */
  strain_fit_residual?: string;
  /** k 点收敛档位，如 dense / 0.03 A^-1 */
  k_convergence_tier?: string;
  /** 计算—实验偏差标签，如 within_5pct */
  calc_exp_deviation_label?: string;
}

export interface VaspStabilityCheck {
  id: string;
  expr: string;
  value: number;
  passed: boolean;
}

export interface VaspStabilityReport {
  passed: boolean;
  crystal_system: string;
  born_passed: boolean;
  mouhat_passed: boolean;
  checks: VaspStabilityCheck[];
  messages: string[];
}

export interface VaspImportRequest {
  username: string;
  element: string;
  structure: string;
  method: 'stress_strain' | 'energy_strain' | 'summary' | 'outcar_elastic_tensor' | 'manual';
  cij?: Record<string, number>;
  scan_dir?: string;
  work_dir?: string;
  notes?: string;
  functional?: string;
  encut?: string;
  k_mesh?: string;
  /** 应变拟合残差 */
  strain_fit_residual?: string | number;
  /** k 点收敛档位 */
  k_convergence_tier?: string;
  /** 计算—实验偏差标签 */
  calc_exp_deviation_label?: string;
}

export interface VaspImportResponse {
  success: boolean;
  auto_rejected?: boolean;
  id?: string;
  message?: string;
  stability?: VaspStabilityReport;
  db_data?: Record<string, string>;
  quality?: VaspImportQualityFields;
  calc_meta?: VaspImportQualityFields & Record<string, unknown>;
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
  fit_type?: DataFitRequest['fit_type'];
  degree?: number;
  fit_func?: string;
  r_squared?: number;
  /** 拟合 RMSE，与应变—能量拟合残差口径一致 */
  rmse?: number;
  strain_fit_residual?: number;
  coeffs?: number[];
  coeff_stderr?: number[] | null;
  covariance_matrix?: number[][] | null;
  uncertainty_note?: string;
  x_fit?: number[];
  y_fit?: number[];
}

export interface ExtendedPropertiesResponse {
  status: string;
  message?: string;
  work_dir?: string;
  registered?: string[];
  modules?: Record<
    string,
    {
      available?: boolean;
      status?: string;
      files?: Record<string, unknown>;
      summary?: Record<string, unknown>;
      curve?: { energy_eV?: number[]; dos?: number[] };
    }
  >;
}

export interface ConvergenceScanResponse {
  success: boolean;
  message?: string;
  root_dir?: string;
  sweep_type?: string;
  threshold_GPa?: number;
  runs?: Array<Record<string, unknown>>;
  analysis?: {
    converged?: boolean;
    message?: string;
    series?: Array<Record<string, unknown>>;
    recommended?: Record<string, unknown>;
  };
  qc_suggestions?: Record<string, unknown>;
  workflow_note?: string;
}

export interface CreateLatticePictureRequest {
  lattice_const?: string;
  structure?: string;
  lattice_a?: number;
  lattice_b?: number;
  lattice_c?: number;
  element?: string;
  symbol?: string;
  poscar?: string;
  poscar_text?: string;
  supercell?: [number, number, number];
  space_group_no?: number;
  notes?: string;
  material_name?: string;
}

export interface CreateLatticePictureResponse {
  success?: boolean;
  error?: string;
  points?: number[][];
  connections?: number[][];
  elements?: string[];
  lattice_a?: number;
  lattice_b?: number;
  lattice_c?: number;
  n_atoms?: number;
  source?: 'ase_bulk' | 'ase_poscar' | string;
  structure?: string;
  element?: string;
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
  data?: {
    token?: string;
    username?: string;
  };
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
