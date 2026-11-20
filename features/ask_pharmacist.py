"""
AI 藥師小幫手（Gemini）
住戶打「問AI藥師」加上問題，AI 用白話回答簡單的用藥問題。
原本在 features/AI 藥師回覆功能 裡，改成樣板格式讓 router 載得到。

用法：
  「問AI藥師 降血壓藥可以飯前吃嗎？」 → AI 回答
  只打「問AI藥師」                      → 說明怎麼問
"""
import os

from linebot.v3.messaging import TextMessage

NAME = "問AI藥師"
AUTHOR = "@b101114085"
KEYWORDS = ["問AI藥師", "問藥師"]

MAX_QUESTION_LEN = 300
MY_MEDICINES = "高血壓藥、高血脂藥、糖尿病藥"

EMERGENCY_KEYWORDS = ["胸痛", "胸悶", "呼吸困難", "喘不過氣", "昏倒", "意識不清",
                      "抽搐", "嚴重過敏", "吃太多藥", "誤食", "自殺"]

AI_SYSTEM_PROMPT = f"""你是社宅住戶的「用藥衛教小幫手」，對象多為長者。
規則：
1. 使用繁體中文（台灣用語），句子短、用詞白話，總字數 200 字內。
2. 只回答用藥常識與健康衛教，其他主題請禮貌婉拒。
3. 絕對不可以診斷疾病、建議增減藥量、換藥或停藥；遇到這類問題，請引導詢問醫師或藥師。
4. 不確定時要誠實說不確定，不可編造。
5. 若描述可能是緊急狀況，請先叫對方撥打 119。
6. 住戶目前的藥物類別：{MY_MEDICINES}（沒有劑量與品牌資訊，請勿臆測）。
7. 結尾固定加上一句：「若仍有疑問，請詢問醫師或藥師。」"""

HOW_TO_ASK = (
    "🤖 AI 藥師小幫手\n\n"
    "請在「問AI藥師」後面直接打你的用藥問題，例如：\n"
    "• 問AI藥師 降血壓藥可以飯前吃嗎？\n"
    "• 問AI藥師 忘記吃藥怎麼辦？\n\n"
    "⚠️ AI 回答僅供衛教參考，不能取代醫師或藥師。"
)


def _get_api_key():
    # 先找環境變數，再找 Colab 的 🔑 密鑰（GitHub 上跑測試時兩個都沒有）
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        from google.colab import userdata
        return userdata.get("GEMINI_API_KEY")
    except Exception:
        return None


API_KEY = _get_api_key()


def is_emergency(text):
    return any(k in text for k in EMERGENCY_KEYWORDS)


def ask_ai_pharmacist(question):
    if not API_KEY:
        return "AI 藥師目前沒有開啟，請直接詢問藥師。"
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=API_KEY)
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=AI_SYSTEM_PROMPT,
                max_output_tokens=600,
                temperature=0.3,
            ),
        )
        answer = (resp.text or "").strip()
        if not answer:
            return "這個問題我暫時無法回答，建議直接詢問醫師或藥師。"
        return answer[:1500]
    except Exception as e:
        print("[Gemini error]", str(e))
        return "AI 藥師目前忙線中，請稍後再試，或直接詢問藥師。"


def handle(text, user_id):
    # 把關鍵字拿掉，剩下的就是問題
    question = text
    for k in KEYWORDS:
        question = question.replace(k, "")
    question = question.strip(" ：:，,")

    if question == "":
        return [TextMessage(text=HOW_TO_ASK)]

    if len(question) > MAX_QUESTION_LEN:
        answer = f"問題太長了（{len(question)} 字），請縮短到 {MAX_QUESTION_LEN} 字以內。"
    elif is_emergency(question):
        answer = ("🚨 這可能是緊急狀況！\n"
                  "請立刻撥打 119，或請身旁的人協助送醫。\n"
                  "請不要等待 AI 回覆。")
    else:
        answer = "🤖 " + ask_ai_pharmacist(question)

    return [TextMessage(text=answer)]
