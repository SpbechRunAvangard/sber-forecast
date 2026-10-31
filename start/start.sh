#!/usr/bin/env bash
# Меню управления сервисом прогноза (Linux / macOS). Запуск: ./start.sh
# Для автоматизации: ./start.sh start | open | forecast [sales.csv stock.csv [cutoff|all]] | test | logs | rebuild | stop
set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"
IMAGE=sber-forecast
CONTAINER=sber-forecast
PORT="${SBER_PORT:-8000}"
BASE="http://localhost:$PORT"
DEFAULT_CUTOFF=2026-07-26

c_ok=$'\e[32m'; c_err=$'\e[31m'; c_warn=$'\e[33m'; c_head=$'\e[36m'; c_off=$'\e[0m'
ok()   { echo "  ${c_ok}[OK]${c_off} $*"; }
warn() { echo "  ${c_warn}[!]${c_off} $*"; }
fail() { echo "  ${c_err}[X]${c_off} $*"; }

docker_ready() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker не установлен: https://docs.docker.com/get-docker/"; return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    fail "Docker не запущен (или нет прав: попробуйте sudo или добавьте пользователя в группу docker)"; return 1
  fi
}

healthy() { curl -sf -m 3 "$BASE/health" >/dev/null 2>&1; }

build_image() {
  echo "${c_head}Собираю образ $IMAGE (первый раз 3-10 минут)...${c_off}"
  docker build -t "$IMAGE" . && ok "Образ собран"
}

start_service() {
  docker_ready || return 1
  if healthy; then ok "Сервис уже работает: $BASE"; return 0; fi
  docker image inspect "$IMAGE" >/dev/null 2>&1 || build_image || return 1
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  echo "${c_head}Запускаю контейнер на порту $PORT...${c_off}"
  docker run -d --name "$CONTAINER" -p "$PORT:8000" --restart unless-stopped "$IMAGE" >/dev/null \
    || { fail "Не удалось запустить. Если порт занят: SBER_PORT=8001 ./start.sh"; return 1; }
  for _ in $(seq 60); do
    sleep 1
    if healthy; then ok "Сервис работает: $BASE (веб-интерфейс: $BASE/ , API: $BASE/docs)"; return 0; fi
  done
  fail "Сервис не ответил за минуту:"; docker logs --tail 30 "$CONTAINER"; return 1
}

ensure_running() { healthy || { warn "Сервис не запущен - запускаю."; start_service; }; }

stop_service() { docker_ready && docker rm -f "$CONTAINER" >/dev/null 2>&1; ok "Сервис остановлен"; }

open_browser() {
  ensure_running || return 1
  if command -v xdg-open >/dev/null; then xdg-open "$BASE/" >/dev/null 2>&1 &
  elif command -v open >/dev/null; then open "$BASE/"
  else echo "Откройте в браузере: $BASE/"; fi
}

find_file() {
  for d in "$ROOT" "$ROOT/data/raw" "$ROOT/.." "$ROOT/../.."; do
    [ -f "$d/$1" ] && { (cd "$d" && echo "$(pwd)/$1"); return; }
  done
}

ask_file() {  # $1 - подпись, $2 - имя файла по умолчанию; результат в переменной REPLY_FILE
  local found; found="$(find_file "$2")"
  if [ -n "$found" ]; then
    read -r -p "  $1 [$found]: " REPLY_FILE; REPLY_FILE="${REPLY_FILE:-$found}"
  else
    read -r -p "  $1 (путь к CSV): " REPLY_FILE
  fi
}

run_forecast() {  # [sales stock [cutoff|all]]
  ensure_running || return 1
  local sales="${1:-}" stock="${2:-}" cutoff="${3:-}"
  if [ -z "$sales" ]; then
    echo; echo "${c_head}Прогноз из файлов CSV${c_off}"
    ask_file "Продажи (sales)" sales_dataset_hakaton_train.csv; sales="$REPLY_FILE"
    ask_file "Остатки (stock)" stock_dataset_hakaton_train.csv; stock="$REPLY_FILE"
    echo "  Какие даты использовать?"
    echo "    1 - по 26.07.2026, как в основном submission (по умолчанию)"
    echo "    2 - все даты из файлов"
    echo "    3 - указать свою последнюю дату"
    read -r -p "  Ваш выбор: " ch
    case "$ch" in 2) cutoff=all ;; 3) read -r -p "  Дата ГГГГ-ММ-ДД: " cutoff ;; *) cutoff=$DEFAULT_CUTOFF ;; esac
  fi
  cutoff="${cutoff:-$DEFAULT_CUTOFF}"
  [ -f "$sales" ] || { fail "Нет файла: $sales"; return 1; }
  [ -f "$stock" ] || { fail "Нет файла: $stock"; return 1; }
  local url="$BASE/predict"; [ "$cutoff" != all ] && url="$url?cutoff=$cutoff"
  mkdir -p results
  local out="results/forecast_$(date +%Y-%m-%d_%H-%M).csv"
  echo "${c_head}Считаю прогноз (на полных данных 30-60 секунд)...${c_off}"
  local code; code=$(curl -s -o "$out.tmp" -w "%{http_code}" -X POST "$url" -F "sales=@$sales" -F "stock=@$stock")
  if [ "$code" != 200 ]; then fail "Ошибка $code: $(cat "$out.tmp")"; rm -f "$out.tmp"; return 1; fi
  mv "$out.tmp" "$out"
  ok "Готово: $ROOT/$out ($(($(wc -l < "$out") - 1)) строк)"
  awk -F, 'NR==2{w=$1} NR>1{t+=$4; if($1==w){n++; if($4>0)z++}} END{printf "  Ненулевой прогноз: %d из %d пар; всего за 9 недель: %d шт.\n", z, n, t}' "$out"
  if [ "$cutoff" = "$DEFAULT_CUTOFF" ] && cmp -s "$out" data/submission_weekly_v6.csv; then
    ok "Совпадает с основным submission (data/submission_weekly_v6.csv)"
  fi
}

run_lookup() {
  ensure_running || return 1
  read -r -p "  Артикул (Enter - любой): " art
  read -r -p "  Склад (Enter - любой): " wh
  [ -z "$art$wh" ] && { warn "Нужно указать хотя бы одно"; return 1; }
  local res; res=$(curl -s -G "$BASE/predict" ${art:+--data-urlencode "article=$art"} ${wh:+--data-urlencode "warehouse=$wh"})
  case "$res" in week,*) ;; *) fail "$res"; return 1 ;; esac
  [ "$(echo "$res" | wc -l)" -le 1 ] && { warn "Ничего не найдено: проверьте артикул и склад"; return 1; }
  if command -v column >/dev/null; then echo "$res" | head -61 | column -t -s,; else echo "$res" | head -61 | tr , '\t'; fi
  [ "$(echo "$res" | wc -l)" -gt 61 ] && echo "  ...показаны первые 60 строк"
  return 0
}

run_test() {
  ensure_running || return 1
  if command -v jq >/dev/null; then bash tests/test_api.sh "$BASE"
  else
    warn "jq не установлен - короткая проверка"
    healthy && ok "GET /health" || fail "GET /health"
    local n; n=$(curl -s -X POST "$BASE/predict" -F sales=@data/sample_sales.csv -F stock=@data/sample_stock.csv | wc -l)
    [ "$n" = 79102 ] && ok "POST /predict: 79101 строк" || fail "POST /predict: $n строк"
  fi
}

menu() {
  while true; do
    healthy && state="работает на $BASE" || state="не запущен"
    echo
    echo "${c_head}==============  Прогноз продаж (команда Авангард)  ==============${c_off}"
    echo "  Сервис: $state"
    echo "  1 - Запустить сервис (при первом запуске соберёт образ)"
    echo "  2 - Открыть веб-интерфейс в браузере"
    echo "  3 - Сделать прогноз из CSV-файлов (результат в папке results)"
    echo "  4 - Посмотреть прогноз по артикулу или складу"
    echo "  5 - Самопроверка"
    echo "  6 - Журнал контейнера"
    echo "  7 - Пересобрать образ (после изменения кода)"
    echo "  8 - Остановить сервис"
    echo "  0 - Выход"
    read -r -p "Выберите пункт: " ch || exit 0
    case "$ch" in
      1) start_service ;; 2) open_browser ;; 3) run_forecast ;; 4) run_lookup ;; 5) run_test ;;
      6) docker logs --tail 40 "$CONTAINER" ;; 7) build_image && stop_service && start_service ;;
      8) stop_service ;; 0) exit 0 ;; *) warn "Нет такого пункта" ;;
    esac
  done
}

case "${1:-}" in
  "") menu ;;
  start) start_service ;;
  open) open_browser ;;
  forecast) shift; run_forecast "$@" ;;
  test) run_test ;;
  logs) docker logs --tail 40 "$CONTAINER" ;;
  rebuild) build_image && stop_service && start_service ;;
  stop) stop_service ;;
  *) warn "Неизвестное действие '$1'. Доступно: start, open, forecast, test, logs, rebuild, stop"; exit 1 ;;
esac
