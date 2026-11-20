"""Serve the existing decision model on the benchmark's private Docker network."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

import service

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/decision":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= service.MAX_BYTES:
            self.send_error(413)
            return
        result = service.handle(json.loads(self.rfile.read(size)), None)
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass

start = time.monotonic()
service.model()
print(f"Laya cold model load: {time.monotonic() - start:.2f}s", flush=True)
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
