# yuketang2api — 雨课堂 24H AI 智能学伴 → API

把雨课堂的「24H AI 智能学伴」逆向成 OpenAI 兼容 API。
**已在真实登录态下完整验证打通**(2026-11,流式、多轮、usage 均正常,底层模型 `智谱GLM-4-Plus`)。

## 协议(逆向 + 实测验证)

入口域:**`www.yuketang.cn`**(chatbot iframe 同源)。认证:Django session(`sessionid`+`csrftoken` cookie,HttpOnly 只能从 Network 请求头抓)。

### 发消息(核心,流式)

```
POST https://www.yuketang.cn/api/v3/ai/online-courseware/capability-conversation/send-message-stream?classroom_id=..&agent_id=..
Cookie: sessionid=...; csrftoken=...      X-CSRFToken: <csrftoken>
xtbz: ykt   Xt-Agent: web   university-id: <uv_id>

{
  "messageInfo": {                 ← 对象!传字符串服务端直接 500
    "templateId": 0, "source": 0,
    "content": "你的问题",
    "agentId": 27537, "type": "str", "files": [], "lessonId": ""
  },
  "conversationId": 30210152
}
```

响应 `application/octet-stream`,每行一个 JSON(`}\n{` 拼接):

```
{"reply_id":133980404,"send_id":133980403}     ← 首片:消息 id
{"content":"","additional":{}}
{"content":"你好","provider":null}               ← 正文增量流
{"content":"我是","provider":null}
{"content":"","rag_documents":[...],"provider":"zhipu"}   ← 引用课程文档
{"content":"","usage":{"prompt_tokens":7839,...},"model":"智谱GLM-4-Plus"}
{"content":"","rag_documents":[...],"end_reason":0}       ← 结束
```

注意:`content` 里混有**零宽字符水印**(U+200B-200D/U+FEFF,反爬),要 strip。

### 配套接口

| 功能 | 请求 |
|---|---|
| 查会话 | `GET /c27/online_courseware/capability-conversation/?capability_id=..&entity_id=..&entity_type=25&classroom_id=..&source_id=0&agent_id=..` → `data.results[]` |
| 建会话 | `POST /c27/online_courseware/capability-conversation/`(同参数 JSON body) |
| 历史 | `GET /c27/online_courseware/capability-conversation/{id}/talk_records/?page_size=20` |
| 停止生成 | `POST /c27/online_courseware/capability-conversation/reply_stop/` |
| 清空 | `POST /c27/online_courseware/capability-conversation/{id}/clear/` |

24H 学伴:`entity_type=25`,`entity_id` = classroom_id。

## 使用

### 1. 抓参数(30 秒)

`sessionid` 是 HttpOnly,控制台 JS 读不到——从 Network 抓:

1. 登录雨课堂,进有 24H 学伴的课程,打开学伴问一句
2. `F12` → **Network** → 过滤 `capability-conversation`
3. 右键任一请求(推荐 GET 那条)→ **Copy → Copy as cURL**
4. 粘贴运行解析器,自动产出全部环境变量:

```bash
python3 parse_curl.py <(pbpaste)   # 或粘到文件/交互粘贴
```

得到(示例值):

```bash
export YKT_SESSION='sessionid=xxx; csrftoken=yyy'
export YKT_UV_ID='2614'
export YKT_AGENT_ID='27537'
export YKT_CLASSROOM_ID='33073653'
export YKT_ENTITY_ID='33073653'
export YKT_ENTITY_TYPE='25'
export YKT_CAPABILITY_ID='418409'
```

### 2. 命令行直聊(实测输出)

```bash
python3 ykt24h.py chat "一句话:什么是雨课堂?"
# 雨课堂是一种基于移动互联网的教学工具,它能够帮助教师实现课前预习、课堂互动和课后反馈的全流程教学管理。
# [end_reason=0 model=智谱GLM-4-Plus usage={'prompt_tokens': 4118, ...}]

python3 ykt24h.py repl      # 多轮(同会话自动带上下文),/new 开新会话
```

### 3. OpenAI 兼容 API

```bash
python3 ykt24h_server.py 8317
```

任何 OpenAI 客户端(Cherry Studio / one-api / openai sdk):

```bash
curl http://127.0.0.1:8317/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"yuketang-24h","stream":true,"messages":[{"role":"user","content":"你好"}]}'
```

- `stream:true` 流式;`reasoning_content` 兼容思维链展示
- 多轮上下文在雨课堂会话侧;用 `X-Conv-Key` 请求头隔离不同对话
- `YKT_BASE` 环境变量可换域(默认 `https://www.yuketang.cn`)

## 文件

- `ykt24h.py` — 核心客户端(会话管理 + 流式解析 + CLI)
- `ykt24h_server.py` — OpenAI 兼容服务(标准库实现,零依赖)
- `parse_curl.py` — DevTools "Copy as cURL" → 环境变量
- `grab_snippet.js` — 浏览器控制台辅助(读不到 HttpOnly cookie,仅参考)

## 注意

- `sessionid` 过期脚本会提示重抓;教师端可见 24H 学伴问答审计,频率悠着点
- `long_task:true` 走长任务模式(报告生成类)
- 免责:仅供个人学习研究
