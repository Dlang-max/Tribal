"""Validate an optional shared bearer token before public HTTP MCP dispatch."""

from __future__ import annotations

import hashlib
import hmac

from starlette.responses import JSONResponse


class MCPBearerTokenMiddleware:
    """Authenticate the public MCP transport independently of private curator tokens."""

    # Store only a digest of a configured printable ASCII bearer secret.
    def __init__(self, app, token: str | None) -> None:
        self.app = app
        self.token_digest = None
        if token is not None:
            if not token or any(ord(character) < 33 or ord(character) > 126 for character in token):
                raise ValueError("TRIBAL_MCP_BEARER_TOKEN must be nonempty printable ASCII without spaces")
            self.token_digest = hashlib.sha256(token.encode("ascii")).digest()

    # Reject invalid credentials before reading a body or entering an MCP session.
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and self.token_digest is not None:
            headers = [value for key, value in scope.get("headers", [])
                       if key.lower() == b"authorization"]
            value = headers[0] if len(headers) == 1 else b""
            scheme, separator, candidate = value.partition(b" ")
            valid_format = (scheme.lower() == b"bearer" and separator and candidate
                            and all(33 <= character <= 126 for character in candidate))
            valid_secret = hmac.compare_digest(hashlib.sha256(candidate).digest(), self.token_digest)
            if not valid_format or not valid_secret:
                await JSONResponse(
                    {"error": "A valid bearer token is required"}, status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="tribal"', "Cache-Control": "no-store"},
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)
