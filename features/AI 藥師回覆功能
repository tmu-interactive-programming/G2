# @title 正式 LINE BOT 伺服器：請至 LINE Developers 設定 Webhook 網址

!pip install -q line-bot-sdk google-genai

from flask import Flask, request
import os
import re
import gspread
from datetime import datetime
import numpy as np
from PIL import Image
from io import BytesIO

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage,
    LocationMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent
)

# 匯入 Gemini 相關套件與初始化 client
from google import genai
from google.genai import types
from google.colab import userdata

client = genai.Client(api_key=userdata.get("GEMINI_API_KEY"))

app = Flask(__name__)
port = "5000"


# =========================
# Google Sheet 管理端資料庫
# =========================
SPREADSHEET_NAME = "六張犁社宅用藥管理"

def init_google_sheet():
    global spreadsheet, user_sheet, pickup_request_sheet, pickup_history_sheet
    try:
        spreadsheet = gc.open(SPREADSHEET_NAME)
        user_sheet = spreadsheet.worksheet("住戶資料")
        pickup_request_sheet = spreadsheet.worksheet("領藥需求")
        pickup_history_sheet = spreadsheet.worksheet("領藥紀錄")
        print("Google Sheet 連線成功")
    except Exception as e:
        spreadsheet = None
        user_sheet = None
        pickup_request_sheet = None
        pickup_history_sheet = None
        print("Google Sheet 尚未連線：", str(e))

def ensure_headers():
    try:
        if user_sheet and not user_sheet.get_all_values():
            user_sheet.append_row([
                "LINE User ID", "姓名", "生日", "身分識別",
                "同意服務", "健保卡處方箋集中保管", "建立時間"
            ])
        if pickup_request_sheet and not pickup_request_sheet.get_all_values():
            pickup_request_sheet.append_row([
                "時間", "LINE User ID", "姓名", "狀態", "預計領藥日", "備註"
            ])
        if pickup_history_sheet and not pickup_history_sheet.get_all_values():
            pickup_history_sheet.append_row([
                "日期", "LINE User ID", "姓名", "領藥方式", "結果", "藥物確認"
            ])
    except Exception as e:
        print("建立 Google Sheet 標題列失敗：", str(e))

def save_user_profile_to_sheet(user_id, profile):
    if not user_sheet:
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_sheet.append_row([
            user_id,
            profile.get("name", ""),
            profile.get("birthday", ""),
            profile.get("masked_twid", ""),
            "YES" if profile.get("service_enabled") else "NO",
            "YES" if profile.get("custody_consent") else "NO",
            now
        ])
        return True
    except Exception as e:
        print("寫入住戶資料失敗：", str(e))
        return False

def save_pickup_request_to_sheet(user_id, name, status, expected_date="", note=""):
    if not pickup_request_sheet:
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pickup_request_sheet.append_row([
            now, user_id, name, status, expected_date, note
        ])
        return True
    except Exception as e:
        print("寫入領藥需求失敗：", str(e))
        return False

def save_pickup_history_to_sheet(user_id, name, method="未指定", result="已完成", medicine_check=""):
    if not pickup_history_sheet:
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pickup_history_sheet.append_row([
            now, user_id, name, method, result, medicine_check
        ])
        return True
    except Exception as e:
        print("寫入領藥紀錄失敗：", str(e))
        return False

try:
    init_google_sheet()
    ensure_headers()
except Exception as e:
    print("Sheet 初始化跳過:", e)


# =========================
# 使用者註冊 / 服務啟用狀態
# =========================
user_profiles = {}
user_states = {}

def service_intro_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=MessageAction(
                    label="了解並繼續",
                    text="了解服務內容"
                )
            ),
            QuickReplyItem(                action=MessageAction(
                    label="暫不使用",
                    text="暫不使用服務"
                )
            )
        ]
    )

def custody_consent_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=MessageAction(
                    label="我同意",
                    text="同意集中保管"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="不同意",
                    text="不同意集中保管"
                )
            )
        ]
    )

def onboarding_intro_message():
    return (
        "🏠 六張犁社宅代領藥物服務\n\n"
        "【服務內容】\n"
        "• 協助符合需求的住戶進行領藥協調\n"
        "• 提供領藥提醒、藥物確認與領藥紀錄\n"
        "• 社宅管理端協助集中處理代領需求\n\n"
        "【使用者規範】\n"
        "• 請提供正確的個人與處方相關資料\n"
        "• 藥物仍應依醫師處方與藥師指示使用\n"
        "• 如發現藥物與預期不符，請勿自行服用有疑問的藥物，並等待藥師確認\n"
        "• 個人資料僅應用於本服務必要範圍\n\n"
        "若您了解以上內容，請點選「了解並繼續」。"
    )

def mask_twid(twid):
    if not twid:
        return ""
    if len(twid) <= 4:
        return "*" * len(twid)
    return twid[:2] + "*" * (len(twid) - 4) + twid[-2:]

# =========================
# AI 藥師小幫手（Gemini）
# =========================
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

def is_emergency(text):
    return any(k in text for k in EMERGENCY_KEYWORDS)

def ask_ai_pharmacist(question):
    try:
        resp = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=AI_SYSTEM_PROMPT,
                max_output_tokens=600,
                temperature=0.3,
            ),
        )
        answer = (resp.text or "").strip()
        if not answer:
            return "這個問題我暫時無法回答，建議直接詢問醫師 or 藥師。"
        return answer[:1500]
    except Exception as e:
        print("[Gemini error]", str(e))
        return "AI 藥師目前忙線中，請稍後再試，或直接詢問藥師。"

def ai_quick_reply():
    return QuickReply(items=[
        QuickReplyItem(action=MessageAction(label="回主選單", text="選單"))
    ])


# =========================
# 共用：主選單 Quick Reply
# =========================
def main_menu_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=MessageAction(
                    label="我的藥物",
                    text="我的藥物"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="下次領藥",
                    text="下次領藥"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="我要協助",
                    text="我要協助"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="領藥紀錄",
                    text="領藥紀錄"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="問AI藥師",
                    text="問AI藥師"
                )
            )
        ]
    )


# =========================
# for 我要協助
# =========================
def help_menu_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=MessageAction(
                    label="我可以自己領",
                    text="我可以自己領"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="這次需要代領",
                    text="這次需要代領"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="晚點提醒我",
                    text="晚點提醒我"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="近期長期不便",
                    text="近期長期不便"
                )
            )
        ]
    )

# =========================
# for 確認藥物 Quick Reply
# =========================
def confirm_medicine_quick_reply():
    return QuickReply(
        items=[
            QuickReplyItem(
                action=MessageAction(
                    label="正確",
                    text="藥物正確"
                )
            ),
            QuickReplyItem(
                action=MessageAction(
                    label="錯誤",
                    text="藥物錯誤"
                )
            )
        ]
    )

@app.route("/", methods=["POST"])
def linebot():
    body = ""
    try:
        api_client = ApiClient(configuration)
        line_bot_api = MessagingApi(api_client)
        parser = WebhookParser(secret)

        signature = request.headers["X-Line-Signature"]
        body = request.get_data(as_text=True)

        try:
            events = parser.parse(body, signature)
        except InvalidSignatureError:
            return "Invalid signature", 400

        print("received events =", events)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue

            # =====================================
            # 收到文字訊息
            # =====================================
            if isinstance(event.message, TextMessageContent):
                received_text = event.message.text.strip()
                user_id = event.source.user_id

                print("RECEIVE TEXT:", received_text)
                print("USER ID:", user_id)

                reply_msg = []

                profile = user_profiles.get(user_id, {})
                state = user_states.get(user_id)

                # 讓使用者在提問模式下按其他選單時能正常跳出：
                MENU_COMMANDS = [
                    "我的藥物", "下次領藥", "我要協助", "領藥紀錄", "問AI藥師",
                    "選單", "首頁", "開始", "menu", "Menu",
                    "我可以自己領", "這次需要代領", "晚點提醒我", "近期長期不便",
                    "已領藥", "確認藥物", "藥物正確", "藥物錯誤"
                ]
                if state == "WAITING_AI_QUESTION" and received_text in MENU_COMMANDS:
                    user_states[user_id] = None
                    state = None

                # ---------------------------------
                # Step 1：服務內容與使用者規範
                # ---------------------------------
                if received_text in ["開始", "註冊", "啟用服務"] and not profile.get("service_enabled"):
                    user_states[user_id] = "WAITING_SERVICE_ACK"
                    reply_msg.append(
                        TextMessage(
                            text=onboarding_intro_message(),
                            quick_reply=service_intro_quick_reply()
                        )
                    )

                # ---------------------------------
                # 使用者閱讀完服務說明
                # ---------------------------------
                elif received_text == "了解服務內容":
                    user_states[user_id] = "WAITING_CUSTODY_CONSENT"
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "🔐 健保卡與處方箋保管同意\n\n"
                                "為進行代領藥物服務，需詢問您是否願意讓"
                                "「社宅管理人員」於服務必要期間集中保管您的健保卡與處方箋。\n\n"
                                "請確認您了解：\n"
                                "• 僅限代領服務必要用途使用\n"
                                "• 應由授權人員保管及處理\n"
                                "• 您可以選擇不同意，並停止啟用本服務\n\n"
                                "請選擇是否同意。"
                            ),
                            quick_reply=custody_consent_quick_reply()
                        )
                    )

                # ---------------------------------
                # Step 2：同意集中保管
                # ---------------------------------
                elif received_text == "同意集中保管":
                    user_profiles[user_id] = {
                        "custody_consent": True,
                        "service_enabled": False
                    }
                    user_states[user_id] = "WAITING_NAME"
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "✅ 已記錄您的同意。\n\n"
                                "接下來建立個人檔案。\n"
                                "請輸入您的「姓名」。"
                            )
                        )
                    )

                elif received_text in ["不同意集中保管", "暫不使用服務"]:
                    user_profiles[user_id] = {
                        "custody_consent": False,
                        "service_enabled": False
                    }
                    user_states[user_id] = None
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "好的，本次不啟用代領服務。\n\n"
                                "您仍可之後輸入「開始」，重新閱讀服務內容並決定是否啟用。"
                            )
                        )
                    )

                # ---------------------------------
                # Step 3-1：輸入姓名
                # ---------------------------------
                elif state == "WAITING_NAME":
                    name = received_text.strip()
                    if len(name) < 2:
                        reply_msg.append(
                            TextMessage(text="姓名格式似乎不完整，請重新輸入您的姓名。")
                        )
                    else:
                        user_profiles.setdefault(user_id, {})["name"] = name
                        user_states[user_id] = "WAITING_BIRTHDAY"
                        reply_msg.append(
                            TextMessage(
                                text=(
                                    f"已記錄姓名：{name}\n\n"
                                    "請輸入您的生日，格式為：YYYY/MM/DD\n"
                                    "例如：1950/05/20"
                                )
                            )
                        )

                # ---------------------------------
                # Step 3-2：輸入生日
                # ---------------------------------
                elif state == "WAITING_BIRTHDAY":
                    birthday = received_text.strip()
                    if not re.fullmatch(r"	*\d{4}/\d{2}/\d{2}	*", birthday):
                        # 簡單的正則檢測
                        match = re.search(r"\d{4}/\d{2}/\d{2}", birthday)
                        if match:
                            birthday = match.group(0)
                        else:
                            birthday = None

                    if not birthday:
                        reply_msg.append(
                            TextMessage(
                                text=(
                                    "生日格式不正確。\n"
                                    "請使用 YYYY/MM/DD 格式，例如：1950/05/20"
                                )
                            )
                        )
                    else:
                        user_profiles.setdefault(user_id, {})["birthday"] = birthday
                        user_states[user_id] = "WAITING_TWID"
                        reply_msg.append(
                            TextMessage(
                                text=(
                                    "已記錄生日。\n\n"
                                    "請輸入您的身分證字號。\n"
                                    "例如：A123456789"
                                )
                            )
                        )

                # ---------------------------------
                # Step 3-3：輸入身分證字號
                # ---------------------------------
                elif state == "WAITING_TWID":
                    twid = received_text.strip().upper()
                    if not re.fullmatch(r"[A-Z][12]\d{8}", twid):
                        reply_msg.append(
                            TextMessage(
                                text=(
                                    "身分證字號格式不正確，請重新輸入。\n"
                                    "格式範例：A123456789"
                                )
                            )
                        )
                    else:
                        user_profiles.setdefault(user_id, {})["twid"] = twid
                        user_profiles[user_id]["service_enabled"] = True
                        user_profiles[user_id]["masked_twid"] = mask_twid(twid)
                        user_states[user_id] = None

                        sheet_saved = save_user_profile_to_sheet(
                            user_id,
                            user_profiles[user_id]
                        )

                        name = user_profiles[user_id].get("name", "")
                        birthday = user_profiles[user_id].get("birthday", "")

                        reply_msg.append(
                            TextMessage(
                                text=(
                                    "🎉 個人檔案建立完成，代領服務已啟用！\n\n"
                                    f"姓名：{name}\n"
                                    f"生日：{birthday}\n"
                                    f"身分證：{mask_twid(twid)}\n"
                                    "健保卡／處方箋集中保管：已同意\n"
                                    + ("管理端資料：已同步至 Google Sheet\n\n" if sheet_saved else "管理端資料：目前未同步，請通知管理者\n\n")
                                    + "現在可以使用下方功能。"
                                ),
                                quick_reply=main_menu_quick_reply()
                            ) 
                        )

                # ---------------------------------
                # 已完成註冊：首頁 / 選單
                # ---------------------------------
                elif received_text in ["開始", "首頁", "選單", "menu", "Menu"]:
                    if not profile.get("service_enabled"):
                        user_states[user_id] = "WAITING_SERVICE_ACK"
                        reply_msg.append(
                            TextMessage(
                                text=onboarding_intro_message(),
                                quick_reply=service_intro_quick_reply()
                            )
                        )
                    else:
                        reply_msg.append(
                            TextMessage(
                                text=(
                                    "歡迎使用「六張犁社宅用藥小幫手」💊\n\n"
                                    "我可以幫您：\n"
                                    "• 查看藥物\n"
                                    "• 提醒下次領藥\n"
                                    "• 提出領藥協助\n"
                                    "• 查看領藥紀錄\n\n"
                                    "請選擇您想使用的功能："
                                ),
                                quick_reply=main_menu_quick_reply()
                            )
                        )

                # ---------------------------------
                # 未啟用服務者限制功能
                # ---------------------------------
                elif received_text in ["我的藥物", "下次領藥", "我要協助", "領藥紀錄", "問AI藥師"] and not profile.get("service_enabled"):
                    user_states[user_id] = "WAITING_SERVICE_ACK"
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "您尚未完成代領服務啟用。\n\n"
                                "請先閱讀服務內容並完成同意與個人資料建立。"
                            ),
                            quick_reply=service_intro_quick_reply()
                        )
                    )

                # ---------------------------------
                # 我的藥物
                # ---------------------------------
                elif received_text == "我的藥物":
                    medicine_menu = QuickReply(
                        items=[
                            QuickReplyItem(
                                action=MessageAction(
                                    label="確認藥物",
                                    text="確認藥物"
                                )
                            ),
                            QuickReplyItem(
                                action=MessageAction(
                                    label="回主選單",
                                    text="選單"
                                )
                            )
                        ]
                    )
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "💊 我的藥物\n\n"
                                "目前藥物資料：\n"
                                "1. 高血壓藥：剩餘 12 天\n"
                                "2. 高血脂藥：剩餘 12 天\n"
                                "3. 糖尿病藥：剩餘 7 天\n\n"
                                "請確認您目前收到的藥物，"
                                "是否與上述資料相符。"
                            ),
                            quick_reply=medicine_menu
                        )
                    )

                # ---------------------------------
                # 下次領藥
                # ---------------------------------
                elif received_text == "下次領藥":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "🟡 下次領藥狀態：準備\n\n"
                                "預計可領藥日期：10/28\n"
                                "目前剩餘藥量：約 7 天\n\n"
                                "您的藥物即將需要補充，"
                                "請確認近期是否方便自行外出領藥。"
                            ),
                            quick_reply=help_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 我要協助
                # ---------------------------------
                elif received_text == "我要協助":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "請選擇您目前需要的協助：\n\n"
                                "① 我可以自己領\n"
                                "② 這次需要代領\n"
                                "③ 晚點提醒我\n"
                                "④ 近期長期不方便外出"
                            ),
                            quick_reply=help_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 自己領
                # ---------------------------------
                elif received_text == "我可以自己領":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "好的 👍\n"
                                "這次將標記為「自行領藥」。\n\n"
                                "領藥完成後，可以再輸入：\n"
                                "「已領藥」"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 需要代領
                # ---------------------------------
                elif received_text == "這次需要代領":
                    name = user_profiles.get(user_id, {}).get("name", "未知住戶")
                    save_pickup_request_to_sheet(
                        user_id,
                        name,
                        "需要代領",
                        "10/28",
                        ""
                    )
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "✅ 已收到您的代領需求。\n\n"
                                "目前狀態：等待安排\n"
                                "預計可領藥日期：10/28\n\n"
                                "管理端確認後，"
                                "系統會再通知您後續領取方式。"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 晚點提醒
                # ---------------------------------
                elif received_text == "晚點提醒我":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "好的，我先幫您標記為「稍後確認」。\n\n"
                                "若有需要修改狀態，請重新輸入：\n"
                                "「下次領藥」"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 長期不便
                # ---------------------------------
                elif received_text == "近期長期不便":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "已記錄您近期較不方便外出。\n\n"
                                "之後可由管理端進一步協助評估：\n"
                                "• 固定代領服務\n"
                                "• 家庭藥師\n"
                                "• 長照相關資源\n"
                                "• 其他社區協助"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 領藥紀錄
                # ---------------------------------
                elif received_text == "領藥紀錄":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "📋 最近領藥紀錄\n\n"
                                "9/28　已完成\n"
                                "8/29　已完成\n"
                                "7/30　已完成\n\n"
                                "下次預計可領藥：10/28"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 已完成領藥
                # ---------------------------------
                elif received_text == "已領藥":
                    name = user_profiles.get(user_id, {}).get("name", "未知住戶")
                    save_pickup_history_to_sheet(
                        user_id,
                        name,
                        "社宅協助／自行領取",
                        "已完成",
                        ""
                    )
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "✅ 已完成本次領藥紀錄！\n\n"
                                "系統將重新計算下一次領藥日期與剩餘藥量。\n\n"
                                "目前狀態：🟢 藥量充足"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 確認藥物
                # ---------------------------------
                elif received_text == "確認藥物":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "🔍 請確認您目前收到的藥物\n\n"
                                "請確認以下項目：\n"
                                "• 藥袋上的姓名是否正確\n"
                                "• 藥物名稱是否正確\n"
                                "• 藥品數量是否正確\n"
                                "• 藥物外觀是否與平常相符\n\n"
                                "確認完成後，請選擇「正確」或「錯誤」。"
                            ),
                            quick_reply=confirm_medicine_quick_reply()
                        )
                    )

                # ---------------------------------
                # 藥物正確
                # ---------------------------------
                elif received_text == "藥物正確":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "✅ 藥物確認完成\n\n"
                                "請依照醫師處方及藥袋上的指示服用。\n\n"
                                "💡 用藥注意事項\n"
                                "• 請按照指定時間與劑量服用\n"
                                "• 不要自行增加或減少劑量\n"
                                "• 不要自行停藥\n"
                                "• 若服藥後出現明顯不適，請聯絡醫療人員\n"
                                "• 若對藥物有疑問，請詢問醫師或藥師"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 藥物錯誤
                # ---------------------------------
                elif received_text == "藥物錯誤":
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "⚠️ 發現藥物可能有誤\n\n"
                                "請先不要服用這次有疑問的藥物。\n\n"
                                "請保留藥袋與藥物，"
                                "並等候藥師確認與回覆。\n\n"
                                "若您不確定是哪一項藥物有問題，"
                                "請不要自行猜測或更換藥物。"
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # ---------------------------------
                # 問 AI 藥師：進入提問模式
                # ---------------------------------
                elif received_text == "問AI藥師":
                    user_states[user_id] = "WAITING_AI_QUESTION"
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "🤖 AI 藥師小幫手\n\n"
                                "請直接輸入您的用藥問題，例如：\n"
                                "• 降血壓藥可以飯前吃嗎？\n"
                                "• 忘記吃藥怎麼辦？\n\n"
                                "⚠️ AI 回答僅供衛教參考，不能取代醫師或藥師。\n"
                                "要離開請點「回主選單」。"
                            ),
                            quick_reply=ai_quick_reply()
                        )
                    )

                # ---------------------------------
                # 問 AI 藥師：處理問題
                # ---------------------------------
                elif state == "WAITING_AI_QUESTION":
                    if len(received_text) > MAX_QUESTION_LEN:
                        answer = f"問題太長了（{len(received_text)} 字），請縮短到 {MAX_QUESTION_LEN} 字以內。"
                    elif is_emergency(received_text):
                        answer = ("🚨 這可能是緊急狀況！\n"
                                  "請立刻撥打 119，或請身旁的人協助送醫。\n"
                                  "請不要等待 AI 回覆。")
                    else:
                        answer = "🤖 " + ask_ai_pharmacist(received_text)

                    reply_msg.append(
                        TextMessage(text=answer, quick_reply=ai_quick_reply())
                    )

                # ---------------------------------
                # 預設回覆
                # ---------------------------------
                else:
                    reply_msg.append(
                        TextMessage(
                            text=(
                                "我目前主要提供用藥與領藥相關功能。\n"
                                "請從下方選單選擇："
                            ),
                            quick_reply=main_menu_quick_reply()
                        )
                    )

                # 執行回覆
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=reply_msg
                    )
                )

            # =====================================
            # 收到圖片訊息
            # =====================================
            elif isinstance(event.message, ImageMessageContent):
                api_instance = MessagingApiBlob(api_client)
                message_content = api_instance.get_message_content(
                    event.message.id
                )

                image_arr = np.asarray(
                    Image.open(BytesIO(message_content))
                )

                folder = "photos"
                os.makedirs(folder, exist_ok=True)

                # 修正路徑開頭不可有空格
                image_path = f"{folder}/{event.message.id}.png"

                with open(image_path, "wb") as f:
                    f.write(message_content)

                image_url = (
                    f"{public_url[0]}/{folder}/{event.message.id}.png"
                )

                print("RECEIVE IMG:", image_url)

                reply_msg = [
                    TextMessage(
                        text="已收到您的照片。"
                    )
                ]

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=reply_msg
                    )
                )

            # =====================================
            # 其他格式
            # =====================================
            else:
                reply_msg = [
                    TextMessage(
                        text="目前請使用文字或選單功能操作。"
                    )
                ]

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=reply_msg
                    )
                )

    except Exception as e:
        print("[error]", body)
        print("[error]", str(e))

    return "OK"


if __name__ == '__main__':
    app.run(port=port)
