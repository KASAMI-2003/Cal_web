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
- 若已在 PATH 中找到 **`cargo`**，`pyserver` 会启动 `database/`（Rust）；否则跳过（见下文 Linux 说明与环境变量 `TSX_SKIP_RUST_SERVER`）。

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

### 一键启动（前后端同机开发）

先完成 **`web/`：`npm install`**，以及 **`server/`** 依赖与（可选）**`web/.env`**（端口与「终端 B」一致）。

**Linux / macOS / Git Bash：**

```bash
chmod +x scripts/start-all.sh   # 仅需一次
bash scripts/start-all.sh
```

**Windows PowerShell（项目根目录）：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-all.ps1
```

脚本会先拉起 **`server/pyserver.py`**（若存在 **`server/.venv`** 会自动使用该环境），再执行 **`web` 的 `npm run dev`**。按 **Ctrl+C** 结束前端时会一并结束后端进程。

可选环境变量：**`PYTHON`**（指定 Python 可执行文件）、**`TERMINAL_WS_PORT`**、**`TSX_SKIP_RUST_SERVER=1`**（无 cargo 时）。

### Linux / macOS 说明

- Python 侧建议使用 **`python3`**，并在 `server/` 下用虚拟环境安装依赖，例如：
  ```bash
  cd server
  python3 -m venv .venv
  source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
  pip install -r requirements.txt
  python3 pyserver.py
  ```
- 私钥路径与 Windows 相同逻辑：默认读取 **`~/.ssh/id_ed25519`** 或 **`id_rsa`**（`expanduser` 在各平台为当前用户主目录）。
- 若机器未安装 Rust / `cargo`，`pyserver` 会跳过 `database/` 子进程并打日志；不需要 Rust API 时可设置环境变量 **`TSX_SKIP_RUST_SERVER=1`** 主动跳过。
- **`digital_twin_user_registry.json`** 中的 `disk_path` 应为相对 `server/` 的路径（仓库内已修正）；旧版若仍为 Windows 绝对路径，启动后会在能解析到文件时自动改写为相对路径。

### 3. 静态资源说明

开发模式下，Vite 会把 `/api`、`/img` 等代理到 `VITE_PYTHON_API_ORIGIN`（见 `web/vite.config.ts`）。  
请保证 **先启动 `server/`**，否则图片与接口会失败。

### 4. 可视化页远程终端（SSH / WebSocket）

终端在浏览器里连接的是 **`/api/ssh/ws`（相对当前页面，即 Vite 的 host:5173）**，再由 Vite 转到本机 Python 上的终端 WebSocket 端口（默认与环境变量 `TERMINAL_WS_PORT` 一致，多为 `8765`）。`VITE_PYTHON_API_ORIGIN` 只对应 **HTTP API**，不能用来连终端；若 Python 日志提示终端端口已从默认值改掉，请在启动 `npm run dev` 的环境里同步设置相同的 `TERMINAL_WS_PORT`。

## 生产部署（Nginx + systemd）

### 服务分工

| 服务 | 端口 | 用途 |
|------|------|------|
| **Rust `database/`** | `8088` | **注册、登录、用户资料**（`/register`、`/login`、`/users/*`） |
| **Python `pyserver.py`** | `3569`（附近） | 业务 API、`/api/*`、`/img`、WebSocket 终端 |
| **Nginx** | `443` | 静态前端 + 反代上述服务 |

**注册 405 的常见原因**：前端请求 `POST /register`，但 Nginx 只配置了静态 `location /`，未把 `/register` 反代到 **8088**。

### 1. 构建前端

```bash
cd web
cp .env.production.example .env.production   # 改成你的 HTTPS 域名
npm ci
npm run build
```

`.env.production` 示例：

```env
VITE_PYTHON_API_ORIGIN=https://calweb.physedu.top
VITE_RUST_API_ORIGIN=https://calweb.physedu.top
```

### 2. Nginx

参考 **[deploy/nginx-calweb.conf.example](deploy/nginx-calweb.conf.example)** 复制到 `/etc/nginx/conf.d/cal_web.conf`。

要点：

- **`/register`、`/login`、`/users/`** → `127.0.0.1:8088`（Rust）
- **`/api/`** → `127.0.0.1:3569`（Python，**不要** `rewrite` 去掉 `/api` 前缀）
- **`/api/ssh/ws`** → 终端 WebSocket 端口（默认 `8765`）

### 3. 后端常驻（systemd 示例）

只保留 **一个** `pyserver` 进程；若手动 `python pyserver.py` 与 systemd 同时跑，会出现 `Address already in use`，HTTP 起不来只剩 WebSocket。

```bash
sudo systemctl stop calweb-backend    # 手动调试前先停服务
# 确认 3569 / 8765 未被占用
sudo ss -tlnp | grep -E '3569|8088|8765'
sudo systemctl start calweb-backend
```

确认 Rust 在监听：

```bash
curl -s http://127.0.0.1:8088/health
curl -s http://127.0.0.1:3569/ -o /dev/null -w '%{http_code}\n'
```

**502 的常见原因**：Nginx 已反代 `/register` → 8088，但 Rust 未启动。systemd 里若 PATH 不含 `~/.cargo/bin`，`cargo` 找不到会直接跳过 Rust。解决：先 `cargo build --release`，再用 **[deploy/calweb-backend.service.example](deploy/calweb-backend.service.example)**（含 PATH）重启服务。

## 与旧目录的关系

- 顶栏样式在 `web/src/styles/nav.css`，入口见 `web/src/main.tsx`。
- 页面与路由全部由 **`web/`** 提供；`GET /` 仅返回 API 说明（HTML），请勿将其当作主界面。
