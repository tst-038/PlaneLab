#!/usr/bin/env python3
"""Small Newznab proxy for indexers with a broken tvsearch implementation."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen


UPSTREAM_URL = os.environ.get(
    "UPSTREAM_URL", "https://www.usenet-crawler.com/api"
).rstrip("?")
LISTEN_PORT = int(os.environ.get("PORT", "8080"))
TIMEOUT = int(os.environ.get("UPSTREAM_TIMEOUT", "30"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def rewrite_query(raw_query: str) -> tuple[str, bool]:
    """Turn title-based TV searches into broad general searches."""
    pairs = parse_qsl(raw_query, keep_blank_values=True)
    values = {}
    for key, value in pairs:
        values[key.lower()] = value

    if values.get("t", "").lower() != "tvsearch" or not values.get("q"):
        return raw_query, False

    query = values["q"].strip()

    discarded = {
        "cat",
        "season",
        "ep",
        "tvdbid",
        "tvmazeid",
        "rid",
        "imdbid",
        "traktid",
    }
    rewritten = []
    for key, value in pairs:
        lowered = key.lower()
        if lowered in discarded:
            continue
        if lowered == "t":
            rewritten.append((key, "search"))
        elif lowered == "q":
            rewritten.append((key, query))
        else:
            rewritten.append((key, value))

    return urlencode(rewritten), True


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._respond(200, b"ok\n", "text/plain; charset=utf-8")
            return

        if parsed.path not in {"/", "/api"}:
            self._respond(404, b"not found\n", "text/plain; charset=utf-8")
            return

        query, rewritten = rewrite_query(parsed.query)
        target = f"{UPSTREAM_URL}?{query}"
        request = Request(
            target,
            headers={"User-Agent": "PlaneLab-Newznab-Proxy/1.0"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP_HEADERS | {"content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-PlaneLab-Rewritten", str(rewritten).lower())
                self.end_headers()
                self.wfile.write(body)
                if rewritten:
                    print(
                        "Rewrote title-based tvsearch to category-free search",
                        flush=True,
                    )
        except HTTPError as error:
            body = error.read()
            self._respond(
                error.code,
                body,
                error.headers.get("Content-Type", "application/xml"),
            )
        except (URLError, TimeoutError) as error:
            reason = getattr(error, "reason", str(error))
            self._respond(
                502,
                f"Upstream request failed: {reason}\n".encode(),
                "text/plain; charset=utf-8",
            )

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Do not log request URLs: Newznab URLs contain API keys.
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    print(f"PlaneLab Newznab proxy listening on port {LISTEN_PORT}")
    server.serve_forever()
