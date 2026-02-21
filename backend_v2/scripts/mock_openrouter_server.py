#!/usr/bin/env python
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _analysis_payload(model: str) -> dict:
    return {
        "id": "chatcmpl-phase6-analysis",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '[{"command":"PLAYER_STATE_UPDATE","note":"phase6-mock"}]',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "total_tokens": 160,
            "cost": 0.0001,
        },
    }


def _narrative_payload(model: str) -> dict:
    return {
        "id": "chatcmpl-phase6-narrative",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        "Du nimmst die Umgebung aufmerksam wahr und findest einen klaren Ansatzpunkt. "
                        "Wie gehst du als naechstes vor?"
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 180,
            "completion_tokens": 90,
            "total_tokens": 270,
            "cost": 0.0002,
        },
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "Phase6MockOpenRouter/1.0"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._send_json({"status": "ok"})
            return
        self._send_json({"detail": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/v1/chat/completions":
            self._send_json({"detail": "Not found"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": {"message": "Invalid JSON"}}, status=400)
            return

        model = str(payload.get("model") or "phase6-mock-model")
        messages = payload.get("messages") if isinstance(payload, dict) else []
        system_prompt = ""
        if isinstance(messages, list):
            for item in messages:
                if isinstance(item, dict) and item.get("role") == "system":
                    system_prompt = str(item.get("content") or "")
                    break

        if "strict game command extractor" in system_prompt.lower():
            self._send_json(_analysis_payload(model))
            return

        self._send_json(_narrative_payload(model))

    def log_message(self, format: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local mock server for OpenRouter chat completions.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8031, help="Bind port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"Phase6 mock OpenRouter listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
