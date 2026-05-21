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

**不要用 PowerShell 的 `>` 重定向**（会生成 UTF-16，Linux 导入报 `ASCII '\0'`）。

**推荐：用 mysqldump 的 `--result-file` 直接写 UTF-8 文件**（不经过 shell 重定向）。

在 **PowerShell** 里路径含空格，必须用 `&` 调用：

```powershell
cd C:\Users\24991\Desktop\挑战杯\WEB_FILE\tsx-web-app\web

& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -u py_server -p --default-character-set=utf8mb4 --skip-lock-tables --single-transaction --result-file=element_inf.sql element element_inf
```

或在 **cmd** 里：

```cmd
cd C:\Users\24991\Desktop\挑战杯\WEB_FILE\tsx-web-app\web
"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -u py_server -p --default-character-set=utf8mb4 --skip-lock-tables --single-transaction --result-file=element_inf.sql element element_inf
```

（把 MySQL 路径改成你本机实际安装路径。）

备选 cmd 重定向：

```cmd
cmd /c "mysqldump -u py_server -p --default-character-set=utf8mb4 --skip-lock-tables --single-transaction u_nb_database materials > materials.sql"
```

若本机 MySQL 不在 PATH，用完整路径，例如：
`"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"`

## 3. 上传到服务器并导入

若已在 Linux 上出现 `ASCII '\0'` 错误，说明 SQL 是 UTF-16，先转码：

```bash
cd /opt/cal_web/Cal_web/web   # 或 sql 文件所在目录
file materials.sql            # 若显示 UTF-16，必须转码
iconv -f UTF-16LE -t UTF-8//IGNORE materials.sql -o materials_utf8.sql
iconv -f UTF-16LE -t UTF-8//IGNORE element_inf.sql -o element_inf_utf8.sql
mysql -u py_server -p123456 u_nb_database < materials_utf8.sql
mysql -u py_server -p123456 element < element_inf_utf8.sql
```

正常 UTF-8 文件可直接：

```bash
mysql -u py_server -p123456 u_nb_database < materials.sql
mysql -u py_server -p123456 element < element_inf.sql
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
| `ASCII '\0'` 导入失败 | Windows PowerShell `>` 生成了 UTF-16 → 用 `--result-file` 重新导出，或 `iconv` 转码 |
| `element_inf` 1064 语法错误 | UTF-16 经 iconv 后中文列名乱码 → **必须**用 `--result-file` 重新导出 `element_inf.sql` |
| 本机表结构多列 | 以本机 `mysqldump` 为准覆盖服务器表（会带上完整 CREATE TABLE） |

若本机 `materials` 表列比 `mysql-init.sql` 多，**优先用 mysqldump 整表导出**，不要只用手写建表 SQL。
