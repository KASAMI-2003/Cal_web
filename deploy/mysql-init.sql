-- Cal_web MySQL 初始化（在服务器上执行）
-- 用法：mysql -u root -p < deploy/mysql-init.sql
-- 数据：使用论文种子 deploy/thesis-element_inf.sql + deploy/thesis-materials.sql（见 deploy/mysql-import.md）

CREATE DATABASE IF NOT EXISTS `element`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `u_nb_database`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'py_server'@'localhost' IDENTIFIED BY '123456';
GRANT ALL PRIVILEGES ON `element`.* TO 'py_server'@'localhost';
GRANT ALL PRIVILEGES ON `u_nb_database`.* TO 'py_server'@'localhost';
FLUSH PRIVILEGES;

USE `u_nb_database`;

CREATE TABLE IF NOT EXISTS `materials` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `material_name` VARCHAR(512) NOT NULL COMMENT '材料名称，如 U-50at.%Nb',
  `u_at_pct` DECIMAL(10,4) NOT NULL COMMENT 'U 原子百分比',
  `nb_at_pct` DECIMAL(10,4) NOT NULL COMMENT 'Nb 原子百分比',
  `space_group_no` INT NULL COMMENT '空间群编号',
  `data_source` TEXT NULL COMMENT '数据来源',
  `a` DOUBLE NOT NULL COMMENT '晶格常数 a (Å)',
  `b` DOUBLE NOT NULL COMMENT '晶格常数 b (Å)',
  `c` DOUBLE NOT NULL COMMENT '晶格常数 c (Å)',
  `alpha` DOUBLE DEFAULT 90 COMMENT '晶格角 α (°)',
  `beta` DOUBLE DEFAULT 90 COMMENT '晶格角 β (°)',
  `gamma` DOUBLE DEFAULT 90 COMMENT '晶格角 γ (°)',
  `formation_energy` DOUBLE NULL COMMENT '形成能 (eV/atom)',
  `data_type` ENUM('experimental','calculated') NOT NULL DEFAULT 'calculated',
  `notes` TEXT NULL COMMENT '备注/相结构说明',
  `created_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_material_name` (`material_name`(191)),
  KEY `idx_u_nb` (`u_at_pct`, `nb_at_pct`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

USE `element`;

CREATE TABLE IF NOT EXISTS `element_inf` (
  `元素` VARCHAR(50) DEFAULT NULL,
  `备注` VARCHAR(255) DEFAULT NULL,
  `晶体结构` VARCHAR(50) DEFAULT NULL,
  `晶格常数` VARCHAR(50) DEFAULT NULL,
  `晶格常数数据来源` VARCHAR(255) DEFAULT NULL,
  `k取值` DOUBLE DEFAULT NULL,
  `etmx` DOUBLE DEFAULT NULL,
  `RESULT` VARCHAR(50) DEFAULT NULL,
  `杨氏模量E-H` VARCHAR(50) DEFAULT NULL,
  `理论值` VARCHAR(50) DEFAULT NULL,
  `Column11` VARCHAR(50) DEFAULT NULL,
  `相对误差` VARCHAR(50) DEFAULT NULL,
  `体积模量B_H` VARCHAR(50) DEFAULT NULL,
  `理论值_1` VARCHAR(50) DEFAULT NULL,
  `Column15` VARCHAR(50) DEFAULT NULL,
  `相对误差_1` VARCHAR(50) DEFAULT NULL,
  `泊松比nu_H` DOUBLE DEFAULT NULL,
  `理论值_2` VARCHAR(50) DEFAULT NULL,
  `Column19` VARCHAR(50) DEFAULT NULL,
  `相对误差_2` VARCHAR(50) DEFAULT NULL,
  `弹性刚度常数C11` VARCHAR(50) DEFAULT NULL,
  `理论值_3` VARCHAR(50) DEFAULT NULL,
  `Column23` VARCHAR(50) DEFAULT NULL,
  `相对误差_3` VARCHAR(50) DEFAULT NULL,
  `C12` VARCHAR(50) DEFAULT NULL,
  `理论值_4` VARCHAR(50) DEFAULT NULL,
  `Column27` VARCHAR(50) DEFAULT NULL,
  `相对误差_4` VARCHAR(50) DEFAULT NULL,
  `C44` VARCHAR(50) DEFAULT NULL,
  `C33` DOUBLE DEFAULT NULL,
  `C13` DOUBLE DEFAULT NULL,
  `Column32` VARCHAR(50) DEFAULT NULL,
  KEY `idx_element` (`元素`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
