#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雨课堂 24H AI 智能学伴 → API 客户端
逆向自 www.yuketang.cn 前端 (fe-static web/1.2.354, module 94192/8181/66542)
已在真实登录态下验证打通(HTTP 200,流式正常,底层模型 智谱GLM-4-Plus)。

协议要点(实测验证):
  发消息(流式): POST /api/v3/ai/online-courseware/capability-conversation/send-message-stream?classroom_id=..&agent_id=..
      body: {"messageInfo":{            ← 注意是对象,不是字符串!
               "templateId":0,"source":0,"content":"<文本>",
               "agentId":<id>,"type":"str","files":[],"lessonId":""},
             "conversationId":<id>}
      响应: application/octet-stream, 每行一个 JSON(}\n{ 拼接),字段:
        {reply_id, send_id} → {"content":"增量"} 连续流 → rag_documents
        → usage/model("智谱GLM-4-Plus") → {"end_reason":0} 结束
        content 里可能混零宽字符(\u200B-\u200D\uFEFF,反爬水印,需 strip)
  查会话:   GET  /c27/online_courseware/capability-conversation/?capability_id=..&entity_id=..&entity_type=25&classroom_id=..&source_id=0&agent_id=..
             → data.results[] (按 last_talk_time 倒序,取[0]或新建)
  建会话:   POST /c27/online_courseware/capability-conversation/ (同参数 JSON body)
  历史:     GET  /c27/online_courseware/capability-conversation/{id}/talk_records/
  停止生成: POST /c27/online_courseware/capability-conversation/reply_stop/
  清空:     POST /c27/online_courseware/capability-conversation/{id}/clear/
  Agent能力: GET /c27/online_courseware/ykt/agent/{agentId}/capability/?category=1
  认证:     Cookie sessionid + csrftoken(Django);POST 需 X-CSRFToken 头
             xtbz: ykt / Xt-Agent: web / university-id: <uv_id>
  24H 学伴 entity_type = 25

用法:
  export YKT_SESSION="sessionid=xxx; csrftoken=yyy"    # 从浏览器拷
  export YKT_AGENT_ID=27537
  export YKT_ENTITY_ID=33073653 YKT_ENTITY_TYPE=25 YKT_CAPABILITY_ID=418409
  export YKT_CLASSROOM_ID=33073653 YKT_UV_ID=2614
  python3 ykt24h.py chat "你好"
  python3 ykt24h.py repl
"""
import json
import os
import re
import sys
import time
import requests

BASE = os.environ.get("YKT_BASE", "https://www.yuketang.cn").rstrip("/")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _env(name, default=""):
    return os.environ.get(name, default).strip()


class Yuketang24H:
    def __init__(self, session_cookie=None, uv_id=0, agent_id=0, classroom_id=0):
        self.cookie = session_cookie or _env("YKT_SESSION")
        self.uv_id = _env("YKT_UV_ID", str(uv_id))
        self.agent_id = int(_env("YKT_AGENT_ID", str(agent_id)) or 0)
        self.classroom_id = int(_env("YKT_CLASSROOM_ID", str(classroom_id)) or 0)
        self.entity_id = _env("YKT_ENTITY_ID")
        self.entity_type = _env("YKT_ENTITY_TYPE", "25")
        self.capability_id = _env("YKT_CAPABILITY_ID")
        if not self.cookie:
            raise SystemExit("缺 Cookie: 先 export YKT_SESSION='sessionid=...; csrftoken=...'"
                             "(浏览器 F12 → Network → 任意请求 → 请求头 Cookie)")
        m = re.search(r"csrftoken=([^;]+)", self.cookie)
        self.csrftoken = m.group(1) if m else ""
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Cookie": self.cookie,
            "xtbz": "ykt",
            "Xt-Agent": "web",
            "university-id": self.uv_id,
            "uv-id": self.uv_id,
            "Referer": BASE + "/ai-workspace/chatbot-window",
            "Origin": BASE,
        })
        self.conversation_id = None

    # ---------- 基础 ----------
    def _check(self, r):
        if r.status_code in (301, 302) or "web_redirect" in r.text[:200]:
            raise SystemExit("登录态失效(sessionid 过期),重新从浏览器拷 Cookie")
        return r

    def get_json(self, path, params=None):
        r = self._check(self.s.get(BASE + path, params=params, timeout=30))
        return r.json()

    def post_json(self, path, body=None, params=None):
        h = {"Content-Type": "application/json", "X-CSRFToken": self.csrftoken}
        r = self._check(self.s.post(BASE + path, params=params, json=body, headers=h, timeout=30))
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

    # ---------- Agent 能力(24H 学伴配置) ----------
    def agent_capability(self, agent_id=None, category=1):
        aid = agent_id or self.agent_id
        return self.get_json(f"/c27/online_courseware/ykt/agent/{aid}/capability/",
                             {"category": category})

    # ---------- 会话 ----------
    def get_or_create_conversation(self, agent_id=None, classroom_id=None):
        aid = agent_id if agent_id is not None else self.agent_id
        cid = classroom_id if classroom_id is not None else self.classroom_id
        q = {"capability_id": self.capability_id or "",
             "entity_id": self.entity_id, "entity_type": self.entity_type,
             "classroom_id": cid, "source_id": 0, "agent_id": aid,
             "lesson_id": "", "entity_ids": "", "student_id": "", "source_ids": ""}
        data = self.get_json("/c27/online_courseware/capability-conversation/", q)
        conv = None
        if isinstance(data, dict):
            d = data.get("data")
            if isinstance(d, dict):
                results = d.get("results")
                conv = results[0] if results else None
            elif isinstance(d, list):
                conv = d[0] if d else None
        if not conv:
            body = dict(q, agent_id=aid, classroom_id=cid, source_id=0)
            data = self.post_json("/c27/online_courseware/capability-conversation/", body)
            conv = data.get("data") if isinstance(data, dict) else None
            if isinstance(conv, dict) and conv.get("results"):
                conv = conv["results"][0]
        if not conv:
            raise RuntimeError(f"拿不到会话: {json.dumps(data, ensure_ascii=False)[:300]}")
        self.conversation_id = conv["id"]
        return self.conversation_id

    def history(self, conversation_id=None, page_size=20):
        cid = conversation_id or self.conversation_id
        return self.get_json(f"/c27/online_courseware/capability-conversation/{cid}/talk_records/",
                             {"page_size": page_size, "last_id": "",
                              "agent_id": self.agent_id, "classroom_id": self.classroom_id})

    def clear_history(self, conversation_id=None):
        cid = conversation_id or self.conversation_id
        return self.post_json(f"/c27/online_courseware/capability-conversation/{cid}/clear/", {})

    # ---------- 发消息(流式) ----------
    def send(self, message, conversation_id=None, long_task=False):
        """流式发送。yield {role, content, reasoning, done, extra}"""
        cid = conversation_id or self.conversation_id
        if not cid:
            cid = self.get_or_create_conversation()
        # messageInfo 是对象(字符串形式会被服务端 500)
        message_info = {"templateId": 0, "source": 0, "content": message,
                        "agentId": self.agent_id, "type": "str",
                        "files": [], "lessonId": ""}
        body = {"messageInfo": message_info, "conversationId": cid}
        if long_task:
            body["long_task"] = True
        h = {"Content-Type": "application/json", "X-CSRFToken": self.csrftoken,
             "Accept": "application/json, text/plain, */*"}
        q = {}
        if self.agent_id:
            q["agent_id"] = self.agent_id
        if self.classroom_id:
            q["classroom_id"] = self.classroom_id
        r = self.s.post(BASE + "/api/v3/ai/online-courseware/capability-conversation/send-message-stream",
                        params=q, json=body, headers=h, stream=True, timeout=300)
        self._check(r)
        # 与前端一致: 增量解析 "}\n{" 分隔的 JSON 流
        buf = ""
        decoder = _JsonStreamDecoder()
        for chunk in r.iter_content(chunk_size=None):
            if not chunk:
                continue
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", errors="replace")
            buf += chunk
            for obj in decoder.feed(buf):
                buf = ""
                for ev in self._handle_event(obj):
                    yield ev
        for obj in decoder.flush():
            for ev in self._handle_event(obj):
                yield ev
        yield {"role": "assistant", "content": "", "reasoning": "", "done": True}

    def _handle_event(self, w):
        if not isinstance(w, dict):
            return
        if w.get("type") == "heartbeat":
            return
        # send_id / reply_id
        if w.get("reply_id") and w.get("send_id"):
            yield {"role": "meta", "send_id": w["send_id"], "reply_id": w["reply_id"]}
        out_c, out_r = "", ""
        if isinstance(w.get("content"), str):
            out_c = _strip_zwsp(w["content"])
        if isinstance(w.get("reasoning_content"), str):
            out_r = _strip_zwsp(w["reasoning_content"])
        # search 类: content 是对象
        if isinstance(w.get("content"), dict):
            cm = w["content"]
            if cm.get("event") == "cmpl" and cm.get("action") == 3:
                txt = (cm.get("aiSummaryResult") or {}).get("text", "")
                if txt:
                    out_c = _strip_zwsp(txt)
        if out_c or out_r:
            yield {"role": "assistant", "content": out_c, "reasoning": out_r, "done": False}
        if w.get("end_reason") is not None and w.get("end_reason") >= 0:
            ev = {"role": "assistant", "content": "", "reasoning": "",
                  "done": True, "end_reason": w.get("end_reason")}
            if w.get("recommend_questions"):
                ev["recommend_questions"] = w["recommend_questions"]
            if w.get("rag_documents"):
                ev["rag_documents"] = w["rag_documents"]
            if w.get("usage"):
                ev["usage"] = w["usage"]
            if w.get("model"):
                ev["model"] = w["model"]
            yield ev

    def stop(self, conversation_id, send_id, reply_id, content, ds="text"):
        body = {"additional": None, "ds": ds, "conversation_id": conversation_id,
                "send_id": send_id, "reply_id": reply_id, "content": content,
                "reasoning_content": "", "prompt_tokens": 0, "completion_tokens": 0,
                "embedding_tokens": 0, "rerank_tokens": 0, "provider": "null"}
        return self.post_json("/c27/online_courseware/capability-conversation/reply_stop/", body)


def _strip_zwsp(s):
    return re.sub(r"[\u200B-\u200D\uFEFF]+", "", s)


class _JsonStreamDecoder:
    """增量切分 '}{ ' 拼接的 JSON 对象流(等价前端 }\n{ 切分),括号/字符串感知。"""
    def __init__(self):
        self.pending = ""

    def feed(self, text):
        self.pending += text
        objs, rest = self._parse(self.pending)
        self.pending = rest
        return objs

    def flush(self):
        objs, rest = self._parse(self.pending, final=True)
        self.pending = rest
        return objs

    def _parse(self, s, final=False):
        out, i, n = [], 0, len(s)
        while i < n:
            # 跳到首个 { 或 [
            while i < n and s[i] not in "{[":
                i += 1
            if i >= n:
                return out, ""
            depth, j, in_str, esc, start = 0, i, False, False, i
            ok = False
            while j < n:
                c = s[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                else:
                    if c == '"':
                        in_str = True
                    elif c in "{[":
                        depth += 1
                    elif c in "}]":
                        depth -= 1
                        if depth == 0:
                            ok = True
                            j += 1
                            break
                j += 1
            if not ok:
                if final and j >= n and depth > 0:
                    # 可能被截断,保留
                    return out, s[start:]
                return out, s[i:]
            frag = s[start:j]
            try:
                out.append(json.loads(frag))
            except Exception:
                pass
            i = j
        return out, ""


# ---------- CLI ----------
def _cli():
    if len(sys.argv) >= 2 and sys.argv[1] == "chat":
        msg = sys.argv[2] if len(sys.argv) > 2 else "你好"
        cli = Yuketang24H()
        cli.get_or_create_conversation()
        print(f"[conversation {cli.conversation_id}]")
        full, think = [], []
        for ev in cli.send(msg):
            if ev.get("role") == "assistant":
                if ev.get("reasoning"):
                    think.append(ev["reasoning"])
                if ev.get("content"):
                    full.append(ev["content"])
                    print(ev["content"], end="", flush=True)
                if ev.get("done") and ev.get("end_reason") is not None:
                    print(f"\n[end_reason={ev['end_reason']}"
                          f" model={ev.get('model','?')}"
                          f" usage={ev.get('usage',{})}]")
                    if ev.get("recommend_questions"):
                        print("推荐问题:", ev["recommend_questions"])
        print()
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "repl":
        cli = Yuketang24H()
        cli.get_or_create_conversation()
        print(f"[conversation {cli.conversation_id}] 输入 /hist 看历史, /new 新会话, Ctrl-D 退出")
        while True:
            try:
                msg = input("你> ").strip()
            except EOFError:
                break
            if not msg:
                continue
            if msg == "/new":
                cli.conversation_id = None
                cli.get_or_create_conversation()
                print(f"[新会话 {cli.conversation_id}]")
                continue
            if msg == "/hist":
                print(json.dumps(cli.history(), ensure_ascii=False, indent=2)[:2000])
                continue
            print("AI> ", end="", flush=True)
            for ev in cli.send(msg):
                if ev.get("role") == "assistant" and ev.get("content"):
                    print(ev["content"], end="", flush=True)
            print()
    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
