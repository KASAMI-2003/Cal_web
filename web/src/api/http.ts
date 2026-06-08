type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

interface RequestOptions<TBody> {
  method?: HttpMethod;
  body?: TBody;
  baseUrl?: string;
  headers?: Record<string, string>;
}

function buildUrl(path: string, baseUrl?: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl}${path}`;
}

function errorMessageFromPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    const message = record.message ?? record.error ?? record.detail;
    if (typeof message === 'string' && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export async function requestJson<TResponse, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  const response = await fetch(buildUrl(path, options.baseUrl), {
    method: options.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    credentials: 'same-origin',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      const preview = text.replace(/\s+/g, ' ').slice(0, 160);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}${preview ? `: ${preview}` : ''}`);
      }
      throw new Error(`服务器返回非 JSON 响应: ${preview || '(empty body)'}`);
    }
  }
  if (!response.ok) {
    throw new Error(
      errorMessageFromPayload(payload, `HTTP ${response.status} ${response.statusText}`),
    );
  }
  return payload as TResponse;
}
