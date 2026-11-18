"""Loopback-only inference on the project's own VM."""
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 2_000_000


def upstream(path, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", 8181, timeout=240)
    connection.request("POST" if payload is not None else "GET", path,
                       json.dumps(payload).encode() if payload is not None else None,
                       {"Content-Type": "application/json"})
    return connection.getresponse()


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass  # Prompt bodies, query strings and provider errors never enter the service log.

    def relay(self, response):
        self.send_response(response.status)
        self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
        self.end_headers()
        if response.status >= 400:
            self.wfile.write(json.dumps({"error": "Inference returned HTTP %d. Check model context size and service status." % response.status}).encode())
            return
        while chunk := response.read1(16384):
            self.wfile.write(chunk)
            self.wfile.flush()

    def do_GET(self):
        if self.path != "/health":
            return self.send_error(404)
        try:
            with upstream("/health") as response:
                self.relay(response)
        except OSError:
            self.send_error(503, "Inference offline or loading")

    def do_POST(self):
        if self.path != "/v1/responses":
            return self.send_error(404)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= MAX_BODY:
                return self.send_error(413)
            body = json.loads(self.rfile.read(size))
            body.update(model="oci-local", store=False)
            body["max_output_tokens"] = min(int(body.get("max_output_tokens", 2048)), 2048)
            with upstream("/v1/responses", body) as response:
                self.relay(response)
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
            self.send_error(502, "Check inference service, routing settings and request limits")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8182), Gateway).serve_forever()
