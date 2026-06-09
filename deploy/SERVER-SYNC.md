# 本地已跑通 → 同步到生产服务器

本地与线上行为不一致，**99% 是服务器未部署最新 `server/pyserver.py` 与 `web/dist`**。

## 1. 同步后端（必做）

在服务器上（路径以 `/opt/cal_web/Cal_web` 为例）：

```bash
cd /opt/cal_web/Cal_web
# git pull 或 scp/rsync 上传整个 tsx-web-app

cd server
source .venv/bin/activate   # 若用虚拟环境
pip install -r requirements.txt -q

# 确认关键修复已存在（应能 grep 到）
grep -n "use_document_model=False" pyserver.py
grep -n "_mp_open_rester" pyserver.py
```

**必须包含的修复**（2026-06 本地联调）：

- `MPRester(..., use_document_model=False)` — MP 新 ID 格式（`mp-aaacsndk`）不再触发 Pydantic 报错
- `page2_search` 合并 MP 列表 + 本地缓存
- 单元素检索（如 H、Al）同时查 MP，不依赖本地 `element_inf`

## 2. 配置 MP_API_KEY（解封后）

```bash
sudo systemctl edit calweb-backend
# 添加：
# [Service]
# Environment=MP_API_KEY=你的32位密钥

sudo systemctl daemon-reload
sudo systemctl restart calweb-backend
```

## 3. 重新构建并部署前端（必做）

```bash
cd /opt/cal_web/Cal_web/web
cp .env.production.example .env.production   # 确认 VITE_PYTHON_API_ORIGIN=https://calweb.physedu.top
npm ci
npm run build
# dist/ 由 Nginx root 指向，无需单独拷贝
```

## 4. 重启与验证

```bash
sudo systemctl restart calweb-backend
bash deploy/verify-api.sh
```

期望输出示例：

- `page2 H MP: 10` 或更多（本地库无 H 也应能查到 MP）
- `get_data single mp-134: OK`
- `create_lattice_picture: OK`

## 5. MP 解封后关闭顶部横幅

编辑 `web/src/config/opsNotice.ts` → `SHOW_MP_API_BLOCKED_NOTICE = false`，再 `npm run build`。

## 常见问题

| 现象 | 原因 |
|------|------|
| 只能搜本地 U/Nb，搜不到 H/Al | 旧版 `pyserver.py`，未部署 MP 检索修复 |
| MP 计算报 `Invalid MPID Format` | 未部署 `use_document_model=False` |
| 检索/原胞 405 | Nginx 未反代 `/page2_search`、`/create_lattice_picture`（见 `nginx-calweb.conf.example` 第④块） |
| 检索 502 | `calweb-backend` 未运行或 3569 被占用 |
