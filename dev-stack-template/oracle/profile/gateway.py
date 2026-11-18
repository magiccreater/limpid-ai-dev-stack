"""Loopback-only Oracle Responses gateway. Configure optional escalation on the VM."""
import http.client
import json
import os
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCAL = "http://127.0.0.1:8181"
MAX_BODY = 2_000_000


def upstream(base, path, payload=None, key=None):
    url = urlsplit(base)
    cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    connection = cls(url.hostname, url.port, timeout=240)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    connection.request("POST" if payload is not None else "GET", url.path.rstrip("/") + path,
                       json.dumps(payload).encode() if payload is not None else None, headers)
    return connection.getresponse()


def reserve(db_path, limit):
    with sqlite3.connect(db_path, timeout=10) as db:
        db.execute("CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, calls INTEGER)")
        db.execute("BEGIN IMMEDIATE")
        day = date.today().isoformat()
        db.execute("INSERT OR IGNORE INTO usage VALUES (?, 0)", (day,))
        return db.execute("UPDATE usage SET calls=calls+1 WHERE day=? AND calls<?", (day, limit)).rowcount == 1


def choose(body, public):
    local = (LOCAL, "oci-local", None)
    key = os.getenv("PUBLIC_OPENAI_KEY")
    model = os.getenv("PUBLIC_OPENAI_MODEL")
    limit = int(os.getenv("PUBLIC_CALLS_PER_DAY", "0"))
    if not (public and key and model and limit > 0):
        return local
    # Inspect a small portion of the sanitized user request, excluding tools and system instructions.
    items = body.get("input", "")
    if isinstance(items, list):
        items = [x.get("content") for x in items if isinstance(x, dict) and x.get("role") == "user"]
    question = json.dumps(items, ensure_ascii=False)[-1800:]
    request = {"model": "oci-local", "temperature": 0, "max_tokens": 8, "messages": [
        {"role": "system", "content": "Classify the difficulty. Reply exactly SIMPLE or HARD. "
         "Use HARD for complex implementation or cross-module reasoning."},
        {"role": "user", "content": question}]}
    with upstream(LOCAL, "/v1/chat/completions", request) as response:
        if response.status != 200:
            return local
        decision = json.load(response)["choices"][0]["message"]["content"].strip().upper()
    if decision == "HARD" and reserve(os.environ["USAGE_DB"], limit):
        return "https://api.openai.com", model, key
    return local


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
            with upstream(LOCAL, "/health") as response:
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
            public = self.headers.get("X-Public-Project") == "yes"
            base, model, key = choose(body, public)
            body.update(model=model, store=False)
            body["max_output_tokens"] = min(int(body.get("max_output_tokens", 2048)), 2048)
            with upstream(base, "/v1/responses", body, key) as response:
                self.relay(response)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, http.client.HTTPException):
            self.send_error(502, "Check inference service, routing settings and request limits")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8182), Gateway).serve_forever()
