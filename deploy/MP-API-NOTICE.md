# MP-API 生产环境暂不可用（临时备忘）

**状态**：待处理（2026-05-21）  
**影响域名**：`https://calweb.physedu.top`  
**不影响**：本地 `npm run dev` + 本机 `pyserver.py`

## 现象

```bash
curl -s "http://127.0.0.1:3569/api/data?element=Fe&num_element=1"
# → {"message": ["MP-API请求失败: ... error status code 403 ... IP address or ASN has been blocked ..."]}
```

`server/error.log` 中同样出现 `403` / `"version": "blocked"`。

## 原因

Materials Project 封禁了**阿里云服务器公网 IP**（判定为 inefficient or abusive traffic）。  
可能与早期错误 API 调用（无效参数、重复请求、一次拉取过多字段）叠加有关。

## 解封步骤

1. 在服务器查公网 IP：
   ```bash
   curl -s ifconfig.me && echo
   ```
2. 发邮件至 **support@materialsproject.org**（英文即可）：
   - 说明学术/教学用途、站点域名
   - 附上公网 IP
   - 说明已修复 `mp-api` 调用方式、会控制请求频率
3. 在 [materialsproject.org/api](https://materialsproject.org/api) 申请**自己的 32 位 API Key**
4. 写入 systemd（参考 `deploy/calweb-backend.service.example`）：
   ```ini
   Environment=MP_API_KEY=你的密钥
   ```
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart calweb-backend
   ```
5. 验证：
   ```bash
   bash deploy/verify-api.sh
   curl -s "http://127.0.0.1:3569/api/data?element=Fe&num_element=1" | head -c 400
   # 应出现 Material ID: mp-...
   ```

## 解封后需关闭的临时提示

| 位置 | 操作 |
|------|------|
| `web/src/config/opsNotice.ts` | `SHOW_MP_API_BLOCKED_NOTICE = false` |
| `README.md` 顶部 | 删除或更新「已知问题」块 |
| 本文件 | 删除或改为「已解决」 |

## 后续优化（降低再次被封风险）

- [ ] 合并 `page2_search` 与 `/api/data` 的重复 MP 请求
- [ ] 缩小 `get_data` 请求字段与条数上限
- [ ] 对 MP 结果做短期缓存
