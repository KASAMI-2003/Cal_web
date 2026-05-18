# TSX 前端（独立工程内 `web/`）

本目录属于上级 **[tsx-web-app](../README.md)** 中的前端部分；本地开发须先启动 `server/` 中的 Python API。

## 运行

```bash
npm install
npm run dev
```

## 页面路由（TSX）

- `/` 主页面
- `/login`、`/register`、`/profile`、`/admin`
- `/data-input`、`/data-fitting`
- `/digital-twin`、`/visualization`

## 前后端

- 前端通过 `VITE_PYTHON_API_ORIGIN`（Python）与 `VITE_RUST_API_ORIGIN`（Rust）配置后端地址。
- 开发环境可用 Vite 代理转发 `/api`、`/img`、`/data_input` 等，避免跨域调试问题。

## 后端契约

- 契约说明：`docs/API_CONTRACT.md`
