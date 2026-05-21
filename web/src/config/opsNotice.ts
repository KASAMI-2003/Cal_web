/**
 * 运维提示（临时）。MP 解封并完成 API 优化后，将 SHOW_MP_API_BLOCKED_NOTICE 改为 false。
 * 详见仓库根目录 README「已知问题」与 deploy/MP-API-NOTICE.md
 */
export const SHOW_MP_API_BLOCKED_NOTICE = true;

export const MP_API_BLOCKED_NOTICE_TEXT =
  '【待处理】生产服务器 MP-API 暂不可用：Materials Project 已封禁服务器公网 IP（403）。线上检索仅显示本地 MySQL 数据；MP 材料请先用本地开发环境。解封：发邮件至 support@materialsproject.org 并附上服务器公网 IP，同时配置环境变量 MP_API_KEY。';
