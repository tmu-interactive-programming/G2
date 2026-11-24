"""
用藥注意事項小幫手（第 8 步）
領完藥之後，用 Gemini 把藥的注意事項講成長輩聽得懂的話。

用法（長輩打字不方便，所以盡量用按鈕）：
  打「注意」          → 跳出藥物按鈕，點一下就好
  打「注意 普拿疼」    → 直接解釋普拿疼
"""
import __main__
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from linebot.v3.messaging import (
    FlexContainer,
    FlexMessage,
    MessageAction,
    QuickReply,
    QuickReplyItem,
    TextMessage,
)

NAME = "用藥注意事項"
AUTHOR = "@114150"
KEYWORDS = ["注意", "用藥注意"]

# 還沒串藥物資料前，先用組上「我的藥物」的那三種
MY_MEDICINES = ["高血壓藥", "高血脂藥", "糖尿病藥"]

# 卡片上每個藥的圖示和顏色（長輩看顏色比較好認）
MED_STYLE = {
    "高血壓藥": ("❤️", "#E05A47"),
    "高血脂藥": ("🧈", "#E89A2C"),
    "糖尿病藥": ("🍬", "#3B82C4"),
}

# 給 AI 看的說明書（每種藥都用同一套）
RULES = """你是社宅長輩的用藥衛教小幫手，請用繁體中文回答。
使用者會給你藥名或藥物類別（例如「高血壓藥」），可能不只一種，請依照以下規則回覆：
1. 每種藥用「【藥名】」當小標題，下面最多列 3 點注意事項，每點一句話、20 字左右
2. 如果是藥物類別，就給這一類藥共通的注意事項，不要反問使用者詳細藥名
3. 用長輩聽得懂的口語，不要用專有名詞，不要開場白
4. 不要提供任何劑量數字，劑量請以藥袋為準
5. 不確定的內容不要寫，不可編造
6. 如果問到漏吃、補吃、加倍、停藥，不要給建議，只回覆：「這需要依照您的藥來判斷，請直接詢問藥師或醫師。」
7. 只有完全不是藥（例如「皮卡丘」）時，才請使用者確認藥袋上的藥名"""

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
    # 回答下方的小按鈕，點了會自動送出「注意事項 藥名」，長輩不用打字
    items = [
        QuickReplyItem(action=MessageAction(label=med, text=f"注意事項 {med}"))
        for med in MY_MEDICINES
    ]
    items.append(QuickReplyItem(action=MessageAction(label="全部的藥", text="注意事項 全部")))
    return QuickReply(items=items)


def medicine_card():
    # 一張漂亮的選單卡片：每個藥一顆大大的彩色按鈕
    buttons = []
    for med in MY_MEDICINES:
        icon, color = MED_STYLE.get(med, ("💊", "#2E8B7A"))
        buttons.append({
            "type": "button",
            "style": "primary",
            "color": color,
            "height": "md",
            "action": {"type": "message", "label": f"{icon} {med}", "text": f"注意事項 {med}"},
        })
    buttons.append({
        "type": "button",
        "style": "secondary",
        "height": "md",
        "action": {"type": "message", "label": "📋 全部的藥一起看", "text": "注意事項 全部"},
    })

    card = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#2E8B7A",
            "paddingAll": "18px",
            "contents": [
                {"type": "text", "text": "💊 用藥注意事項", "weight": "bold", "size": "xl", "color": "#FFFFFF"},
                {"type": "text", "text": "AI 用白話說給您聽", "size": "sm", "color": "#D9F2EC", "margin": "sm"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": "想看哪個藥要注意什麼？\n點一下就好 👇", "wrap": True, "size": "md", "color": "#333333"},
            ] + buttons,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "⏳ 按下後 AI 大約 10～50 秒回覆\n看到「...」就是在想，不用再傳一次喔", "wrap": True, "size": "sm", "color": "#2E8B7A", "weight": "bold"},
                {"type": "text", "text": "其他的藥：打「注意 藥名」\n例如：注意 普拿疼", "wrap": True, "size": "xs", "color": "#888888", "margin": "md"},
            ],
        },
    }
    return FlexMessage(alt_text="用藥注意事項：請選擇藥物", contents=FlexContainer.from_dict(card))


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


AI_TIMEOUT_SECONDS = 50  # 盡量等 AI 想完；但 LINE 的回覆機會大約 1 分鐘就過期，所以最多等 50 秒
_pool = ThreadPoolExecutor(max_workers=4)


def show_thinking(user_id):
    # 在 LINE 聊天室顯示「...」思考動畫，讓長輩知道 AI 在想、不用再傳訊息
    # access token 從環境變數或 Colab 步驟 4 的 access_token 拿（只讀，不寫進程式）
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or getattr(__main__, "access_token", None)
    if not token or not str(user_id).startswith("U"):
        return
    try:
        from linebot.v3.messaging import (
            ApiClient,
            Configuration,
            MessagingApi,
            ShowLoadingAnimationRequest,
        )
        with ApiClient(Configuration(access_token=token)) as api_client:
            MessagingApi(api_client).show_loading_animation(
                ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60)
            )
    except Exception as e:
        print("[med_notice] 思考動畫沒顯示：", repr(e))


def ask_gemini_with_timeout(drug_names):
    # 讓 AI 在背景想，超過 50 秒就先放棄，回 "TIMEOUT"
    future = _pool.submit(ask_gemini, drug_names)
    try:
        return future.result(timeout=AI_TIMEOUT_SECONDS)
    except FutureTimeout:
        print("[med_notice] AI 超過", AI_TIMEOUT_SECONDS, "秒沒回，先給通用提醒")
        return "TIMEOUT"


# 測試時發現 Gemini 常常 503 塞車，所以準備備用模型：第一個塞車就換下一個
MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]


def ask_gemini(drug_names):
    # 沒有金鑰就不問 AI，回 None 讓下面用通用提醒
    if not API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        print("[med_notice] Gemini 連線失敗：", repr(e))
        return None

    busy = False
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=drug_names,
                config=types.GenerateContentConfig(
                    system_instruction=RULES,
                    temperature=0.3,  # 醫療資訊要穩定，不要 AI 亂打
                    max_output_tokens=800,
                ),
            )
            answer = (response.text or "").strip()
            if answer:
                print("[med_notice] 用", model, "回答成功")
                return answer
        except Exception as e:
            print("[med_notice]", model, "出錯，換下一個：", repr(e)[:120])
            if "503" in repr(e) or "429" in repr(e):
                busy = True
    return "BUSY" if busy else None


def handle(text, user_id):
    # 把關鍵字拿掉，剩下的就是藥名（長的先拿掉，不然「注意事項」會剩下「事項」）
    drug = text
    for k in ["注意事項", "用藥注意", "注意"]:
        drug = drug.replace(k, "")
    drug = drug.strip(" ：:，,的")

    # 沒打藥名 → 跳出彩色卡片讓他點
    if drug == "":
        return [medicine_card()]

    if drug == "全部":
        drug = "、".join(MY_MEDICINES)

    show_thinking(user_id)  # 先讓聊天室出現「...」，長輩就知道要等
    answer = ask_gemini_with_timeout(drug)
    if answer in ("TIMEOUT", "BUSY"):
        body = "⏳ AI 現在有點忙，請過一下再問一次喔\n\n先給您通用的提醒：\n" + BACKUP_NOTICE
    elif answer:
        body = f"💊 {drug} 要注意：\n" + answer[:3000]
    else:
        body = BACKUP_NOTICE

    # 回答完也附上按鈕，方便接著看別的藥
    return [TextMessage(text=body + ENDING, quick_reply=medicine_buttons())]
