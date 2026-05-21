# MySQL 从本机同步到服务器

本地能跑、服务器报 `Table 'u_nb_database.materials' doesn't exist`，说明**服务器缺表或缺数据**。

## 1. 服务器：建库建表（只需一次）

```bash
cd /opt/cal_web/Cal_web
mysql -u root -p < deploy/mysql-init.sql
```

验证：

```bash
mysql -u py_server -p123456 -e "SHOW TABLES FROM u_nb_database;"
mysql -u py_server -p123456 -e "DESCRIBE u_nb_database.materials;"
```

应看到 `materials` 表。

## 2. 本机：导出数据

在**本地 Windows**（MySQL 能正常查 U-Nb 材料的那台）：

```powershell
# 导出 U-Nb 化合物表（含 103–113 等本地数据）
mysqldump -u py_server -p u_nb_database materials > materials.sql

# 建议一并导出单元素表（可选但推荐）
mysqldump -u py_server -p element element_inf > element_inf.sql
```

若本机 MySQL 不在 PATH，用完整路径，例如：
`"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"`

## 3. 上传到服务器并导入

```bash
# 在服务器
mysql -u py_server -p123456 u_nb_database < materials.sql
mysql -u py_server -p123456 element < element_inf.sql   # 若有
```

检查行数：

```bash
mysql -u py_server -p123456 -e "SELECT COUNT(*) FROM u_nb_database.materials;"
mysql -u py_server -p123456 -e "SELECT id, material_name FROM u_nb_database.materials LIMIT 5;"
```

## 4. 无需重启

改 MySQL 后 **不用** 重启 `calweb-backend`，直接刷新页面再试「数据输入审核 → 写入 materials」。

## 常见问题

| 错误 | 处理 |
|------|------|
| `1044 Access denied` | `GRANT ALL ON u_nb_database.* TO 'py_server'@'localhost'; FLUSH PRIVILEGES;` |
| `1049 Unknown database` | 先执行 `deploy/mysql-init.sql` |
| `1146 Table doesn't exist` | 缺表 → `mysql-init.sql`；有表无数据 → 本机 `mysqldump` 导入 |
| 本机表结构多列 | 以本机 `mysqldump` 为准覆盖服务器表（会带上完整 CREATE TABLE） |

若本机 `materials` 表列比 `mysql-init.sql` 多，**优先用 mysqldump 整表导出**，不要只用手写建表 SQL。
