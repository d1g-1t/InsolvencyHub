#!/usr/bin/env bash
# Генерирует секреты в .env. Не печатает значения секретов.
set -euo pipefail

ENV_FILE="${1:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE не найден" >&2
  exit 1
fi

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

# Плейсхолдеры: change-me*, replace-with-*, CHANGE_ME, пустые значения известных ключей
is_placeholder() {
  local val="$1"
  [[ -z "$val" ]] \
    || [[ "$val" == change-me* ]] \
    || [[ "$val" == replace-with-* ]] \
    || [[ "$val" == CHANGE_ME* ]] \
    || [[ "$val" == *change-me* ]]
}

get_var() {
  local key="$1"
  local line
  line=$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 || true)
  if [[ -z "$line" ]]; then
    echo ""
    return
  fi
  echo "${line#*=}"
}

set_var() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # escape for sed: &, \, /
    local esc
    esc=$(printf '%s' "$val" | sed -e 's/[\/&]/\\&/g')
    sed -i -E "s|^${key}=.*|${key}=${esc}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >>"$ENV_FILE"
  fi
}

POSTGRES_USER=$(get_var POSTGRES_USER)
POSTGRES_USER=${POSTGRES_USER:-ih}
POSTGRES_DB=$(get_var POSTGRES_DB)
POSTGRES_DB=${POSTGRES_DB:-insolvency_hub}

POSTGRES_PASSWORD=$(get_var POSTGRES_PASSWORD)
if is_placeholder "$POSTGRES_PASSWORD"; then
  POSTGRES_PASSWORD=$(rand_hex)
  set_var POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
fi

REDIS_PASSWORD=$(get_var REDIS_PASSWORD)
if is_placeholder "$REDIS_PASSWORD"; then
  REDIS_PASSWORD=$(rand_hex)
  set_var REDIS_PASSWORD "$REDIS_PASSWORD"
fi

PASETO_KEY=$(get_var IH_PASETO_KEY_HEX)
if is_placeholder "$PASETO_KEY"; then
  PASETO_KEY=$(rand_hex)
  set_var IH_PASETO_KEY_HEX "$PASETO_KEY"
fi

# Согласованные URL (внутри сети compose)
set_var IH_DATABASE_URL \
  "postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"
set_var IH_REDIS_URL \
  "redis://:${REDIS_PASSWORD}@redis:6379/0"
set_var IH_TEST_DATABASE_URL \
  "postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/insolvency_hub_test"
set_var IH_TEST_REDIS_URL \
  "redis://:${REDIS_PASSWORD}@redis:6379/15"

echo "Секреты сгенерированы в $ENV_FILE (значения не выводятся)"
