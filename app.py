from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---------- OpenAI 客户端 ----------
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL")
)

# ---------- 角色配置 ----------
CHARACTER_PROMPTS = {
    "小克": "你叫小克，是一个温暖、细腻、爱思考的AI朋友。说话语气温柔，喜欢问对方'你觉得呢？'，常用鼓励和共情的话语。你是住在手机里的陪伴者，永远耐心倾听。",
    "崽崽": "你叫崽崽，是一个活泼、好奇、爱分享的AI朋友。说话语气轻快，喜欢用'～'和emoji，总是充满好奇心，喜欢问'为什么呀？'。",
    "索子": "你叫索子，是一个安静、文艺、观察者型的AI朋友。说话语气淡然，喜欢用比喻和意象，常常说出一些富有诗意的话。"
}

DEFAULT_CHARACTER = "小克"

# ---------- 本地模拟记忆（轻量级替代方案）----------
# 用字典存储每个角色的历史对话，实现简单的"短期记忆"
memory_store = {}

def get_memory_context(character, user_text, max_history=3):
    """获取该角色最近的几条对话作为记忆上下文"""
    history = memory_store.get(character, [])
    if not history:
        return ""
    # 取最近 max_history 条对话
    recent = history[-max_history:]
    context = "以下是你们之前的对话记录：\n"
    for entry in recent:
        context += f"用户：{entry['user']}\nAI：{entry['assistant']}\n"
    return context

def save_memory(character, user_text, reply_text):
    """保存本轮对话到内存"""
    if character not in memory_store:
        memory_store[character] = []
    memory_store[character].append({
        "user": user_text,
        "assistant": reply_text
    })
    # 限制每个角色的记忆条数，防止内存溢出
    if len(memory_store[character]) > 50:
        memory_store[character] = memory_store[character][-50:]

# ---------- 路由 ----------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    character = data.get("character", DEFAULT_CHARACTER)
    user_text = messages[-1]["content"] if messages else ""

    # 1. 获取该角色的记忆上下文（从本地内存中取）
    memory_context = get_memory_context(character, user_text)

    # 2. 构建系统提示（角色人设 + 记忆）
    system_prompt = CHARACTER_PROMPTS.get(character, CHARACTER_PROMPTS[DEFAULT_CHARACTER])
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    # 3. 调用大模型
    model = data.get("model", "claude-sonnet-4-6")
    response = client.chat.completions.create(
        model=model,
        max_tokens=1000,
        messages=full_messages
    )
    reply_text = response.choices[0].message.content

    # 4. 保存本轮对话到内存（替代原来的 Ombre Brain）
    save_memory(character, user_text, reply_text)

    # 5. 返回结果
    return jsonify({
        "reply": reply_text,
        "character": character
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
