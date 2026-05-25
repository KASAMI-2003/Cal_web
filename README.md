# TSX 前端 + Python API（独立目录）

> **⚠ 已知问题（2026-05，待后续处理）**  
> **生产服务器**（`calweb.physedu.top` / 阿里云）访问 **Materials Project API 已被封禁**（HTTP 403，公网 IP 被 MP 标记为 abusive traffic）。  
> - **线上**：元素检索只能看到 **本地 MySQL**（`element_inf`、`u_nb_database`），**不会有 `mp-xxxxx` 结果**。  
> - **本地 Windows 开发环境**：MP-API 仍可用。  
> - **解封步骤**：`curl -s ifconfig.me` 查公网 IP → 发邮件至 **support@materialsproject.org** 说明用途并申请解封 → 在 systemd 配置 **`MP_API_KEY`**（勿用仓库默认 key）→ 重启 `calweb-backend`。  
> - 详细说明见 **[deploy/MP-API-NOTICE.md](deploy/MP-API-NOTICE.md)**；前端全站顶栏有临时提示，解封后改 `web/src/config/opsNotice.ts` 关闭。

本目录是从 `WEB_FILE/主页面` 拆出的**可单独拷贝/部署**的一套工程：

| 子目录 | 说明 |
|--------|------|
| **`web/`** | React + TypeScript + Vite 前端（样式自包含，不依赖上级目录） |
| **`server/`** | `pyserver.py`、素材 (`img/`)、数字孪生、`data_fitting`、`automation`、`database`（Rust）等后端运行所需文件；旧版独立 HTML/JS 静态页已从本副本移除 |

原「主页面」仓库里的 `frontend/` 仍可照旧使用；这里是一份**副本**，便于单独打包或放进新 Git 仓库。

## 本地开发

### 1. 启动 Python API（终端 A）

在 `server/` 目录使用虚拟环境并安装依赖（**仅需执行一次**）：

**Windows（PowerShell）：**

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
python pyserver.py
```

**Linux / macOS：**

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
python3 pyserver.py
```

`requirements.txt` 已覆盖 `pyserver.py` 及子模块所需包（`mp-api`、`mysql-connector-python`、`ase`、`matplotlib`、`Flask`、`pandas`、`scipy`、`paramiko`、`websockets` 等）。可选 Celery 示例见 `server/requirements-optional.txt`。环境变量说明见 `server/.env.example`。

**数字孪生 HTEM（必装，否则无法生成各向异性 3D 曲面）**

数字孪生页依赖 HTEM 半解析模型（SAM）与 Fedorov 各向异性计算，需将 **HTEM 源码** 放到 `server/digital_twin/HTEM-main/`（或通过环境变量 `HTEM_ROOT` 指向该目录）。**不是 pip 包**。

一键安装**最小运行时**（约 1MB，含 `source/` + Si 示例 `Elasticity_cold+NVT_s4.dat`，不含 VASP 参考算例）：

```powershell
# Windows（在 tsx-web-app 根目录）
.\scripts\setup_htem.ps1
```

```bash
# Linux / macOS
chmod +x scripts/setup_htem.sh
./scripts/setup_htem.sh
```

脚本会优先从同级目录 `WEB_FILE/digital_twin/HTEM-main` 复制；也可手动指定路径：`./scripts/setup_htem.sh /path/to/HTEM-main`。

安装后重启 `pyserver`。若 HTEM 仍不可用，后端会回退 NumPy 占位曲面（精度低于 SAM，仅作兜底）。

也可在 `server/.env` 中设置 `HTEM_ROOT=/path/to/HTEM-main`。

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

- Python 侧建议使用 **`python3`** + **`server/.venv`**，依赖安装见上文「启动 Python API」一节（`pip install -r requirements.txt`）。
- 私钥路径与 Windows 相同逻辑：默认读取 **`~/.ssh/id_ed25519`** 或 **`id_rsa`**（`expanduser` 在各平台为当前用户主目录）。
- 若机器未安装 Rust / `cargo`，`pyserver` 会跳过 `database/` 子进程并打日志；不需要 Rust API 时可设置环境变量 **`TSX_SKIP_RUST_SERVER=1`** 主动跳过。
- **`digital_twin_user_registry.json`** 中的 `disk_path` 应为相对 `server/` 的路径（仓库内已修正）；旧版若仍为 Windows 绝对路径，启动后会在能解析到文件时自动改写为相对路径。

### 3. 静态资源说明

开发模式下，Vite 会把 `/api`、`/img` 等代理到 `VITE_PYTHON_API_ORIGIN`（见 `web/vite.config.ts`）。  
请保证 **先启动 `server/`**，否则图片与接口会失败。

### 4. 可视化页远程终端（SSH / WebSocket）

终端在浏览器里连接的是 **`/api/ssh/ws`（相对当前页面，即 Vite 的 host:5173）**，再由 Vite 转到本机 Python 上的终端 WebSocket 端口（默认与环境变量 `TERMINAL_WS_PORT` 一致，多为 `8765`）。`VITE_PYTHON_API_ORIGIN` 只对应 **HTTP API**，不能用来连终端；若 Python 日志提示终端端口已从默认值改掉，请在启动 `npm run dev` 的环境里同步设置相同的 `TERMINAL_WS_PORT`。

## VASP 弹性常数入库

在 **OUTCAR 或汇总表所在目录** 执行 CLI，自动 Born/Mouhat 检验后提交管理员审核（`element_inf`）。

```bash
# 1. 准备汇总文件（任选其一放在当前目录）
#    elastic_import.json | elastic_results.txt | summary.csv | OUTCAR(含 ELASTIC TENSOR)

# 2. 提交（示例：Cu fcc 应力-应变法）
python scripts/vasp_import.py \
  --username admin \
  --element Cu \
  --structure fcc \
  --method stress_strain \
  --scan-dir .

# 3. 仅本地检验、不提交 API
python scripts/vasp_import.py ... --dry-run

# 4. 命令行直接指定 Cij（GPa）
python scripts/vasp_import.py --username admin --element Cu --structure fcc \
  --method energy_strain --c11 175.96 --c12 124.75 --c44 78.36
```

- API：`POST /api/vasp/import`（与 CLI 相同 JSON 字段）
- 可视化页 **终端 → VASP 入库** 可一键向已连接 SSH 终端插入上述命令
- 示例汇总：`scripts/examples/elastic_import.json`
- 稳定性未通过时 **自动退回**，不进入待审核队列

**在服务器（SSH 远程）上使用终端按钮时：**

1. 将 `scripts/vasp_import.py` 与 `server/vasp_import/` 部署到服务器（与 `pyserver.py` 同仓库），例如 `/opt/cal_web/Cal_web/`。
2. 在可视化页「脚本路径」填 **远程绝对路径**：`/opt/cal_web/Cal_web/scripts/vasp_import.py`（勿用单引号包 `~`）。
3. 「Python 命令」默认 `python3.11`（系统 `python3` 若为 3.6 会报 `future feature annotations is not defined`）。可用 `python3.11 --version` 确认。
4. 在 `web/.env` 配置 **远程可访问的 API**（命令在 SSH 机执行，`localhost:5173` 无效）：
   ```env
   VITE_PYTHON_API_ORIGIN=http://127.0.0.1:3569
   # 或与 Nginx 同域：
   VITE_VASP_IMPORT_API_URL=https://calweb.physedu.top
   ```
   pyserver 与 SSH 在同一台云主机时，常用 `http://127.0.0.1:3569`。
5. `cd` 到含 `elastic_import.json` 或 `OUTCAR` 的计算目录后再点按钮。

本地浏览器 + 远程 SSH 联调时，若仍看到 API 为 `5173`，请创建 `web/.env` 并重启 `npm run dev`。

---

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

> **数字孪生 HTEM**：部署后需执行 `./scripts/setup_htem.sh`（或把 `HTEM-main` 放到 `server/digital_twin/HTEM-main`），否则 `/api/digital_twin/anisotropy_surface` 只能走占位回退。详见上文「数字孪生 HTEM（必装）」。

> **MP-API**：若线上 MP 检索 403，见 **[deploy/MP-API-NOTICE.md](deploy/MP-API-NOTICE.md)**（当前生产 IP 待 MP 解封）。

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
