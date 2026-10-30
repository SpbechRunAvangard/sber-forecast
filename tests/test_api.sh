#!/bin/bash
# Самопроверка API. Запустите после поднятия контейнера.
# Usage: bash tests/test_api.sh [BASE_URL]

set -e
BASE_URL="${1:-http://localhost:8000}"

echo "=== 1. Health check ==="
curl -sf "$BASE_URL/health" | jq .
echo "OK"
echo

echo "=== 2. POST /predict ==="
curl -sf -X POST "$BASE_URL/predict" \
  -F "sales=@data/sample_sales.csv" \
  -F "stock=@data/sample_stock.csv" \
  -o /tmp/forecast.csv
echo "Получен файл: $(wc -l < /tmp/forecast.csv) строк"
head -3 /tmp/forecast.csv
echo "OK"
echo

ARTICLE=$(sed -n '2p' /tmp/forecast.csv | cut -d, -f3)
WAREHOUSE=$(sed -n '2p' /tmp/forecast.csv | cut -d, -f2)

echo "=== 3. GET /predict?article= ==="
curl -sf "$BASE_URL/predict?article=$ARTICLE" | head -3
echo "OK"
echo

echo "=== 4. GET /predict?warehouse= ==="
curl -sf "$BASE_URL/predict?warehouse=$WAREHOUSE" | head -3
echo "OK"
echo

echo "=== 5. GET /predict?article=&warehouse= ==="
curl -sf "$BASE_URL/predict?article=$ARTICLE&warehouse=$WAREHOUSE" | head -3
echo "OK"
echo

echo "=== 6. GET /predict/all?format=csv ==="
curl -sf "$BASE_URL/predict/all?format=csv" -o /tmp/full_forecast.csv
echo "Получен файл: $(wc -l < /tmp/full_forecast.csv) строк"
echo "OK"
echo

echo "=== 7. GET /predict/all?format=json ==="
curl -sf "$BASE_URL/predict/all?format=json" | jq '.[0:3]'
echo "OK"
echo

echo "=== 8. Error: GET /predict без параметров ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/predict")
echo "HTTP $CODE (ожидается 400)"
[ "$CODE" = "400" ]
echo

echo "=== 9. Error: пустой файл (ожидается 400) ==="
: > /tmp/empty.csv
CODE=$(curl -s -o /tmp/err.json -w "%{http_code}" -X POST "$BASE_URL/predict" -F "sales=@/tmp/empty.csv" -F "stock=@data/sample_stock.csv")
echo "HTTP $CODE: $(cat /tmp/err.json)"
[ "$CODE" = "400" ]
echo

echo "=== 10. Error: история меньше 180 дней (ожидается 422) ==="
head -1 data/sample_sales.csv > /tmp/short_sales.csv
grep "^2026-07-2" data/sample_sales.csv >> /tmp/short_sales.csv
CODE=$(curl -s -o /tmp/err.json -w "%{http_code}" -X POST "$BASE_URL/predict" -F "sales=@/tmp/short_sales.csv" -F "stock=@data/sample_stock.csv")
echo "HTTP $CODE: $(cat /tmp/err.json)"
[ "$CODE" = "422" ]
echo

echo "=== 11. Error: отрицательный quantity (ожидается 422) ==="
awk -F, 'BEGIN{OFS=","} NR==2{$10="-1"} {print}' data/sample_sales.csv > /tmp/neg_sales.csv
CODE=$(curl -s -o /tmp/err.json -w "%{http_code}" -X POST "$BASE_URL/predict" -F "sales=@/tmp/neg_sales.csv" -F "stock=@data/sample_stock.csv")
echo "HTTP $CODE: $(cat /tmp/err.json)"
[ "$CODE" = "422" ]
echo

echo "=== 12. Отрицательный stock допустим (ожидается 200) ==="
awk -F, 'BEGIN{OFS=","} NR==2{$4="-5"} {print}' data/sample_stock.csv > /tmp/neg_stock.csv
CODE=$(curl -s -o /tmp/forecast_neg.csv -w "%{http_code}" -X POST "$BASE_URL/predict" -F "sales=@data/sample_sales.csv" -F "stock=@/tmp/neg_stock.csv")
echo "HTTP $CODE"
[ "$CODE" = "200" ]
echo

echo "=== Все тесты пройдены! ==="
