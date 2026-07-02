from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import os
import asyncio
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

app = Flask(__name__)

# ---------- OpenAI 客户端 ----------
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL")
)

# ---------- Ombre Brain MCP 配置 ----------
OMBRE_URL = "http://localhost:8000/mcp"

# ---------- 角色配置 ----------
CHARACTER_PROMPTS = {
    "小克": "你叫小克，是一个温暖、细腻、爱思考的AI朋友。说话语气温柔，喜欢问对方'你觉得呢？'，常用鼓励和共情的话语。你是住在手机里的陪伴者，永远耐心倾听。",
    "崽崽": "你叫崽崽，是一个活泼、好奇、爱分享的AI朋友。说话语气轻快，喜欢用'～'和emoji，总是充满好奇心，喜欢问'为什么呀？'。",
    "索子": "你叫索子，是一个安静、文艺、观察者型的AI朋友。说话语气淡然，喜欢用比喻和意象，常常说出一些富有诗意的话。"
}

DEFAULT_CHARACTER = "小克"

# ---------- 异步工具 ----------
async def call_ombre_tool(tool_name, arguments=None):
    arguments = arguments or {}
    async with streamablehttp_client(OMBRE_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            texts = [b.text for b in result.content if hasattr(b, "text")]
            return "\n".join(texts)

def run_async(coro):
    return asyncio.run(coro)

# ---------- 路由 ----------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    # 前端需要传递当前角色名称，若未提供则使用默认
    character = data.get("character", DEFAULT_CHARACTER)
    user_text = messages[-1]["content"] if messages else ""

    # 1. 获取该角色的专属记忆（通过角色名称过滤，需要Ombre Brain支持元数据过滤）
    # 这里假设 breath 工具支持 `filters` 参数，若不支持则只能全量检索
    try:
        # 方式1：如果breath支持过滤（扩展参数）
        # memory_context = run_async(call_ombre_tool("breath", {
        #     "query": user_text,
        #     "filters": {"character": character}
        # }))
        # 方式2：当前breath只接受query，我们临时在存储时加上角色标签，检索时靠语义匹配
        memory_context = run_async(call_ombre_tool("breath", {"query": user_text}))
    except Exception as e:
        memory_context = ""
        print("breath error:", e)

    # 2. 构建系统提示（角色人设 + 记忆）
    system_prompt = CHARACTER_PROMPTS.get(character, CHARACTER_PROMPTS[DEFAULT_CHARACTER])
    if memory_context:
        system_prompt += f"\n\n以下是相关的过往记忆：\n{memory_context}"

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    # 3. 调用大模型（可根据角色切换不同模型）
    model = data.get("model", "gpt-3.5-turbo")  # 可自行调整
    response = client.chat.completions.create(
        model=model,
        max_tokens=1000,
        messages=full_messages
    )
    reply_text = response.choices[0].message.content

    # 4. 存储本轮对话到Ombre Brain（带上角色标签，以便后续检索）
    try:
        # 存储时植入角色前缀，便于检索时通过语义关联
        stored_content = f"[{character}] 苏萌说：{user_text}\n[{character}] 回复：{reply_text}"
        run_async(call_ombre_tool("hold", {
            "content": stored_content
        }))
    except Exception as e:
        print("hold error:", e)

    # 5. 返回结果
    return jsonify({
        "reply": reply_text,
        "character": character  # 回传确认，便于前端展示
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)