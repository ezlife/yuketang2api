#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Chrome DevTools "Copy as cURL" 的请求粘进来,自动产出 ykt24h.py 需要的环境变量。
用法:
  python3 parse_curl.py            # 交互式粘贴(粘完按回车+Ctrl-D 结束)
  python3 parse_curl.py curl.txt   # 从文件读
"""
import json
import re
import sys
import shlex


def parse(curl: str):
    out = {}
    # cookie 头
    m = re.search(r"-H\s+[\"']cookie:\s*([^\"']+)[\"']", curl, re.I) or \
        re.search(r"--cookie\s+[\"']([^\"']+)[\"']", curl, re.I) or \
        re.search(r"\$cookie\s+[\"']([^\"']+)[\"']", curl, re.I)
    if m:
        ck = m.group(1).strip()
        keep = []
        for part in ck.split(";"):
            k = part.strip().split("=")[0].strip()
            if k in ("sessionid", "csrftoken", "uv_id", "university_id"):
                keep.append(part.strip())
        out["YKT_SESSION"] = "; ".join(keep)
    # csrf 头
    m = re.search(r"-H\s+[\"']x-csrftoken:\s*([^\"']+)[\"']", curl, re.I)
    if m and "csrftoken=" + m.group(1).strip() not in out.get("YKT_SESSION", ""):
        out["YKT_SESSION"] = out.get("YKT_SESSION", "") + "; csrftoken=" + m.group(1).strip()
    # university-id
    m = re.search(r"-H\s+[\"'](?:university-id|uv-id):\s*([^\"']+)[\"']", curl, re.I)
    if m:
        out["YKT_UV_ID"] = m.group(1).strip()
    # URL 与 query
    m = re.search(r"(?:curl(?:\s+\S+)*?\s+'|curl(?:\s+\S+)*?\s+)(https?://[^'\s]+)", curl)
    url = m.group(1) if m else ""
    out["_url"] = url
    q = dict(re.findall(r"([a-zA-Z_]+)=([^&'\s]+)", url.split("?", 1)[1] if "?" in url else ""))
    if q.get("agent_id"):
        out["YKT_AGENT_ID"] = q["agent_id"]
    if q.get("agentId"):
        out["YKT_AGENT_ID"] = q["agentId"]
    if q.get("classroom_id"):
        out["YKT_CLASSROOM_ID"] = q["classroom_id"]
    if q.get("classroomId"):
        out["YKT_CLASSROOM_ID"] = q["classroomId"]
    # body
    m = re.search(r"--data-raw\s+'([^']*)'", curl) or re.search(r"-d\s+'([^']*)'", curl)
    if m:
        try:
            out["_body"] = json.loads(m.group(1))
        except Exception:
            out["_body"] = m.group(1)
    return out


def main():
    if len(sys.argv) > 1:
        curl = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
    else:
        print("把 Copy as cURL 的内容粘进来,结束后按回车再 Ctrl-D:")
        curl = sys.stdin.read()
    r = parse(curl)
    print("\n# ===== 复制到终端 export =====")
    for k in ("YKT_SESSION", "YKT_UV_ID", "YKT_AGENT_ID", "YKT_CLASSROOM_ID"):
        if k in r:
            print(f"export {k}='{r[k]}'")
    print("\n# 请求明细(核对用)")
    print("URL:", r.get("_url", "?"))
    print("body:", json.dumps(r.get("_body", ""), ensure_ascii=False))
    if not r.get("YKT_SESSION"):
        print("\n[!] 没解出 Cookie:确认拷的是 changjie.yuketang.cn 的请求(不是静态资源/别的域)")


if __name__ == "__main__":
    main()
