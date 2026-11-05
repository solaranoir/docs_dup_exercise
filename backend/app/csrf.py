"""Cross-site request forgery guard (ADR-009).

SameSite=Lax already keeps the session cookie off cross-site POSTs. This is the second layer:
it also covers multipart uploads (which skip CORS preflight) and hosts that would count as
same-site under a shared custom domain. Browsers send `Origin` on every unsafe request, plus
`Sec-Fetch-Site` in modern browsers. A request with neither comes from a non-browser client,
which cannot carry a victim's cookies, so it is allowed through to normal authentication.
"""

from starlette.requests import Request

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SAME_ORIGIN_FETCH = frozenset({"same-origin", "none"})


def is_cross_site(request: Request, trusted_origins: frozenset[str]) -> bool:
    if request.method not in UNSAFE_METHODS:
        return False
    origin = request.headers.get("origin")
    if origin is not None:
        return origin.rstrip("/") not in trusted_origins  # includes the opaque "null" origin
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site not in _SAME_ORIGIN_FETCH
    return False
