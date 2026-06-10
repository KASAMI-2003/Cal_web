# MySQL 部署到服务器

本地能跑、服务器报 `Table 'u_nb_database.materials' doesn't exist`，说明**服务器缺表或缺数据**。

## 推荐：论文种子数据（答辩/生产）

仓库已包含与毕业论文一致的精简数据，**无需**再从本机 mysqldump 113 行全量 dump。

```bash
cd /opt/cal_web/Cal_web   # 项目根目录

# 1. 建库建表（只需一次）
mysql -u root -p < deploy/mysql-init.sql

# 2. 导入论文数据（会 DROP 并重建表 + 写入种子行）
mysql -u py_server -p123456 < deploy/thesis-element_inf.sql
mysql -u py_server -p123456 < deploy/thesis-materials.sql
```

验证：

```bash
mysql -u py_server -p123456 -e "SELECT COUNT(*) AS n FROM element.element_inf;"
mysql -u py_server -p123456 -e "SELECT 元素, \`弹性刚度常数C11\`, C12, C44 FROM element.element_inf WHERE 元素='Cu';"
mysql -u py_server -p123456 -e "SELECT COUNT(*) AS n FROM u_nb_database.materials;"
mysql -u py_server -p123456 -e "SELECT id, material_name, space_group_no FROM u_nb_database.materials WHERE u_at_pct=50 AND nb_at_pct=50 LIMIT 3;"
```

预期：

| 表 | 行数 | 说明 |
|----|------|------|
| `element.element_inf` | 22 | 论文表 A-2 能量-应变（Li–Pt，含 Cu 175.96/124.75/78.36 GPa） |
| `u_nb_database.materials` | 36 | 纯 U/Nb、COD 等原子、Zhang Vegard 21 点、Beeler/Brown/Pan |

### 种子文件说明

| 文件 | 内容 |
|------|------|
| `deploy/thesis-element_inf.sql` | 单元素弹性常数（能量-应变法，与论文表 3-2 / 附录 A-2 一致） |
| `deploy/thesis-materials.sql` | U–Nb 结构库（γ 相 bcc Im-3m=229，已剔除 MP/OQMD 冗余） |
| `deploy/mysql-init.sql` | 建库、用户 `py_server`、空表结构 |

---

## 备选：从本机 mysqldump 同步

若需与本机 MySQL **完全一致**（含 MP/OQMD 全量 113 行），仍可用本机导出：

**不要用 PowerShell 的 `>` 重定向**（会生成 UTF-16，Linux 导入报 `ASCII '\0'`）。

```powershell
cd C:\Users\24991\Desktop\挑战杯\WEB_FILE\tsx-web-app\web
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -u py_server -p --default-character-set=utf8mb4 --skip-lock-tables --single-transaction --result-file=element_inf.sql element element_inf
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -u py_server -p --default-character-set=utf8mb4 --skip-lock-tables --single-transaction --result-file=materials.sql u_nb_database materials
```

上传到服务器后：

```bash
mysql -u py_server -p123456 element < element_inf.sql
mysql -u py_server -p123456 u_nb_database < materials.sql
```

若出现 UTF-16 错误：

```bash
iconv -f UTF-16LE -t UTF-8//IGNORE element_inf.sql -o element_inf_utf8.sql
mysql -u py_server -p123456 element < element_inf_utf8.sql
```

---

## 导入后

改 MySQL 后 **不用** 重启 `calweb-backend`，刷新页面即可。

前端若刚部署：

```bash
cd web && npm run build
sudo systemctl restart calweb-backend   # 仅当更新了后端代码时需要
```

## 常见问题

| 错误 | 处理 |
|------|------|
| `1044 Access denied` | `GRANT ALL ON u_nb_database.* TO 'py_server'@'localhost'; FLUSH PRIVILEGES;` |
| `1049 Unknown database` | 先执行 `deploy/mysql-init.sql` |
| `1146 Table doesn't exist` | 先 `mysql-init.sql`，再导入 thesis 种子 |
| `ASCII '\0'` 导入失败 | 用 `--result-file` 重新导出，或 `iconv` 转码 |
| 查 Cu 无弹性数据 | 确认已导入 `thesis-element_inf.sql`，`SELECT * FROM element.element_inf WHERE 元素='Cu'` |
