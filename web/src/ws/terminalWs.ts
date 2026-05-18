import { pythonApi } from '../api/pythonApi';

function buildWebSocketUrl(port: number): string {
  const origin = import.meta.env.VITE_PYTHON_API_ORIGIN;
  if (origin) {
    const parsed = new URL(origin);
    const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${parsed.hostname}:${port}`;
  }
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.hostname}:${port}`;
}

function buildBridgeWebSocketUrl(): string {
  // 必须用「当前页面」的 host（开发时即 Vite），才能走 vite.config 里对 `/api/ssh/ws` 的代理。
  // 若误用 VITE_PYTHON_API_ORIGIN（Python 仅 HTTP，如 3569），会得到 ws://…:3569/… ，该端口不做 WebSocket 升级，终端永远连不上。
  const path = import.meta.env.VITE_TERMINAL_BRIDGE_PATH || '/api/ssh/ws';
  const u = new URL(path.startsWith('/') ? path : `/${path}`, window.location.href);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  return u.toString();
}

/**
 * 终端 WebSocket（默认 bridge）：与 WINDOWS/ssh-bridge 一致 — `/api/ssh/ws`，首包 auth JSON，后为二进制 PTY。
 * legacy：直连 pyserver 公布的 TCP WebSocket 端口（旧版 subprocess 终端；新版后端请用 bridge）。
 */
export async function openTerminalSocket(): Promise<WebSocket> {
  const mode = (import.meta.env.VITE_TERMINAL_CONNECTION_MODE || 'bridge').toLowerCase();
  let wsUrl = '';
  if (mode === 'bridge') {
    wsUrl = buildBridgeWebSocketUrl();
  } else {
    try {
      const portResp = await pythonApi.getWebsocketPort();
      if (!portResp.port) {
        throw new Error('WebSocket 端口不可用');
      }
      wsUrl = buildWebSocketUrl(portResp.port);
    } catch {
      wsUrl = buildBridgeWebSocketUrl();
    }
  }
  const ws = new WebSocket(wsUrl);
  ws.binaryType = 'arraybuffer';
  return ws;
}
