#!/usr/bin/env python3
"""
server.py — Simple demo app for Lab 9.
Queries OPA server before serving requests.

Endpoints:
  GET  /         → hello message
  GET  /health   → health check
  GET  /check    → query OPA policy and return decision
"""
import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

OPA_URL  = os.environ.get("OPA_URL", "http://opa:8181")
PORT     = int(os.environ.get("PORT", "3000"))
APP_NAME = os.environ.get("APP_NAME", "lab9-app")


def query_opa(input_data: dict) -> dict:
    url  = f"{OPA_URL}/v1/data/lab/allow"
    body = json.dumps({"input": input_data}).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"error": str(e), "result": False}


class AppHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send_json(200, {
                "message": f"Hello from {APP_NAME} — managed by Terraform",
                "opa_url": OPA_URL,
            })
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "app": APP_NAME})
        elif self.path.startswith("/check"):
            from urllib.parse import urlparse, parse_qs
            qs     = parse_qs(urlparse(self.path).query)
            user   = qs.get("user",   ["anonymous"])[0]
            action = qs.get("action", ["read"])[0]
            decision = query_opa({"user": user, "action": action})
            allowed  = decision.get("result", False)
            self._send_json(200 if allowed else 403, {
                "user": user, "action": action,
                "allowed": allowed, "decision": decision,
            })
        else:
            self._send_json(404, {"error": f"path not found: {self.path}"})


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), AppHandler)
    print(f"{APP_NAME} listening on :{PORT}  opa={OPA_URL}")
    server.serve_forever()