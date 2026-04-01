#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import tdjson


def send(client_id: int, payload: dict) -> None:
    tdjson.td_send(client_id, json.dumps(payload).encode("utf-8"))


def receive(timeout: float):
    raw = tdjson.td_receive(timeout)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def await_result(client_id: int, request_id: str, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = receive(0.25)
        if not event or event.get("@extra") != request_id:
            continue
        return event
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    tdjson.td_execute(
        json.dumps(
            {
                "@type": "setLogVerbosityLevel",
                "new_verbosity_level": 0,
            }
        ).encode("utf-8")
    )

    client_id = tdjson.td_create_client_id()
    started_at = time.monotonic()

    send(
        client_id,
        {
            "@type": "setNetworkType",
            "type": {"@type": "networkTypeOther"},
        },
    )

    request_id = "test-proxy"
    send(
        client_id,
        {
            "@type": "testProxy",
            "proxy": {
                "@type": "proxy",
                "server": args.host,
                "port": args.port,
                "enable": True,
                "type": {
                    "@type": "proxyTypeMtproto",
                    "secret": args.secret,
                },
            },
            "dc_id": 2,
            "timeout": args.timeout,
            "@extra": request_id,
        },
    )

    event = await_result(client_id, request_id, args.timeout)
    if not event:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        print(
            json.dumps(
                {
                    "ok": False,
                    "host": args.host,
                    "port": args.port,
                    "secret": args.secret,
                    "elapsed_ms": elapsed_ms,
                    "error": "Timed out while testing proxy in TDLib",
                }
            )
        )
        return 1

    if event.get("@type") == "ok":
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        print(
            json.dumps(
                {
                    "ok": True,
                    "host": args.host,
                    "port": args.port,
                    "secret": args.secret,
                    "elapsed_ms": elapsed_ms,
                    "message": "TDLib testProxy completed successfully",
                }
            )
        )
        return 0

    if event.get("@type") == "error":
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        print(
            json.dumps(
                {
                    "ok": False,
                    "host": args.host,
                    "port": args.port,
                    "secret": args.secret,
                    "elapsed_ms": elapsed_ms,
                    "code": event.get("code"),
                    "error": event.get("message", "TDLib returned an error"),
                }
            )
        )
        return 1

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    print(
        json.dumps(
            {
                "ok": False,
                "host": args.host,
                "port": args.port,
                "secret": args.secret,
                "elapsed_ms": elapsed_ms,
                "error": "TDLib returned unexpected response",
                "response_type": event.get("@type"),
            }
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
