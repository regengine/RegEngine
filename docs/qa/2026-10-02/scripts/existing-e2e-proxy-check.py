"""Adversarial loopback-only redirect checks with an upstream transport spy."""
import http.client
import importlib.util
import json
from pathlib import Path
import threading

SCRIPT = Path(__file__).with_name("existing-e2e-proxy.py")
spec = importlib.util.spec_from_file_location("qa_proxy", SCRIPT)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
calls = []
fixtures = {
    "/bad": (302, [("Location", "//offhost.invalid/disallowed")], b""),
    "/chain": (307, [("Location", "http://127.0.0.1:3114/bad")], b""),
    "/good": (307, [("Location", "/done")], b""),
    "/done": (200, [("Content-Type", "text/html")], b'<html><head><link rel="preconnect" href="https://offhost.invalid"><link rel="dns-prefetch" href="//offhost.invalid"></head><body>local-only</body></html>'),
}


class TransportSpy:
    def __init__(self, host, port, **kwargs):
        assert (host, port) == ("127.0.0.1", 3114)

    def request(self, method, path, **kwargs):
        self.path = path
        calls.append({"host": "127.0.0.1", "port": 3114, "method": method, "path": path})

    def getresponse(self):
        self.status, self.headers, self.body = fixtures[self.path]
        return self

    def getheaders(self):
        return self.headers

    def getheader(self, key, default=None):
        return next((value for name, value in self.headers if name.lower() == key.lower()), default)

    def read(self):
        return self.body

    def close(self):
        pass


proxy.HTTPConnection = TransportSpy
server = proxy.ThreadingHTTPServer(("127.0.0.1", 3115), proxy.Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()


def request(path):
    client = http.client.HTTPConnection("127.0.0.1", 3115)
    client.request("GET", path)
    response = client.getresponse()
    result = {"path": path, "status": response.status, "location": response.getheader("Location"), "csp": response.getheader("Content-Security-Policy"), "body": response.read().decode()}
    client.close()
    return result


try:
    results = [request("/chain"), request("/bad"), request("/good"), request("/done")]
    assert results[0]["location"] == "http://127.0.0.1:3115/bad"
    assert results[1]["status"] == 502 and results[1]["location"] is None
    assert results[2]["location"] == "http://127.0.0.1:3115/done"
    assert results[3]["status"] == 200 and "offhost.invalid" not in results[3]["body"]
    assert all(result["csp"] and "connect-src 'self'" in result["csp"] for result in results)
    for location in ["https://127.0.0.1:3114/", "http://127.0.0.1:3113/", "http://user@127.0.0.1:3114/", "//offhost.invalid/", "http://localhost:3114/"]:
        try:
            proxy.rewrite_location(location, "/")
            raise AssertionError("accepted off-origin or credentialed redirect")
        except ValueError:
            pass
    evidence = {"passed": True, "transport": "spy: no upstream network request", "browserClient": "loopback-only HTTP client", "results": results, "upstreamCalls": calls}
    target = SCRIPT.parents[1] / "artifacts/browser/existing-e2e-proxy-safety-check.json"
    target.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
finally:
    server.shutdown()
    server.server_close()
