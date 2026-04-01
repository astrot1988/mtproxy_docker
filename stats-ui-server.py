#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATS_PORT = int(os.environ.get("MTPROXY_STATS_PORT", "8888"))
UI_PORT = int(os.environ.get("MTPROXY_UI_PORT", "8080"))
STATS_PATH = os.environ.get("MTPROXY_STATS_PATH", "/stats")
PUBLIC_HOST = os.environ.get("MTPROXY_PUBLIC_HOST", "").strip()
PUBLIC_PORT = int(os.environ.get("MTPROXY_PORT", "443"))
SECRET_ENV = os.environ.get("SECRET", "")
CLIENT_SECRET_FILE = Path("/data/client-secret")
UI_ROOT = Path("/opt/mtproxy/stats-ui")
STATS_URL = f"http://127.0.0.1:{STATS_PORT}{STATS_PATH}"
CHECK_SCRIPT = "/usr/local/bin/tdlib-proxy-check.py"
CHECK_TIMEOUT = float(os.environ.get("MTPROXY_CHECK_TIMEOUT", "8"))
COMMON_KEYS = [
    "version",
    "uptime",
    "workers",
    "total_connections",
    "active_connections",
    "inbound_connections",
    "outbound_connections",
    "total_encrypted_connections",
    "total_special_connections",
    "max_special_connections",
    "tot_forwarded_queries",
    "tot_forwarded_responses",
    "dropped_queries",
    "dropped_responses",
    "load_recent_total",
    "average_idle_percent",
    "recent_idle_percent",
    "http_qps",
]
SECTION_START_RE = re.compile(r"^>{6}(.+?)>{6}$")
SECTION_END_RE = re.compile(r"^<{6}(.+?)<{6}$")


def coerce_value(raw: str):
    raw = raw.strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def parse_stats(text: str):
    metrics = []
    sections = []
    summary = {}
    current_section = None
    current_section_metrics = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if "\t" in line:
            parts = [part.strip() for part in line.split("\t") if part.strip()]
        else:
            parts = re.split(r"\s{2,}", line)
            parts = [part.strip() for part in parts if part.strip()]
            if len(parts) == 1:
                parts = line.split(None, 1)

        if len(parts) < 2:
            continue

        name = parts[0]
        value = " ".join(parts[1:])
        start_match = SECTION_START_RE.fullmatch(name)
        end_match = SECTION_END_RE.fullmatch(name)

        if start_match and value == "start":
            current_section = start_match.group(1)
            current_section_metrics = []
            continue

        if end_match and value == "end":
            section_name = end_match.group(1)
            if current_section == section_name:
                sections.append(
                    {
                        "name": section_name,
                        "title": format_section_title(section_name),
                        "metrics": current_section_metrics,
                    }
                )
            current_section = None
            current_section_metrics = []
            continue

        parsed_value = coerce_value(value)
        metric = {"name": name, "value": parsed_value, "display": value, "raw": line}
        metrics.append(metric)
        if current_section is not None:
            current_section_metrics.append(metric)
        if name in COMMON_KEYS:
            summary[name] = parsed_value

    unsectioned_metrics = [
        metric
        for metric in metrics
        if not any(metric in section["metrics"] for section in sections)
    ]
    if unsectioned_metrics:
        sections.insert(
            0,
            {
                "name": "overview",
                "title": "Overview",
                "metrics": unsectioned_metrics,
            },
        )

    return sections, summary, metrics


def format_section_title(name: str):
    return name.replace("_", " ").title()


def load_secret_values():
    raw = SECRET_ENV.strip()
    if not raw and CLIENT_SECRET_FILE.exists():
        raw = CLIENT_SECRET_FILE.read_text(encoding="utf-8", errors="ignore").strip()

    raw = "".join(raw.split())
    if not raw:
        return []

    secrets = []
    for secret in raw.split(","):
        if secret:
            secrets.append(secret)
    return secrets


def build_connection_links():
    if not PUBLIC_HOST:
        return []

    links = []
    for index, secret in enumerate(load_secret_values(), start=1):
        tg_url = f"tg://proxy?server={PUBLIC_HOST}&port={PUBLIC_PORT}&secret={secret}"
        padded_secret = f"dd{secret}"
        padded_tg_url = (
            f"tg://proxy?server={PUBLIC_HOST}&port={PUBLIC_PORT}&secret={padded_secret}"
        )
        links.append(
            {
                "index": index,
                "label": f"Secret {index}",
                "host": PUBLIC_HOST,
                "port": PUBLIC_PORT,
                "secret": secret,
                "padded_secret": padded_secret,
                "tg_url": tg_url,
                "padded_tg_url": padded_tg_url,
            }
        )
    return links


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file("index.html", "text/html; charset=utf-8")
            return

        if self.path == "/app.js":
            self._serve_file("app.js", "application/javascript; charset=utf-8")
            return

        if self.path == "/styles.css":
            self._serve_file("styles.css", "text/css; charset=utf-8")
            return

        if self.path == "/api/stats":
            self._serve_stats()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/check-proxy":
            self._check_proxy()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        return

    def _serve_file(self, name: str, content_type: str):
        path = UI_ROOT / name
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_stats(self):
        started_at = time.time()
        try:
            with urllib.request.urlopen(STATS_URL, timeout=3) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            body = {
                "ok": False,
                "error": str(exc),
                "upstream": STATS_URL,
                "fetched_at": int(time.time()),
            }
            self._send_json(body, HTTPStatus.BAD_GATEWAY)
            return

        sections, summary, metrics = parse_stats(raw)
        body = {
            "ok": True,
            "upstream": STATS_URL,
            "fetched_at": int(time.time()),
            "response_ms": int((time.time() - started_at) * 1000),
            "public_host": PUBLIC_HOST,
            "public_port": PUBLIC_PORT,
            "links": build_connection_links(),
            "summary": summary,
            "sections": sections,
            "metrics": metrics,
        }
        self._send_json(body, HTTPStatus.OK)

    def _check_proxy(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"ok": False, "error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            return

        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON payload"}, HTTPStatus.BAD_REQUEST)
            return

        host = str(payload.get("host", "")).strip()
        secret = str(payload.get("secret", "")).strip()
        try:
            port = int(payload.get("port", 0))
        except (TypeError, ValueError):
            port = 0

        if not host or not secret or port <= 0:
            self._send_json(
                {"ok": False, "error": "host, port and secret are required"},
                HTTPStatus.BAD_REQUEST,
            )
            return

        started_at = time.time()
        try:
            result = subprocess.run(
                [
                    "python3",
                    CHECK_SCRIPT,
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "--secret",
                    secret,
                    "--timeout",
                    str(CHECK_TIMEOUT),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT + 2,
            )
        except subprocess.TimeoutExpired:
            self._send_json(
                {
                    "ok": False,
                    "host": host,
                    "port": port,
                    "error": "Proxy check process timed out",
                },
                HTTPStatus.BAD_GATEWAY,
            )
            return

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stdout:
            try:
                body = json.loads(stdout)
            except json.JSONDecodeError:
                body = {
                    "ok": False,
                    "host": host,
                    "port": port,
                    "error": "Invalid checker output",
                    "stdout": stdout,
                }
        else:
            body = {
                "ok": False,
                "host": host,
                "port": port,
                "error": stderr or "Proxy checker returned no output",
            }

        body["checked_at"] = int(time.time())
        body["response_ms"] = int((time.time() - started_at) * 1000)
        status = HTTPStatus.OK if body.get("ok") else HTTPStatus.BAD_GATEWAY
        self._send_json(body, status)

    def _send_json(self, body, status: HTTPStatus):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", UI_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
