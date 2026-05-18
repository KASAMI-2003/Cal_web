import { defineConfig } from 'vite';

const pythonOrigin = process.env.VITE_PYTHON_API_ORIGIN ?? 'http://127.0.0.1:3569';
const terminalWsPort = process.env.TERMINAL_WS_PORT ?? '8765';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api/ssh/ws': {
        target: `ws://127.0.0.1:${terminalWsPort}`,
        ws: true,
        changeOrigin: true,
      },
      '/api': pythonOrigin,
      '/data_input': pythonOrigin,
      '/mysql_receive': pythonOrigin,
      '/page2_search': pythonOrigin,
      '/mysql_changeData': pythonOrigin,
      '/create_matrix': pythonOrigin,
      '/create_lattice_picture': pythonOrigin,
      '/execute_ssh': pythonOrigin,
      '/websocket_port': pythonOrigin,
      '/img': {
        target: pythonOrigin,
        changeOrigin: true,
      },
    },
  },
});
