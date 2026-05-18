# TSX 前端 + Python API（独立目录）

本目录是从 `WEB_FILE/主页面` 拆出的**可单独拷贝/部署**的一套工程：

| 子目录 | 说明 |
|--------|------|
| **`web/`** | React + TypeScript + Vite 前端（样式自包含，不依赖上级目录） |
| **`server/`** | `pyserver.py`、素材 (`img/`)、数字孪生、`data_fitting`、`automation`、`database`（Rust）等后端运行所需文件；旧版独立 HTML/JS 静态页已从本副本移除 |

原「主页面」仓库里的 `frontend/` 仍可照旧使用；这里是一份**副本**，便于单独打包或放进新 Git 仓库。

## 本地开发

### 1. 启动 Python API（终端 A）

```bash
cd server
pip install -r requirements.txt
# 按原项目习惯补全 mp_api、ase、mysql、flask 等依赖（与原 pyserver 一致）
python pyserver.py
```

也可在 `tsx-web-app/` 根目录执行 `python server/pyserver.py`：`pyserver` 会切换到 `server/` 再启动，静态资源路径与 `cargo run` 均相对于该目录解析。

- 注意控制台里打印的 **HTTP 端口**（常为 `3569` 附近，可能自动顺延）。
- `pyserver` 仍会尝试 `cargo run` 启动 `database/`（需本机安装 Rust toolchain）。

### 2. 启动前端（终端 B）

```bash
cd web
npm install
```

在 `web/` 下创建 `.env`（可参考 `.env.example`），例如：

```env
VITE_PYTHON_API_ORIGIN=http://127.0.0.1:3569
VITE_RUST_API_ORIGIN=http://127.0.0.1:8088
```

端口 **`3569` 请改成与终端 A 中 Python 打印的一致**。

```bash
npm run dev
```

浏览器访问 Vite 提示的地址（默认 `http://localhost:5173`）。

### 3. 静态资源说明

开发模式下，Vite 会把 `/api`、`/img` 等代理到 `VITE_PYTHON_API_ORIGIN`（见 `web/vite.config.ts`）。  
请保证 **先启动 `server/`**，否则图片与接口会失败。

### 4. 可视化页远程终端（SSH / WebSocket）

终端在浏览器里连接的是 **`/api/ssh/ws`（相对当前页面，即 Vite 的 host:5173）**，再由 Vite 转到本机 Python 上的终端 WebSocket 端口（默认与环境变量 `TERMINAL_WS_PORT` 一致，多为 `8765`）。`VITE_PYTHON_API_ORIGIN` 只对应 **HTTP API**，不能用来连终端；若 Python 日志提示终端端口已从默认值改掉，请在启动 `npm run dev` 的环境里同步设置相同的 `TERMINAL_WS_PORT`。

## 与旧目录的关系

- 顶栏样式在 `web/src/styles/nav.css`，入口见 `web/src/main.tsx`。
- 页面与路由全部由 **`web/`** 提供；`GET /` 仅返回 API 说明（HTML），请勿将其当作主界面。
