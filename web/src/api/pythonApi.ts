import { requestJson } from './http';
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
} from '../types/contracts';

const pythonBaseUrl = import.meta.env.VITE_PYTHON_API_ORIGIN || undefined;

export const pythonApi = {
  submitElement: (body: ApiSubmitRequest) =>
    requestJson<{ status: string; message: string }, ApiSubmitRequest>('/api/submit', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  queryData: () => requestJson<ApiDataResponse>('/api/data', { baseUrl: pythonBaseUrl }),
  mysqlReceive: (body: { element: string; text: string }) =>
    requestJson('/mysql_receive', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  page2Search: (body: { q: string; fuzzy?: boolean; case_sensitive?: boolean; search_in?: string }) =>
    requestJson('/page2_search', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  submitDataInput: (body: { username: string; data: Record<string, unknown> }) =>
    requestJson<{ success: boolean; message: string; id?: string }>('/data_input/submit', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  myDataInputs: (username: string) =>
    requestJson<DataInputListResponse>(`/data_input/my?username=${encodeURIComponent(username)}`, { baseUrl: pythonBaseUrl }),
  pendingDataInputs: () =>
    requestJson<DataInputListResponse>('/data_input/pending?admin_user=admin', { baseUrl: pythonBaseUrl }),
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
    }),
  fitData: (body: DataFitRequest) =>
    requestJson<DataFitResponse, DataFitRequest>('/api/data_fit', { method: 'POST', body, baseUrl: pythonBaseUrl }),
  terminalReachable: (body: TerminalReachableRequest) =>
    requestJson<TerminalReachableResponse, TerminalReachableRequest>('/api/terminal_reachable', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
  getWebsocketPort: () => requestJson<{ port: number | null }>('/websocket_port', { baseUrl: pythonBaseUrl }),
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
  createLatticePicture: (body: { lattice_const: string }) =>
    requestJson<{ points?: unknown[]; connections?: unknown[] }, { lattice_const: string }>('/create_lattice_picture', {
      method: 'POST',
      body,
      baseUrl: pythonBaseUrl,
    }),
};
