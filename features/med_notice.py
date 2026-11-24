"""
用藥注意事項小幫手（第 8 步）
領完藥之後，用 Gemini 把藥的注意事項講成長輩聽得懂的話。

用法（長輩打字不方便，所以盡量用按鈕）：
  打「注意」          → 跳出藥物按鈕，點一下就好
  打「注意 普拿疼」    → 直接解釋普拿疼
"""
import os

from linebot.v3.messaging import MessageAction, QuickReply, QuickReplyItem, TextMessage

NAME = "用藥注意事項"
AUTHOR = "@114150"
KEYWORDS = ["注意", "用藥注意"]

# 還沒串藥物資料前，先用組上「我的藥物」的那三種
MY_MEDICINES = ["高血壓藥", "高血脂藥", "糖尿病藥"]

# 給 AI 看的說明書（每種藥都用同一套）
RULES = """你是社宅長輩的用藥衛教小幫手，請用繁體中文回答。
使用者會給你他領到的藥名（可能不只一種），請依照以下規則回覆：
1. 每種藥最多列出 3 點服藥注意事項，每點一句話、20 字左右
2. 用長輩聽得懂的口語，不要用專有名詞
3. 不要提供任何劑量數字，劑量請以藥袋為準
4. 不確定的內容不要寫，不可編造
5. 如果問到漏吃、補吃、加倍、停藥，不要給建議，只回覆：「這需要依照您的藥來判斷，請直接詢問藥師或醫師。」
6. 如果輸入不是藥名，請使用者確認藥袋上的藥名"""

# AI 沒辦法用的時候，至少給這段通用提醒
BACKUP_NOTICE = (
    "💡 用藥注意事項\n"
    "• 請按照藥袋上的時間服用\n"
    "• 不要自己增加或減少劑量\n"
    "• 不要自己停藥\n"
    "• 吃藥後很不舒服，請聯絡醫療人員"
)
ENDING = "\n\n以藥袋和藥師說明為準，有疑問請問藥師 🙏"


def medicine_buttons():
    # 每個藥一顆按鈕，點了會自動送出「注意事項 藥名」，長輩不用打字
    items = [
        QuickReplyItem(action=MessageAction(label=med, text=f"注意事項 {med}"))
        for med in MY_MEDICINES
    ]
    items.append(QuickReplyItem(action=MessageAction(label="全部的藥", text="注意事項 全部")))
    return QuickReply(items=items)


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


# 在載入功能時就先拿好金鑰，Bot 跑起來之後就不用再去 Colab 拿
API_KEY = _get_api_key()


def ask_gemini(drug_names):
    # 沒有金鑰就不問 AI，回 None 讓下面用通用提醒
    if not API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=drug_names,
            config=types.GenerateContentConfig(
                system_instruction=RULES,
                temperature=0.3,  # 醫療資訊要穩定，不要 AI 亂打
                max_output_tokens=800,
            ),
        )
        answer = (response.text or "").strip()
        return answer or None
    except Exception as e:
        print("[med_notice] Gemini 出錯：", repr(e))
        return None


def handle(text, user_id):
    # 把關鍵字拿掉，剩下的就是藥名（長的先拿掉，不然「注意事項」會剩下「事項」）
    drug = text
    for k in ["注意事項", "用藥注意", "注意"]:
        drug = drug.replace(k, "")
    drug = drug.strip(" ：:，,的")

    # 沒打藥名 → 跳出按鈕讓他點
    if drug == "":
        return [TextMessage(
            text="想看哪個藥要注意什麼？\n點下面的按鈕就可以了 👇",
            quick_reply=medicine_buttons(),
        )]

    if drug == "全部":
        drug = "、".join(MY_MEDICINES)

    answer = ask_gemini(drug)
    if answer:
        body = f"💊 {drug} 要注意：\n" + answer[:3000]
    else:
        body = BACKUP_NOTICE

    # 回答完也附上按鈕，方便接著看別的藥
    return [TextMessage(text=body + ENDING, quick_reply=medicine_buttons())]
