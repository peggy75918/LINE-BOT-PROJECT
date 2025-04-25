from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest, 
    TextMessage, FlexMessage, FlexContainer
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import os
import re
import uuid  # ✅ 新增 UUID 產生功能
import supabase
import json
from dotenv import load_dotenv
from datetime import datetime

# 讀取 .env 環境變數
load_dotenv()

# 初始化 Flask
app = Flask(__name__)

# 設定 LINE API
configuration = Configuration(access_token=os.getenv('CHANNEL_ACCESS_TOKEN'))
line_handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

# 連接 Supabase
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
supabase_client = supabase.create_client(supabase_url, supabase_key)

# **使用字典來存放用戶的對話狀態**
user_state = {}

@app.route("/callback", methods=['POST'])
def callback():
    """處理來自 LINE 的 Webhook"""
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    print(f"📩 收到 LINE Webhook 請求: {body}")  # ✅ Debug log

    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ 簽名驗證失敗")
        abort(400)
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")  # ✅ 印出完整錯誤訊息
        import traceback
        traceback.print_exc()  # ✅ 印出錯誤詳細堆疊
        abort(500)

    return 'OK'

def handle_share_message(user_message, line_id, project_id):
    match = re.match(r"#分享\s+(\S+)\s+(\S+)\s+(https?://\S+)(?:\s+(.*))?", user_message)
    if not match:
        return "❗️格式錯誤，請使用：#分享 資源名稱 標籤 連結 描述（描述可省略）"

    title, tag, link, description = match.groups()
    description = description or ""

    try:
        supabase_client.table("shared_resources").insert({
            "id": str(uuid.uuid4()),
            "user_id": line_id,
            "project_id": project_id,
            "title": title,
            "tag": tag,
            "link": link,
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return f"✅ 資源「{title}」已成功分享！"
    except Exception as e:
        return f"❌ 儲存失敗：{str(e)}"

def push_debug_message(api, user_id_or_group_id, text):
    try:
        api.push_message(
            PushMessageRequest(
                to=user_id_or_group_id,
                messages=[TextMessage(text=f"🐞 Debug：{text}")]
            )
        )
    except Exception as e:
        print(f"⚠️ Debug 傳送失敗：{e}")

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """處理 LINE 訊息"""
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        user_message = event.message.text.strip()
        
        # **判斷訊息來自個人還是群組**
        user_id = event.source.user_id if hasattr(event.source, "user_id") else None
        group_id = event.source.group_id if hasattr(event.source, "group_id") else None

        # **處理「開始使用」訊息**
        print(f"📩 收到的訊息內容: {user_message}")  # 確認收到的訊息
        if user_message == "開始使用":
            # 讀取 JSON 檔案
            with open("card.json", "r", encoding="utf-8") as f:
                flex_json = json.load(f)

            # 轉換為 FlexContainer
            flex_content = FlexContainer.from_json(json.dumps(flex_json))

            # 建立 FlexMessage
            flex_message = FlexMessage(alt_text="計畫飄飄👻 開始使用說明", contents=flex_content)

            # 發送訊息
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
            )
            return

        # **處理「呼叫飄飄」訊息**
        if user_message == "呼叫飄飄":
            try:
                with open("piao.json", "r", encoding="utf-8") as f:
                    flex_json = json.load(f)

                flex_content = FlexContainer.from_json(json.dumps(flex_json))
                flex_message = FlexMessage(alt_text="呼叫飄飄👻", contents=flex_content)

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
                )
            except Exception as e:
                print(f"❌ 載入 piao.json 發生錯誤：{e}")
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="❌ 無法載入飄飄畫面，請稍後再試！")]
                    )
                )
            return


        if user_message == "本週結算":
            try:
                from weekly_report import generate_weekly_report
                
                # ⚙️ 呼叫週報產生函式（會回傳 JSON dict 或錯誤訊息）
                result = generate_weekly_report(group_id)
        
                # ✅ 若為錯誤訊息（字串）
                if isinstance(result, str):
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=result)]
                        )
                    )
                else:
                    # ✅ 否則為 JSON dict，需轉換為 FlexMessage
                    flex_msg = FlexMessage(
                        alt_text="📊 任務週報",
                        contents=FlexContainer.from_json(json.dumps(result))
                    )
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[flex_msg]
                        )
                    )
        
            except Exception as e:
                # 捕捉錯誤
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"❌ 發送週報時發生錯誤：{str(e)}")]
                    )
                )
            return

        if user_message == "生成專案報表":
            from project_summary_report import generate_project_summary

            # 先查 group 對應的 project_id（跟 weekly_report 做法一樣）
            project_res = supabase_client.table("projects").select("id") \
                .eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()

            if not project_res.data:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="⚠️ 找不到群組中的專案，請先建立一個專案")]
                    )
                )
                return

            project_id = project_res.data[0]["id"]
            result = generate_project_summary(project_id)

            # 回覆 Flex 報表
            if isinstance(result, str):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=result)]
                    )
                )
            else:
                flex_msg = FlexMessage(
                    alt_text="🗃️ 專案總結報表",
                    contents=FlexContainer.from_json(json.dumps(result))
                )
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_msg]
                    )
                )
                return

        # 分享資源
        if user_message.startswith("#分享"):
            try:
                project_res = supabase_client.table("projects").select("id") \
                    .eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
                if not project_res.data:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="⚠️ 找不到群組中的專案，請先建立一個專案")]
                        )
                    )
                    return
        
                project_id = project_res.data[0]["id"]
                result = handle_share_message(user_message, user_id, project_id)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=result)]
                    )
                )
                return
        
            except Exception as e:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"❌ 分享過程中發生錯誤：{str(e)}")]
                    )
                )
                return

        
        # **檢查使用者是否正在輸入「專案階段數量」**
        if user_id in user_state and user_state[user_id]["step"] == "waiting_for_stage_count":
            project_name = user_state[user_id]["project_name"]

            # **確保輸入是數字**
            if user_message.isdigit():
                stage_count = int(user_message)

                # **手動產生 UUID 作為 project_id**
                project_id = str(uuid.uuid4())

                # **儲存到 Supabase**
                try:
                    project_response = supabase_client.table("projects").insert({
                        "id": project_id,  # ✅ **手動設定 UUID**
                        "name": project_name,
                        "stage_count": stage_count,  # **存入階段數量**
                        "created_by": user_id,  # ✅ **存入 LINE 使用者 ID**
                        "group_id": group_id  # ✅ **存入群組 ID**
                    }).execute()

                    if project_response.data:
                        print(f"✅ 專案已建立，UUID: {project_id}")  # Debug log
                        reply_messages = [
                            TextMessage(text=f"✅ 專案『{project_name}』已建立，共{stage_count}個階段！\n成員可根據範例輸入學號姓名加入！"),
                            TextMessage(text="111219060／王曉明／加入專案")
                        ]
                    else:
                        reply_text = "⚠️ 無法建立專案，請稍後再試。"

                except Exception as e:
                    reply_text = f"❌ 建立專案失敗: {str(e)}"

                # **清除狀態**
                del user_state[user_id]

            else:
                reply_text = "⚠️ 請用阿拉伯數字輸入階段數量（此次課程請輸入4）："

            # **回覆用戶**
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=reply_messages
                )
            )
            return

        # **讓使用者加入當前群組的最新專案**
        if "／加入專案" in user_message:  # ✅ 確保訊息格式正確
            try:
                parts = user_message.split("／")
                if len(parts) != 3:
                    reply_text = "⚠️ 格式錯誤！請輸入【學號／姓名／加入專案】，例如：111234001／王曉明／加入專案"
                else:
                    student_id = parts[0].strip()
                    real_name = parts[1].strip()

                    # **查詢該群組的最新專案**
                    project_response = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()

                    if not project_response.data:
                        reply_text = "⚠️ 目前你的群組沒有任何專案，請先讓管理員建立專案！"
                    else:
                        project_id = project_response.data[0]["id"]  # ✅ 取得該群組最新專案 ID
                        
                        # **檢查這個使用者是否已經加入專案**
                        existing_member = supabase_client.table("project_members").select("*").eq("user_id", user_id).eq("project_id", project_id).execute()

                        if existing_member.data:
                            reply_text = "⚠️ 你已經加入此專案，無需重複加入！"
                        else:
                            # **讓使用者手動加入**
                            member_data = {
                                "project_id": project_id,
                                "user_id": user_id,
                                "student_id": student_id,  # ✅ 存入學號
                                "real_name": real_name  # ✅ 存入真實姓名
                            }
                            response = supabase_client.table("project_members").insert(member_data).execute()
                            reply_text = f"✅ 你已成功加入專案！\n學號：{student_id}\n姓名：{real_name}\n https://project-piaopiao-v1.vercel.app/"

            except Exception as e:
                reply_text = f"❌ 加入專案失敗: {str(e)}"

            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            return

        # **第一步：使用者輸入「建立專案：XXX」**
        if user_message.startswith("建立專案："):
            project_name = user_message.replace("建立專案：", "").strip()
            
            if not project_name:
                reply_text = "⚠️ 請輸入專案名稱，如 ➡️ 建立專案：我的新專案"
            else:
                # **記錄使用者狀態，等待輸入階段數量**
                user_state[user_id] = {"step": "waiting_for_stage_count", "project_name": project_name}
                
                reply_text = "📌 請輸入此專案的階段數量（此次課程請輸入4）："

        else:
            return  # **回覆原訊息**

        # **回覆用戶**
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

@line_handler.add(PostbackEvent)
def handle_postback(event):
    """處理 postback 點擊事件"""
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        data = event.postback.data
        user_id = event.source.user_id

        print(f"🟡 收到 Postback：{data}（來自 {user_id}）")

        if data == "explain_share":
            reply_text = "請根據「#分享 名稱 標籤 相關連結 描述（選填）」格式輸入想分享的資源或工具，如「#分享 Figma UI/UX https://www.figma.com/ 視覺設計工具」"
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )

@app.route("/send_project_summary", methods=["POST"])
def send_project_summary():
    from project_summary_report import generate_project_summary
    from linebot.v3.messaging import PushMessageRequest, FlexMessage, FlexContainer

    try:
        data = request.get_json()
        project_id = data.get("project_id")
        group_id = data.get("group_id")

        if not project_id or not group_id:
            return { "success": False, "message": "缺少 project_id 或 group_id" }, 400

        result = generate_project_summary(project_id)
        if isinstance(result, str):
            return { "success": False, "message": result }, 500

        flex_msg = FlexMessage(
            alt_text="🗃️ 專案總結報表",
            contents=FlexContainer.from_json(json.dumps(result))
        )

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(to=group_id, messages=[flex_msg])
            )

        return { "success": True }

    except Exception as e:
        print("❌ 報表推送失敗:", e)
        return { "success": False, "message": str(e) }, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))




