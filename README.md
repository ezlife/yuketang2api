# 雨课堂 24H AI 智能学伴 → API(逆向)

逆向对象:`changjie.yuketang.cn` Web 前端
(frontend `fe-static/web/1.2.354`,模块 94192=HTTP/SSE 封装、8181=聊天 SDK、66542=useChat hook)。

## 一、逆向结论(协议)

### 发消息(核心,流式)

```
POST https://changjie.yuketang.cn/api/v3/ai/online-courseware/capability-conversation/send-message-stream
Content-Type: application/json
Cookie: sessionid=...; csrftoken=...
X-CSRFToken: <csrftoken 值>
xtbz: ykt
Xt-Agent: web
university-id: <uv_id,可为 0>

{"messageInfo":"你的问题","conversationId":123456}
```

- 响应**不是标准 SSE**,是 `}\n{` 拼接的 JSON 增量流,逐片解析
- 每片 JSON 字段:
  - `content`:正文增量(string)
  - `reasoning_content`:思考链增量
  - `type == "heartbeat"`:心跳,跳过
  - `send_id` / `reply_id`:问答消息 id(第一条带)
  - `end_reason >= 0`:结束(敏感词/出错也在这)
  - `recommend_questions`、`rag_documents`、`additional`、`node_info`
- 前端源码里就是拿 XHR `onDownloadProgress` 的 `responseText` 增量按 `}\n{` 切分

### 会话与周边接口

| 功能 | 请求 |
|---|---|
| 查会话 | `GET /c27/online_courseware/capability-conversation/?agent_id=..&classroom_id=..&source_id=0` |
| 建会话 | `POST /c27/online_courseware/capability-conversation/`(同参数 JSON body) |
| 历史 | `GET /c27/online_courseware/capability-conversation/{id}/talk_records/?page_size=20` |
| 停止生成 | `POST /c27/online_courseware/capability-conversation/reply_stop/` |
| 清空历史 | `POST /c27/online_courseware/capability-conversation/{id}/clear/` |
| Agent能力 | `GET /c27/online_courseware/ykt/agent/{agentId}/capability/?category=1` |

### 认证

Django session:`sessionid` + `csrftoken` 两个 cookie,POST 带 `X-CSRFToken` 头。无独立 token。
辅助头:`xtbz: ykt`、`Xt-Agent: web`、`university-id`。

### 入口链路(为什么这样设计)

课程页"24小时智能学伴"图标 → 同站 iframe
`/ai-workspace/chatbot-window?agentId=..&category=1&classroomId=..`(iframe URL 里就有 agentId)
→ iframe 内 `useChat` hook:GET/POST 建会话 → SSE 发消息。

## 二、怎么用(三步)

### 1. 拿 Cookie 和 agentId

浏览器登录雨课堂 → 打开一个带 24H 学伴的课程 → F12 控制台粘贴运行
[grab_snippet.js](grab_snippet.js) 的内容,会直接打出:

```
export YKT_SESSION='sessionid=xxx; csrftoken=yyy'
export YKT_UV_ID='0'
export YKT_AGENT_ID='123456'
export YKT_CLASSROOM_ID='789'
```

> 手工方式:F12 → Application → Cookies → `changjie.yuketang.cn` 拷 `sessionid`/`csrftoken`;
> Network 过滤 `send-message-stream` 或看 chatbot iframe 的 URL 参数拿 `agentId`。

### 2. 命令行直聊

```bash
cd ~/yuketang-research
export YKT_SESSION='...' YKT_AGENT_ID='...'
python3 ykt24h.py chat "用一句话解释傅里叶变换"
python3 ykt24h.py repl      # 多轮(同会话自动带上下文)
```

### 3. 变成 OpenAI 兼容 API(to api)

```bash
python3 ykt24h_server.py 8317
```

然后任意 OpenAI 客户端接入:

```bash
curl http://127.0.0.1:8317/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"yuketang-24h","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

- Cherry Studio / one-api / new-api:API 地址填 `http://127.0.0.1:8317/v1`,Key 任意,模型名 `yuketang-24h`
- 支持流式 `stream:true` 和非流式;`reasoning_content` 字段兼容思维链展示
- 上下文在雨课堂会话侧维护:同一个 OpenAI 客户端对话发 `X-Conv-Key` 头区分不同会话,默认共用一个

## 三、注意事项

- `sessionid` 过期后脚本会提示重新拷;敏感词会以 `end_reason` 返回,正文被替换
- 频率别拉满,雨课堂侧有会话审计(教师端能看到 24H 学伴问答记录)
- `long_task: true` 走长任务模式(报告/文档生成类)
- 复现文件:`chunks/` 是逆向用的原始 JS,`ykt24h.py` 是客户端,`ykt24h_server.py` 是兼容层
