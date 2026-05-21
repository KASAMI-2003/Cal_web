-- Cal_web MySQL 初始化（在服务器上执行）
-- 用法：mysql -u root -p < deploy/mysql-init.sql
-- 若已有 py_server 用户，只需建库建表；数据请从本机 mysqldump 导入（见 deploy/mysql-import.md）

CREATE DATABASE IF NOT EXISTS `element`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `u_nb_database`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 应用使用的账号（已存在可跳过报错）
CREATE USER IF NOT EXISTS 'py_server'@'localhost' IDENTIFIED BY '123456';
GRANT ALL PRIVILEGES ON `element`.* TO 'py_server'@'localhost';
GRANT ALL PRIVILEGES ON `u_nb_database`.* TO 'py_server'@'localhost';
FLUSH PRIVILEGES;

USE `u_nb_database`;

-- 与 pyserver.py 中 SELECT / page2_search / data_input 写入一致
CREATE TABLE IF NOT EXISTS `materials` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `material_name` VARCHAR(512) NOT NULL COMMENT '材料名称，如 U-50at.%Nb',
  `u_at_pct` DECIMAL(10,4) NULL COMMENT 'U 原子百分比',
  `nb_at_pct` DECIMAL(10,4) NULL COMMENT 'Nb 原子百分比',
  `space_group_no` INT NULL COMMENT '空间群编号',
  `a` DOUBLE NULL COMMENT '晶格常数 a',
  `b` DOUBLE NULL COMMENT '晶格常数 b',
  `c` DOUBLE NULL COMMENT '晶格常数 c',
  `notes` TEXT NULL COMMENT '备注/相结构说明',
  `created_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `data_source` TEXT NULL COMMENT '数据来源',
  PRIMARY KEY (`id`),
  KEY `idx_material_name` (`material_name`(191)),
  KEY `idx_u_nb` (`u_at_pct`, `nb_at_pct`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- element.element_inf 列较多且因本地数据而异，请用本机 mysqldump 导入整表，勿只用此占位结构。
-- 若服务器完全没有 element_inf，可先建最小表（仅保证单元素查询不 1146）：
USE `element`;

CREATE TABLE IF NOT EXISTS `element_inf` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `元素` VARCHAR(64) NOT NULL,
  `晶体结构` VARCHAR(255) NULL,
  `晶格常数` VARCHAR(255) NULL,
  `弹性刚度常数C11` VARCHAR(64) NULL,
  `C12` VARCHAR(64) NULL,
  `杨氏模量E-H` VARCHAR(64) NULL,
  PRIMARY KEY (`id`),
  KEY `idx_element` (`元素`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
