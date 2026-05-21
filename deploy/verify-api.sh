#!/usr/bin/env bash
# 在服务器上运行，验证 Nginx → Python/Rust 反代是否正常
# 用法：bash deploy/verify-api.sh [域名，默认 calweb.physedu.top]

set -euo pipefail
DOMAIN="${1:-calweb.physedu.top}"
BASE="https://${DOMAIN}"

echo "=== 本机直连 Python 3569 ==="
curl -sf "http://127.0.0.1:3569/websocket_port" | head -c 120 && echo
curl -sf -X POST "http://127.0.0.1:3569/mysql_receive" \
  -H 'Content-Type: application/json' \
  -d '{"element":"2U-Nb","text":"晶体结构"}' | head -c 200 && echo
curl -sf -X POST "http://127.0.0.1:3569/api/data_fit" \
  -H 'Content-Type: application/json' \
  -d '{"x_data":[1,2,3],"y_data":[1,4,9],"fit_type":"Polynomial","degree":2}' | head -c 200 && echo

echo ""
echo "=== 经 Nginx HTTPS ==="
for path in \
  "POST ${BASE}/mysql_receive" \
  "POST ${BASE}/data_input/submit" \
  "POST ${BASE}/api/data_fit" \
  "POST ${BASE}/page2_search"
do
  method="${path%% *}"
  url="${path#* }"
  code=$(curl -sk -o /tmp/verify-body.txt -w '%{http_code}' -X "$method" "$url" \
    -H 'Content-Type: application/json' \
    -d '{"element":"2U-Nb","text":"晶体结构","username":"test","data":{},"q":"U","x_data":[1,2,3],"y_data":[1,4,9],"fit_type":"Polynomial","degree":2}')
  echo "$method $url → HTTP $code"
  if [[ "$code" == "405" ]]; then
    echo "  ↑ 405：Nginx 未反代此路径，请检查 deploy/nginx-calweb.conf.example 第④块"
  fi
  if [[ "$code" == "502" ]]; then
    echo "  ↑ 502：Python 3569 未监听，systemctl status calweb-backend"
  fi
done

echo ""
echo "完成。若本机直连 OK 但 HTTPS 405，只需更新 Nginx 并 reload。"
