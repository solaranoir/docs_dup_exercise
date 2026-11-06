#!/usr/bin/env bash
# Post-deploy smoke test (roadmap "Render deployment path"). Exercises the deployed stack through
# the static site's same-origin /api rewrite and cleans up after itself.
#
#   scripts/smoke_deployed.sh [WEB_URL] [API_URL] [EXPECTED_COMMIT]
#
# Production has no demo sign-in. To run the authenticated journey there, sign in in a browser,
# copy the __Host-sd_session cookie value (DevTools → Application → Cookies), and pass it:
#   SMOKE_SESSION=<value> scripts/smoke_deployed.sh
# Sharing checks need the seeded demo identities, so they run only where demo sign-in is on.
#
# EXPECTED_COMMIT (optional, prefix ok) guards against a deploy that reports "live" but serves
# stale code (#30). Exit code 0 = all checks passed.
set -euo pipefail

WEB="${1:-https://docworkspace-web.onrender.com}"
API="${2:-https://docworkspace-api.onrender.com}"
EXPECTED_COMMIT="${3:-}"
FIXTURES="$(cd "$(dirname "$0")/../backend/tests/fixtures" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILURES=0

pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
expect() { # expect <label> <expected> <actual>
  if [[ "$3" == "$2" ]]; then pass "$1 ($3)"; else fail "$1: expected $2, got $3"; fi
}
code() { curl -s -m 60 -o /dev/null -w '%{http_code}' "$@"; }
json() { python3 -c "import sys, json; print(json.load(sys.stdin)$1)"; }

echo "Warming API…"
curl -s -m 120 -o /dev/null "$API/health/live" || true

echo "Health"
live="$(curl -s -m 60 "$API/health/live")"
commit="$(echo "$live" | json '.get("commit") or ""')"
if [[ -n "$EXPECTED_COMMIT" ]]; then
  [[ "$commit" == "$EXPECTED_COMMIT"* ]] && pass "served commit $commit" || fail "served commit '$commit' != expected '$EXPECTED_COMMIT'"
else
  pass "served commit ${commit:-unknown}"
fi
ready="$(curl -s -m 60 "$API/health/ready")"
expect "database" ok "$(echo "$ready" | json '["database"]')"
expect "storage" ok "$(echo "$ready" | json '.get("storage")')"
expect "static site /" 200 "$(code "$WEB/")"
expect "deep link /doc/:id serves the app" 200 "$(code "$WEB/doc/00000000-0000-0000-0000-000000000000")"
expect "unknown /api path still reaches the API" 404 "$(code "$WEB/api/no-such-route")"
headers="$(curl -s -m 60 -D - -o /dev/null "$WEB/" | tr -d '\r' | tr 'A-Z' 'a-z')"
grep -q "^content-security-policy: default-src 'self'" <<<"$headers" && pass "CSP header" || fail "CSP header missing"
grep -q '^x-frame-options: deny' <<<"$headers" && pass "X-Frame-Options DENY" || fail "X-Frame-Options missing"

echo "Security (via $WEB/api)"
expect "anonymous /api/me" 401 "$(code "$WEB/api/me")"
expect "anonymous export all" 401 "$(code "$WEB/api/export")"
expect "anonymous Trash" 401 "$(code "$WEB/api/trash")"
expect "anonymous write, same origin" 401 "$(code -X POST -H "Origin: $WEB" \
  -H 'content-type: application/json' -d '{}' "$WEB/api/documents")"
expect "cross-site write blocked" 403 "$(code -X POST -H 'Origin: https://evil.example' \
  -H 'content-type: application/json' -d '{}' "$WEB/api/documents")"
expect "cross-site upload blocked" 403 "$(code -H 'Origin: https://evil.example' \
  -F "file=@$FIXTURES/sample.txt" "$WEB/api/imports")"

demo_status="$(code "$WEB/api/demo/users")"
if [[ "$demo_status" == 404 ]]; then
  pass "demo sign-in disabled (production)"
  expect "sign-in providers offered" yes "$(curl -s -m 60 "$WEB/api/auth/methods" \
    | json '["providers"] and "yes" or "no"')"
  if [[ -z "${SMOKE_SESSION:-}" ]]; then
    if (( FAILURES )); then echo "$FAILURES check(s) failed"; exit 1; fi
    echo "All checks passed (authenticated journey skipped: set SMOKE_SESSION to run it)"
    exit 0
  fi
  MODE=production
  echo "Session (SMOKE_SESSION)"
  A=(-H "Cookie: __Host-sd_session=$SMOKE_SESSION")
  expect "signed in" 200 "$(code "${A[@]}" "$WEB/api/me")"
else
  expect "demo users listed (non-production)" 200 "$demo_status"
  MODE=demo
  echo "Sessions (via $WEB/api)"
  for user in alice bob charlie; do
    expect "login $user" 200 "$(code -c "$TMP/$user" -X POST "$WEB/api/demo/login" \
      -H 'content-type: application/json' -d "{\"login_key\":\"$user\"}")"
  done
  A=(-b "$TMP/alice"); B=(-b "$TMP/bob"); C=(-b "$TMP/charlie")
  bob_id="$(curl -s "${B[@]}" "$WEB/api/me" | json '["id"]')"
fi

echo "Documents + import"
expect "templates listed" 200 "$(code "${A[@]}" "$WEB/api/templates")"
expect "import preview (.docx)" 200 "$(code "${A[@]}" -F "file=@$FIXTURES/sample.docx" "$WEB/api/imports")"
doc="$(curl -s "${A[@]}" -H 'content-type: application/json' \
  -d '{"title":"Smoke test - safe to delete"}' "$WEB/api/documents" | json '["id"]')"
pass "created document $doc"
expect "append .md import" 200 "$(code "${A[@]}" -F "file=@$FIXTURES/sample.md" -F mode=append \
  -F expected_revision=1 "$WEB/api/documents/$doc/imports")"
expect "stale revision rejected" 409 "$(code "${A[@]}" -X PATCH -H 'content-type: application/json' \
  -d '{"expected_revision":1,"title":"stale"}' "$WEB/api/documents/$doc")"

echo "Attachments (object storage)"
att="$(curl -s "${A[@]}" -F "file=@$FIXTURES/sample.txt" "$WEB/api/documents/$doc/attachments" | json '["id"]')"
curl -s "${A[@]}" -o "$TMP/download" "$WEB/api/documents/$doc/attachments/$att"
cmp -s "$TMP/download" "$FIXTURES/sample.txt" && pass "download is byte-identical" || fail "download differs"
curl -s "${A[@]}" -o "$TMP/export.zip" "$WEB/api/documents/$doc/export"
[[ "$(head -c 2 "$TMP/export.zip")" == PK ]] && pass "Markdown export (.zip with attachment)" || fail "export is not a zip"

if [[ "$MODE" == demo ]]; then
echo "Sharing"
expect "grant Bob viewer" 201 "$(code "${A[@]}" -H 'content-type: application/json' \
  -d '{"email":"bob@demo.test"}' "$WEB/api/documents/$doc/grants")"
expect "Bob reads" 200 "$(code "${B[@]}" "$WEB/api/documents/$doc")"
expect "Bob downloads" 200 "$(code "${B[@]}" "$WEB/api/documents/$doc/attachments/$att")"
expect "Bob cannot edit" 403 "$(code "${B[@]}" -X PATCH -H 'content-type: application/json' \
  -d '{"expected_revision":2,"title":"x"}' "$WEB/api/documents/$doc")"
expect "Charlie denied" 404 "$(code "${C[@]}" "$WEB/api/documents/$doc")"
expect "revoke Bob" 204 "$(code "${A[@]}" -X DELETE "$WEB/api/documents/$doc/grants/$bob_id")"
expect "Bob denied after revoke" 404 "$(code "${B[@]}" "$WEB/api/documents/$doc")"
fi

echo "Invalid input"
printf 'MZ' > "$TMP/x.exe"
expect "unsupported type" 415 "$(code "${A[@]}" -F "file=@$TMP/x.exe" "$WEB/api/imports")"

echo "Cleanup"
# Delete moves it to the Trash (ADR-012); delete it from there too so no smoke data is left behind.
expect "move document to Trash" 204 "$(code "${A[@]}" -X DELETE "$WEB/api/documents/$doc")"
expect "delete for good (and its object)" 204 "$(code "${A[@]}" -X DELETE "$WEB/api/trash/$doc")"

if (( FAILURES )); then echo "$FAILURES check(s) failed"; exit 1; fi
echo "All checks passed"
