"""Run inside the LiteLLM container after both services start."""
from http.client import HTTPConnection
import json
import time

for _ in range(90):
    connection = HTTPConnection("laya", 8000, timeout=2)
    try:
        connection.request("GET", "/decision")
        response = connection.getresponse()
        response.close()
        break
    except OSError:
        time.sleep(2)
    finally:
        connection.close()
else:
    raise SystemExit("Laya HTTP server did not start.")

for brief in ("Fix the synthetic bug.", "Review this synthetic patch.", "Plan a synthetic database migration."):
    connection = HTTPConnection("127.0.0.1", 8080, timeout=15)
    try:
        body = json.dumps({"model": "public-free-coder", "stream": True,
                           "messages": [{"role": "user", "content": brief}]})
        start = time.monotonic()
        connection.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        contents = response.read()
        seconds = round(time.monotonic() - start, 3)
        score = response.getheader("X-Limpid-Decision-Score")
        assert response.status == 200 and b"READY" in contents and b"[DONE]" in contents, (
            response.status, contents[:400],
        )
        assert score is not None, "Laya returned no usable score."
        print(json.dumps({"sample": brief, "route": response.getheader("X-Limpid-Route"),
                          "decision": response.getheader("X-Limpid-Decision"),
                          "score": score, "seconds": seconds}), flush=True)
    finally:
        connection.close()
