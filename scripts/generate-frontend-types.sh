#!/usr/bin/env bash
# Generates dashboard/frontend/src/api/types.generated.ts from the real, running A7 API
# (development mode only, since /api/openapi.json is None in production — app.py). Starts a
# throwaway dev server on an isolated port, fetches its schema, generates, stops the server.
# Entirely offline (127.0.0.1 only). See docs/specs/a8-frontend-dashboard.md.
#
# Usage: scripts/generate-frontend-types.sh [output-path]
#   make gen-types    -> writes the committed dashboard/frontend/src/api/types.generated.ts
#   make check-types  -> writes to a temp path and diffs, to catch drift (CI-style check)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/dashboard/frontend"
# openapi-typescript needs a TypeScript major it actually supports (docs/technical-debt.md);
# kept out of dashboard/frontend's own dependency tree so the two never conflict.
CODEGEN_BIN="$ROOT_DIR/scripts/codegen/node_modules/.bin/openapi-typescript"
OUT_PATH="${1:-$WEB_DIR/src/api/types.generated.ts}"
HOST="127.0.0.1"
PORT="${HOME_DNS_GEN_TYPES_PORT:-8099}"
SCHEMA_PATH="$ROOT_DIR/.local/gen-types-openapi.json"
SERVER_LOG="$ROOT_DIR/.local/gen-types-server.log"

if [ ! -x "$CODEGEN_BIN" ]; then
  echo "generate-frontend-types.sh: $CODEGEN_BIN missing — run 'npm install' in scripts/codegen/ first" >&2
  exit 1
fi

export PYTHONPATH="$ROOT_DIR/src"
export HOME_DNS_API__PORT="$PORT"

CLI=(uv run --locked python -m home_dns.cli)

# `serve` refuses to start without at least one admin user (A7). This user lives only in the
# gitignored .local/ dev database and is never used for anything but local type generation.
printf 'gen-types-local-dev-only\n' | (cd "$ROOT_DIR" && "${CLI[@]}" \
  auth set-password --env development --username gen-types --role admin --password-stdin) >/dev/null

mkdir -p "$ROOT_DIR/.local"
# Redirected, not inherited: an unredirected background process here would keep this script's
# own stdout pipe open (and any caller reading it blocked) even after this script exits.
(cd "$ROOT_DIR" && "${CLI[@]}" serve --env development) >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  # Belt-and-suspenders: reach the actual listening process even if $SERVER_PID was a
  # short-lived wrapper (e.g. `uv run`) that didn't forward the signal to its child.
  # (plain `xargs kill`, no `-r`: that GNU flag doesn't exist on macOS/BSD xargs)
  listeners="$(lsof -ti "tcp:$PORT" 2>/dev/null || true)"
  if [ -n "$listeners" ]; then
    echo "$listeners" | xargs kill >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

ready=""
for _ in $(seq 1 50); do
  if curl -fsS "http://$HOST:$PORT/api/v1/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.2
done
if [ -z "$ready" ]; then
  echo "generate-frontend-types.sh: the dev server never became healthy on port $PORT" >&2
  exit 1
fi

mkdir -p "$(dirname "$SCHEMA_PATH")"
curl -fsS "http://$HOST:$PORT/api/openapi.json" -o "$SCHEMA_PATH"

cleanup
trap - EXIT

mkdir -p "$(dirname "$OUT_PATH")"
"$CODEGEN_BIN" "$SCHEMA_PATH" -o "$OUT_PATH"
rm -f "$SCHEMA_PATH"

echo "generate-frontend-types.sh: wrote $OUT_PATH"
