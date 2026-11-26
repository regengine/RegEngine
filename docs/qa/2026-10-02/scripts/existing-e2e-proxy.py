"""Local-only QA proxy. Each redirect hop is checked before the browser sees it."""

import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit, urlunsplit

UPSTREAM = "http://127.0.0.1:3114"
PUBLIC = "http://127.0.0.1:3115"
CSP = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
DROP_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "content-encoding",
    "content-security-policy",
    "x-dns-prefetch-control",
    "link",
    "refresh",
}


def rewrite_location(location, request_path):
    target = urlsplit(urljoin(UPSTREAM + request_path, location))
    if (
        (target.scheme, target.hostname, target.port) != ("http", "127.0.0.1", 3114)
        or target.username
        or target.password
    ):
        raise ValueError("QA off-origin redirect blocked")
    return PUBLIC + urlunsplit(("", "", target.path, target.query, target.fragment))


def _sanitize_http_header(value: str) -> str:
    """Strip CR/LF so upstream header values cannot split the response.

    Code-scanning py/http-response-splitting alerts 59 and 60.
    """
    return value.replace("\r", "").replace("\n", "")


def _strip_preconnect_links(html: str) -> str:
    """Remove <link rel=preconnect|dns-prefetch> tags without backtracking.

    A single left-to-right scan avoids the polynomial ReDoS shape of
    ``<link\b[^>]*rel=...[^>]*>`` (code-scanning alert 7).
    """
    lower = html.lower()
    out = []
    i = 0
    n = len(html)
    while i < n:
        start = lower.find("<link", i)
        if start < 0:
            out.append(html[i:])
            break
        out.append(html[i:start])
        end = lower.find(">", start)
        if end < 0:
            out.append(html[start:])
            break
        tag = lower[start : end + 1]
        if "rel=" in tag and ("preconnect" in tag or "dns-prefetch" in tag):
            i = end + 1
            continue
        out.append(html[start : end + 1])
        i = end + 1
    return "".join(out)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, headers):
        self.send_response(status)
        for key, value in headers:
            if key.lower() not in DROP_HEADERS:
                self.send_header(
                    _sanitize_http_header(key),
                    _sanitize_http_header(value),
                )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-DNS-Prefetch-Control", "off")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def proxy(self):
        if self.path == "/__qa_proxy_stop" and self.command == "POST":
            self.send(200, b"stopping", [("Content-Type", "text/plain")])
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if not self.path.startswith("/") or self.path.startswith("//"):
            return self.send(400, b"Local paths only", [])
        length = int(self.headers.get("Content-Length", "0"))
        if length > 30000000:
            return self.send(413, b"QA payload limit", [])
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "transfer-encoding", "content-length", "accept-encoding"}
        }
        headers["Accept-Encoding"] = "identity"
        connection = HTTPConnection("127.0.0.1", 3114, timeout=40)
        try:
            # HTTPConnection never follows redirects. There is exactly one
            # fixed loopback upstream request for every browser request.
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            outgoing = []
            for key, value in response.getheaders():
                if key.lower() == "location":
                    try:
                        value = rewrite_location(value, self.path)
                    except ValueError:
                        print(json.dumps({"event": "blocked_redirect", "path": self.path}), flush=True)
                        return self.send(502, b"QA off-origin redirect blocked", [("Content-Type", "text/plain")])
                outgoing.append((key, value))
            data = response.read()
            if "text/html" in response.getheader("Content-Type", ""):
                html = data.decode("utf-8")
                html = _strip_preconnect_links(html)
                data = html.encode("utf-8")
            self.send(response.status, data, outgoing)
        except (OSError, ValueError) as error:
            self.send(502, str(type(error).__name__).encode(), [("Content-Type", "text/plain")])
        finally:
            connection.close()

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = proxy


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 3115), Handler)
    print(json.dumps({"event": "started", "public": PUBLIC, "upstream": UPSTREAM}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        print(json.dumps({"event": "stopped"}), flush=True)
