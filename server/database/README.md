# Rust 文件数据库服务

基于 JSON 文件的轻量数据库，提供 HTTP API，用于用户登录/注册与化合物数据存储。

## 构建与运行

```bash
cd database
cargo build --release
cargo run
```

服务默认监听 `127.0.0.1:8088`。

## API 说明

### 健康检查

- **GET** `/health`  
  返回 `{"status":"ok"}`，用于确认服务已就绪（如 pyserver 启动前可轮询此接口）。

### 用户

- **POST** `/register`  
  Body: `{"username":"...", "password":"..."}`  
  返回 JSON: `{"success": true/false, "message": "..."}`

- **POST** `/login`  
  Body: `{"username":"...", "password":"..."}`  
  返回 JSON: `{"success": true/false, "message": "..."}`

### 化合物（与前端 /mysql_receive 兼容）

- **GET** `/compounds`  
  - 无参数：返回全部化合物。  
  - 查询参数 `元素=xxx`：按元素筛选。  
  返回 JSON: `{"success": true, "data": [ {...}, ... ]}`

- **POST** `/compounds/query`（与 Python `/mysql_receive` 协议一致）  
  Body: `{"element": "2U-Nb", "text": "晶体结构,晶格常数,弹性刚度常数C11,C12,杨氏模量E-H"}`  
  返回 JSON: `{"message": [v1, v2, v3, v4, v5]}`（按 `text` 中列顺序；无记录时为 `null`）。

- **POST** `/compounds`  
  Body: 单条记录的键值对，需包含 `元素` 等字段。  
  返回 JSON: `{"success": true/false, "message": "..."}`

- **PUT** `/compounds`  
  Body: 必须包含 `元素`（用于定位），其余为要更新的字段。  
  返回 JSON: `{"success": true/false, "message": "..."}`

- **DELETE** `/compounds?元素=xxx`  
  按元素删除一条记录。  
  返回 JSON: `{"success": true/false, "message": "..."}`

## 与 Python 服务配合（可选）

可视化页当前通过 Python 的 `/mysql_receive` 从 MySQL 取化合物数据。若希望改用 Rust 文件库：

1. 保证 Rust 服务先启动（可轮询 `GET http://127.0.0.1:8088/health`）。
2. 在 `pyserver.py` 中，对 `/mysql_receive` 做一次代理到 Rust：
   - 收到 POST 后，将 body 原样转发到 `POST http://127.0.0.1:8088/compounds/query`。
   - 将 Rust 返回的 `{"message": [...]}` 作为 `/mysql_receive` 的响应返回给前端。

这样前端无需改请求地址和参数，仅后端数据源从 MySQL 换为 Rust 文件库。

## 数据目录

- 数据与表结构存放在 `test_data/`：
  - `schema.json`：表结构（列名与类型）。
  - `users.json`、`compounds.json` 等：各表数据。

若需与前端列名完全一致，可清空或重命名现有 `test_data/schema.json` 与 `test_data/compounds.json` 后重启服务，让程序按 `main.rs` 中的 `compound_columns` 重新建表（含 `晶体结构`、`晶格常数`、`弹性刚度常数C11`、`C12`、`杨氏模量E-H` 等）。
