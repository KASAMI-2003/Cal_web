-- 论文 element_inf 种子数据（表 A-2 能量-应变法，答辩/服务器部署用）
-- 用法：mysql -u py_server -p123456 element < deploy/thesis-element_inf.sql
-- 数值来源：毕业设计论文表 A-2 / 平台 VASP 能量-应变计算结果

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

USE `element`;

DROP TABLE IF EXISTS `element_inf`;

CREATE TABLE `element_inf` (
  `元素` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `备注` varchar(255) DEFAULT NULL,
  `晶体结构` varchar(50) DEFAULT NULL,
  `晶格常数` varchar(50) DEFAULT NULL,
  `晶格常数数据来源` varchar(255) DEFAULT NULL,
  `k取值` double DEFAULT NULL,
  `etmx` double DEFAULT NULL,
  `RESULT` varchar(50) DEFAULT NULL,
  `杨氏模量E-H` varchar(50) DEFAULT NULL,
  `理论值` varchar(50) DEFAULT NULL,
  `Column11` varchar(50) DEFAULT NULL,
  `相对误差` varchar(50) DEFAULT NULL,
  `体积模量B_H` varchar(50) DEFAULT NULL,
  `理论值_1` varchar(50) DEFAULT NULL,
  `Column15` varchar(50) DEFAULT NULL,
  `相对误差_1` varchar(50) DEFAULT NULL,
  `泊松比nu_H` double DEFAULT NULL,
  `理论值_2` varchar(50) DEFAULT NULL,
  `Column19` varchar(50) DEFAULT NULL,
  `相对误差_2` varchar(50) DEFAULT NULL,
  `弹性刚度常数C11` varchar(50) DEFAULT NULL,
  `理论值_3` varchar(50) DEFAULT NULL,
  `Column23` varchar(50) DEFAULT NULL,
  `相对误差_3` varchar(50) DEFAULT NULL,
  `C12` varchar(50) DEFAULT NULL,
  `理论值_4` varchar(50) DEFAULT NULL,
  `Column27` varchar(50) DEFAULT NULL,
  `相对误差_4` varchar(50) DEFAULT NULL,
  `C44` varchar(50) DEFAULT NULL,
  `C33` double DEFAULT NULL,
  `C13` double DEFAULT NULL,
  `Column32` varchar(50) DEFAULT NULL,
  KEY `idx_element` (`元素`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

TRUNCATE TABLE `element_inf`;

INSERT INTO `element_inf` (
  `元素`, `备注`, `晶体结构`, `晶格常数`, `晶格常数数据来源`,
  `k取值`, `etmx`, `杨氏模量E-H`, `体积模量B_H`, `泊松比nu_H`,
  `弹性刚度常数C11`, `C12`, `C44`, `C33`, `C13`
) VALUES
('Li', '论文表A-2 能量-应变', 'bcc', '3.49', 'CRC Handbook', 0.1, 0.03, '11.64', '14.19', 0.36, '14.99', '13.79', '11.5', NULL, NULL),
('Be', '论文表A-2 能量-应变', 'hcp', '2.84,2.84,4.70', 'CRC Handbook', 0.1, 0.03, '280.66', '123.05', 0.05, '250.54', '75.62', '165.65', 318.13, 11.4),
('Na', '论文表A-2 能量-应变', 'bcc', '4.23', 'Materials Project', 0.15, 0.03, '8.96', '7.97', 0.31, '9.73', '7.09', '6.42', NULL, NULL),
('Al', '论文表A-2 能量-应变', 'fcc', '4.05', 'CRC Handbook', 0.1, 0.03, '69.18', '77.86', 0.35, '100.9', '66.3', '32.24', NULL, NULL),
('Sc', '论文表A-2 能量-应变', 'bcc', '3.616', 'CRC Handbook', 0.15, 0.03, '82.11', '57.93', 0.26, '104.88', '39.89', '29.87', 107.36, 31.94),
('Ti', '论文表A-2 能量-应变', 'hcp', '2.950,2.950,4.683', 'CRC Handbook', 0.15, 0.03, '120.89', '117.8', 0.33, '181.86', '86.39', '29.99', 105.3, 31.7),
('V',  '论文表A-2 能量-应变', 'bcc', '3.030', '', 0.15, 0.03, '56.18', '189.22', 0.45, '282.68', '142.5', '4.88', NULL, NULL),
('Ni', '论文表A-2 能量-应变', 'fcc', '3.523', '', 0.15, 0.03, '198.91', '203.43', 0.34, '255.84', '177.22', '113.84', NULL, NULL),
('Cu', '论文表A-2 能量-应变; 实验对照 Simmons&Wang', 'fcc', '3.609', 'CRC Handbook', 0.15, 0.03, '128', '141.82', 0.34, '175.96', '124.75', '78.36', NULL, NULL),
('Zn', '论文表A-2 能量-应变', 'hcp', '2.660,2.660,4.940', '', 0.15, 0.03, '107.07', '69.71', 0.24, '185.74', '43.96', '31.81', 68.36, 42.91),
('Mo', '论文表A-2 能量-应变', 'bcc', '3.147', 'CRC Handbook', 0.15, 0.03, '316.52', '272.83', 0.31, '489.88', '164.31', '99.23', NULL, NULL),
('Rh', '论文表A-2 能量-应变', 'fcc', '3.802', '', 0.15, 0.03, '390.04', '263.99', 0.25, '421.4', '185.29', '187.09', NULL, NULL),
('Pd', '论文表A-2 能量-应变', 'fcc', '3.89', '', 0.1, 0.03, '118.05', '173.04', 0.39, '202.64', '158.23', '65.73', NULL, NULL),
('Ag', '论文表A-2 能量-应变', 'fcc', '4.086', '', 0.15, 0.01, '78.84', '97.46', 0.37, '110.56', '86.27', '43.22', NULL, NULL),
('Cd', '论文表A-2 能量-应变', 'hcp', '2.98,2.98,5.69', '', 0.1, 0.03, '38.65', '45.5', 0.36, '86.89', '48.81', '10.6', 44.24, 32.71),
('Hf', '论文表A-2 能量-应变', 'hcp', '3.19,3.19,5.16', '', 0.1, 0.03, '145.36', '114.3', 0.29, '189.26', '76.02', '53.62', 201.97, 74.21),
('Ta', '论文表A-2 能量-应变', 'bcc', '3.3', '', 0.15, 0.03, '165.03', '202.1', 0.36, '276.83', '164.73', '63.66', NULL, NULL),
('W',  '论文表A-2 能量-应变', 'bcc', '3.165', 'CRC Handbook', 0.15, 0.03, '399.46', '317.61', 0.29, '541.7', '205.56', '146.51', NULL, NULL),
('Re', '论文表A-2 能量-应变', 'hcp', '2.76,2.76,4.47', '', 0.1, 0.03, '461.03', '378.84', 0.3, '625.01', '276.79', '161.87', 680.21, 231.45),
('Os', '论文表A-2 能量-应变', 'hcp', '2.764,2.764,4.407', '', 0.15, 0.03, '657.21', '414.39', 0.24, '755.15', '229.08', '258.08', 835.88, 231.79),
('Ir', '论文表A-2 能量-应变', 'fcc', '3.84', '', 0.1, 0.03, '550.93', '355.66', 0.24, '592.42', '237.28', '257.4', NULL, NULL),
('Pt', '论文表A-2 能量-应变', 'fcc', '3.92', '', 0.15, 0.03, '164.19', '253.62', 0.39, '313.52', '223.67', '70.75', NULL, NULL);

SET FOREIGN_KEY_CHECKS = 1;
