from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import os
import json
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

# 角色 -> 模型（群聊里每个角色用自己的模型说话）
CHARACTER_MODELS = {
    "小克": "claude-sonnet-4-6",
    "崽崽": "claude-sonnet-4-6",
    "索子": "claude-sonnet-4-6",
}
DEFAULT_MODEL = "claude-sonnet-4-6"

# ---------- 本地模拟记忆（轻量级替代方案）----------
memory_store = {}
def get_memory_context(character, user_text, max_history=3):
    history = memory_store.get(character, [])
    if not history:
        return ""
    recent = history[-max_history:]
    context = "以下是你们之前的对话记录：\n"
    for entry in recent:
        context += f"用户：{entry['user']}\nAI：{entry['assistant']}\n"
    return context
def save_memory(character, user_text, reply_text):
    if character not in memory_store:
        memory_store[character] = []
    memory_store[character].append({"user": user_text, "assistant": reply_text})
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

    memory_context = get_memory_context(character, user_text)
    system_prompt = CHARACTER_PROMPTS.get(character, CHARACTER_PROMPTS[DEFAULT_CHARACTER])
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    model = data.get("model", "claude-sonnet-4-6")
    response = client.chat.completions.create(
        model=model,
        max_tokens=1000,
        messages=full_messages
    )
    reply_text = response.choices[0].message.content

    save_memory(character, user_text, reply_text)

    return jsonify({"reply": reply_text, "character": character})


# ============================================================
# 群聊功能
# ============================================================

def build_transcript(entries, limit=20):
    """把 [{speaker, content}, ...] 拼成一段可读文本"""
    lines = [f"{e['speaker']}：{e['content']}" for e in entries[-limit:]]
    return "\n".join(lines)

def decide_speakers(transcript_text, members):
    """用一次轻量调用判断接下来该谁接话，返回角色名列表（最多3个，按发言顺序）"""
    prompt = (
        f"你是群聊场景的旁观者。群里有这些角色：{'、'.join(members)}。"
        "根据下面的聊天记录（最后一条是苏萌刚发的新消息），判断接下来应该由谁接话，"
        "可以是一个角色，也可以是多个角色依次发言（最多3个），也可以没有人回复（返回空数组）。"
        "只输出一个JSON数组，例如[\"崽崽\",\"索子\"]，不要输出任何别的文字或解释。\n\n"
        f"聊天记录：\n{transcript_text}"
    )
    try:
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        speakers = json.loads(raw)
        return [s for s in speakers if s in members][:3]
    except Exception as e:
        print("decide_speakers error:", e)
        return []

@app.route("/group-chat", methods=["POST"])
def group_chat():
    data = request.json
    members = data.get("members", list(CHARACTER_PROMPTS.keys()))
    transcript = data.get("transcript", [])  # [{speaker, content}], 最后一条是苏萌的新消息

    speakers = decide_speakers(build_transcript(transcript), members)
    replies = []

    for character in speakers:
        current_transcript = build_transcript(transcript + replies)
        system_prompt = CHARACTER_PROMPTS.get(character, "")
        others = [m for m in members if m != character]
        system_prompt += (
            f"\n\n你正在一个群聊里，一起在场的还有：{'、'.join(others) if others else '没有其他人'}。"
            "下面是目前为止的聊天记录，请你以你的身份自然地接一句话，"
            "不用重复别人说过的内容，也不要在回复开头加自己的名字。\n\n"
            f"{current_transcript}"
        )
        model = CHARACTER_MODELS.get(character, DEFAULT_MODEL)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=500,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": "请接话。"}]
            )
            reply_text = resp.choices[0].message.content
        except Exception as e:
            print("group reply error:", e)
            reply_text = "（这句话没说出来，网络似乎不太顺畅）"
        replies.append({"speaker": character, "content": reply_text})

    return jsonify({"replies": replies})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
