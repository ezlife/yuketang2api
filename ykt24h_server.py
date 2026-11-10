#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雨课堂 24H 学伴 → OpenAI 兼容 API 服务(零依赖,标准库实现)
把 ykt24h.py 包装成 /v1/chat/completions(支持 stream)。

启动:
  export YKT_SESSION="sessionid=xxx; csrftoken=yyy"
  export YKT_AGENT_ID=123456
  python3 ykt24h_server.py [端口,默认 8317]

接入任何 OpenAI 客户端(Cherry Studio / one-api / openai python):
  BASE_URL=http://127.0.0.1:8317/v1
  API_KEY=任意值
  model=yuketang-24h
"""
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ykt24h import Yuketang24H

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8317"))
MODEL_NAME = "yuketang-24h"
CLIENTS = {}          # conv_key -> client(同 key 复用会话,保上下文)


def get_client(conv_key):
    if conv_key not in CLIENTS:
        cli = Yuketang24H()
        cli.get_or_create_conversation()
        CLIENTS[conv_key] = cli
    return CLIENTS[conv_key]


def sse_chunk(cid, delta=None, finish=None, role=None):
    d = {}
    if role:
        d["role"] = role
    if delta:
        d["content"] = delta
    obj = {"id": f"chatcmpl-{cid}", "object": "chat.completion.chunk",
           "created": int(time.time()), "model": MODEL_NAME,
           "choices": [{"index": 0, "delta": d, "finish_reason": finish}]}
    return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            return self._json(200, {"object": "list", "data": [
                {"id": MODEL_NAME, "object": "model", "owned_by": "yuketang"}]})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._json(404, {"error": "not found"})
        try:
            ln = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        messages = body.get("messages", [])
        stream = bool(body.get("stream"))
        last_user = ""
        for m in messages:
            if m.get("role") == "user":
                last_user = m.get("content", "")
        if not last_user:
            last_user = "\n".join(str(m.get("content", "")) for m in messages
                                  if m.get("role") != "assistant")
        conv_key = self.headers.get("X-Conv-Key", "default")
        try:
            cli = get_client(conv_key)
        except SystemExit as e:
            return self._json(500, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})

        cid = uuid.uuid4().hex[:12]
        if not stream:
            full, reasoning = [], []
            try:
                for ev in cli.send(last_user):
                    if ev.get("role") == "assistant":
                        if ev.get("content"):
                            full.append(ev["content"])
                        if ev.get("reasoning"):
                            reasoning.append(ev["reasoning"])
            except Exception as e:
                return self._json(500, {"error": str(e)})
            text = "".join(full)
            return self._json(200, {
                "id": f"chatcmpl-{cid}", "object": "chat.completion",
                "created": int(time.time()), "model": MODEL_NAME,
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": len(text),
                          "total_tokens": len(text)}})

        # ---- 流式 ----
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(sse_chunk(cid, role="assistant"))
            self.wfile.flush()
            for ev in cli.send(last_user):
                if ev.get("role") != "assistant":
                    continue
                if ev.get("reasoning"):
                    obj = {"id": f"chatcmpl-{cid}", "object": "chat.completion.chunk",
                           "created": int(time.time()), "model": MODEL_NAME,
                           "choices": [{"index": 0, "delta": {
                               "reasoning_content": ev["reasoning"]},
                               "finish_reason": None}]}
                    self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
                    self.wfile.flush()
                if ev.get("content"):
                    self.wfile.write(sse_chunk(cid, delta=ev["content"]))
                    self.wfile.flush()
            self.wfile.write(sse_chunk(cid, finish="stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.wfile.write(sse_chunk(cid, delta=f"\n[error] {e}"))
                self.wfile.write(b"data: [DONE]\n\n")
            except Exception:
                pass


if __name__ == "__main__":
    print(f"OpenAI 兼容端点: http://127.0.0.1:{PORT}/v1/chat/completions  model={MODEL_NAME}")
    print(f"测试: curl http://127.0.0.1:{PORT}/v1/chat/completions -d "
          f"'{{\"model\":\"yuketang-24h\",\"messages\":[{{\"role\":\"user\",\"content\":\"你好\"}}]}}' -H 'Content-Type: application/json'")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
