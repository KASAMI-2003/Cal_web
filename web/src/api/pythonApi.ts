import { requestJson } from './http';
import { authHeaders } from '../auth/authStore';
import type {
  ActivateDatRequest,
  ActivateDatResponse,
  ApiDataResponse,
  ApiSubmitRequest,
  DataFitRequest,
  DataFitResponse,
  DataInputListResponse,
  TerminalReachableRequest,
  TerminalReachableResponse,
  TwinCapabilitiesResponse,
  TwinDatListResponse,
  TwinPropertyResponse,
  UploadDatRequest,
  UploadDatResponse,
  VaspImportRequest,
  VaspImportResponse,
  CreateLatticePictureRequest,
  CreateLatticePictureResponse,
  ExtendedPropertiesResponse,
  ConvergenceScanResponse,
} from '../types/contracts';

const pythonBaseUrl = import.meta.env.VITE_PYTHON_API_ORIGIN || undefined;

function withAuth(extra?: Record<string, string>) {
  return { ...authHeaders(), ...(extra ?? {}) };
}

export const pythonApi = {
  submitElement: (body: ApiSubmitRequest) =>
    requestJson<{ status: string; message: string }, ApiSubmitRequest>('/api/submit', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
      headers: withAuth(),
    }),
  queryData: (element?: string, numElement?: number, materialId?: string) => {
    const params = new URLSearchParams();
    if (element) {
      params.set('element', element);
    }
    if (numElement !== undefined) {
      params.set('num_element', String(numElement));
    }
    if (materialId) {
      params.set('material_id', materialId);
    }
    const query = params.toString();
    return requestJson<ApiDataResponse>(query ? `/api/data?${query}` : '/api/data', { baseUrl: pythonBaseUrl });
  },
  mysqlReceive: (body: { element: string; text: string }) =>
    requestJson('/mysql_receive', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  page2Search: (body: {
    q: string;
    fuzzy?: boolean;
    case_sensitive?: boolean;
    search_in?: string;
    filters?: Record<string, unknown>;
    /** true = 仅查本地 MySQL，不调用 MP */
    local_only?: boolean;
  }) => requestJson('/page2_search', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  homeSearch: (body: { q: string; filters?: Record<string, unknown> }) =>
    requestJson('/api/home_search', { method: 'POST', body, baseUrl: pythonBaseUrl, headers: withAuth() }),
  submitDataInput: (body: { username: string; data: Record<string, unknown> }) =>
    requestJson<{ success: boolean; message: string; id?: string }>('/data_input/submit', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
      headers: withAuth(),
    }),
  myDataInputs: (username: string) =>
    requestJson<DataInputListResponse>(`/data_input/my?username=${encodeURIComponent(username)}`, { baseUrl: pythonBaseUrl }),
  pendingDataInputs: () =>
    requestJson<DataInputListResponse>('/data_input/pending?admin_user=admin', { baseUrl: pythonBaseUrl, headers: withAuth() }),
  reviewDataInput: (body: {
    id: string;
    action: 'approve' | 'reject';
    admin_user: string;
    target_db?: 'element_inf' | 'materials';
  }) =>
    requestJson<{ success: boolean; message: string }>('/data_input/review', {
      method: 'PUT',
      body,
      baseUrl: pythonBaseUrl,
      headers: withAuth(),
    }),
  fitData: (body: DataFitRequest) =>
    requestJson<DataFitResponse, DataFitRequest>('/api/data_fit', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  linkFitToCompound: (body: { username: string; element: string; fit_result: DataFitResponse }) =>
    requestJson<{ success: boolean; message: string }>('/api/data_fit/link_compound', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
      headers: withAuth(),
    }),
  terminalReachable: (body: TerminalReachableRequest) =>
    requestJson<TerminalReachableResponse, TerminalReachableRequest>('/api/terminal_reachable', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  getWebsocketPort: () => requestJson<{ port: number | null }>('/websocket_port', { baseUrl: pythonBaseUrl }),
  outcarTail: (dir: string) =>
    requestJson<{ success: boolean; tail?: string; message?: string }>(
      `/api/outcar_tail?dir=${encodeURIComponent(dir)}`,
      { baseUrl: pythonBaseUrl },
    ),
  extendedProperties: (workDir?: string, module = 'all') => {
    const params = new URLSearchParams();
    if (workDir) params.set('work_dir', workDir);
    if (module) params.set('module', module);
    const q = params.toString();
    return requestJson<ExtendedPropertiesResponse>(q ? `/api/extended_properties?${q}` : '/api/extended_properties', {
      baseUrl: pythonBaseUrl,
    });
  },
  scanExtendedProperties: (body: { work_dir: string; module?: string }) =>
    requestJson<ExtendedPropertiesResponse, { work_dir: string; module?: string }>('/api/extended_properties/scan', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  scanConvergence: (body: { root_dir: string; threshold_gpa?: number }) =>
    requestJson<ConvergenceScanResponse, { root_dir: string; threshold_gpa?: number }>('/api/convergence/scan', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  fedorovCrosscheck: (symbol: string) =>
    requestJson<{ success: boolean; message?: string; passed?: boolean }>(
      `/api/digital_twin/fedorov_crosscheck?symbol=${encodeURIComponent(symbol)}`,
      { baseUrl: pythonBaseUrl },
    ),
  twinProperties: (query: string) =>
    requestJson<TwinPropertyResponse>(`/api/digital_twin/properties?${query}`, { baseUrl: pythonBaseUrl }),
  twinCapabilities: (query: string) =>
    requestJson<TwinCapabilitiesResponse>(`/api/digital_twin/capabilities?${query}`, { baseUrl: pythonBaseUrl }),
  twinListDat: (username: string) =>
    requestJson<TwinDatListResponse>(`/api/digital_twin/list_dat?username=${encodeURIComponent(username)}`, {
      baseUrl: pythonBaseUrl,
    }),
  twinUploadDat: (body: UploadDatRequest) =>
    requestJson<UploadDatResponse, UploadDatRequest>('/api/digital_twin/upload_dat', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  twinActivateDat: (body: ActivateDatRequest) =>
    requestJson<ActivateDatResponse, ActivateDatRequest>('/api/digital_twin/activate_dat', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  createLatticePicture: (body: CreateLatticePictureRequest) =>
    requestJson<CreateLatticePictureResponse, CreateLatticePictureRequest>('/create_lattice_picture', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  vaspImport: (body: VaspImportRequest) =>
    requestJson<VaspImportResponse, VaspImportRequest>('/api/vasp/import', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
      headers: withAuth(),
    }),
};
