#!/usr/bin/env bash
# Post-deploy smoke test (roadmap "Render deployment path"). Exercises the deployed stack through
# the static site's same-origin /api rewrite and cleans up after itself.
#
#   scripts/smoke_deployed.sh [WEB_URL] [API_URL] [EXPECTED_COMMIT]
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

echo "Warming API (free tier may take ~50 s)…"
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

echo "Sessions (via $WEB/api)"
for user in alice bob charlie; do
  expect "login $user" 200 "$(code -c "$TMP/$user" -X POST "$WEB/api/demo/login" \
    -H 'content-type: application/json' -d "{\"login_key\":\"$user\"}")"
done
A=(-b "$TMP/alice"); B=(-b "$TMP/bob"); C=(-b "$TMP/charlie")
bob_id="$(curl -s "${B[@]}" "$WEB/api/me" | json '["id"]')"

echo "Documents + import"
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

echo "Sharing"
expect "grant Bob viewer" 201 "$(code "${A[@]}" -H 'content-type: application/json' \
  -d "{\"user_id\":$bob_id}" "$WEB/api/documents/$doc/grants")"
expect "Bob reads" 200 "$(code "${B[@]}" "$WEB/api/documents/$doc")"
expect "Bob downloads" 200 "$(code "${B[@]}" "$WEB/api/documents/$doc/attachments/$att")"
expect "Bob cannot edit" 403 "$(code "${B[@]}" -X PATCH -H 'content-type: application/json' \
  -d '{"expected_revision":2,"title":"x"}' "$WEB/api/documents/$doc")"
expect "Charlie denied" 404 "$(code "${C[@]}" "$WEB/api/documents/$doc")"
expect "revoke Bob" 204 "$(code "${A[@]}" -X DELETE "$WEB/api/documents/$doc/grants/$bob_id")"
expect "Bob denied after revoke" 404 "$(code "${B[@]}" "$WEB/api/documents/$doc")"

echo "Invalid input"
printf 'MZ' > "$TMP/x.exe"
expect "unsupported type" 415 "$(code "${A[@]}" -F "file=@$TMP/x.exe" "$WEB/api/imports")"

echo "Cleanup"
expect "delete document (and its object)" 204 "$(code "${A[@]}" -X DELETE "$WEB/api/documents/$doc")"

if (( FAILURES )); then echo "$FAILURES check(s) failed"; exit 1; fi
echo "All checks passed"
