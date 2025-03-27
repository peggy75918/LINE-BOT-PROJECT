import os
import json
from datetime import datetime, timedelta
from supabase import create_client
from linebot.v3.messaging import (
    FlexMessage, FlexContainer, Configuration, ApiClient,
    MessagingApi, PushMessageRequest, TextMessage
)
from dotenv import load_dotenv

# Load .env
load_dotenv()

# LINE Config
LINE_GROUP_ID = "Cff5327a9fc9323dd8344c1a8789329d9"  # Replace with actual Group ID
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))

# Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

# Send debug log to group
def send_debug_message(line_bot_api, group_id, log_lines):
    debug_text = "🐞 除錯資訊：\n" + "\n".join(log_lines)
    chunks = [debug_text[i:i+1000] for i in range(0, len(debug_text), 1000)]
    for chunk in chunks:
        line_bot_api.push_message(
            PushMessageRequest(
                to=group_id,
                messages=[TextMessage(text=chunk)]
            )
        )

# Format date for display
def format_date(d):
    return d.strftime("%m/%d")

# Weekly report generator
def generate_weekly_report(group_id):
    log = []  # Collect debug logs

    try:
        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        log.append("📌 1️⃣ 查詢最新專案中...")
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return "⚠️ 本群組尚未建立任何專案"
        project_id = project_res.data[0]["id"]
        log.append(f"✅ 專案 ID: {project_id}")

        log.append("📌 2️⃣ 查詢專案成員...")
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        members = {m["user_id"]: {
            "name": m["real_name"], "total_tasks": 0, "completed_tasks": 0,
            "weekly_checklists": 0, "weekly_tasks": set()
        } for m in member_res.data}
        log.append(f"✅ 成員數量: {len(members)}")

        log.append("📌 3️⃣ 查詢任務...")
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {t["id"]: t["assignee_id"] for t in task_res.data if t["assignee_id"] in members}
        for assignee in task_map.values():
            members[assignee]["total_tasks"] += 1
        log.append(f"✅ 有效任務數: {len(task_map)}")

        log.append("📌 4️⃣ 查詢 checklist...")
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute()
        for c in checklist_res.data:
            uid = task_map.get(c["task_id"])
            if not uid:
                continue
            if c["is_done"]:
                members[uid]["completed_tasks"] += 1
                if c["completed_at"]:
                    try:
                        complete_time = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                        if start_of_week <= complete_time <= end_of_week:
                            members[uid]["weekly_checklists"] += 1
                            members[uid]["weekly_tasks"].add(c["task_id"])
                    except Exception as e:
                        log.append(f"⚠️ 時間解析錯誤: {str(e)}")

        log.append("📌 5️⃣ 載入 Flex 模板...")
        with open("weekly.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        log.append("📌 6️⃣ 套用成員資料...")
        member_blocks = []
        for m in members.values():
            member_blocks.extend([
                {"type": "text", "text": m["name"], "color": "#153448", "margin": "lg"},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{m['weekly_checklists']}項", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{len(m['weekly_tasks'])}項", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{m['completed_tasks']} / {m['total_tasks']}", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "separator", "margin": "lg"}
            ])

        # 插入成員統計內容
        template["body"]["contents"][3]["contents"] = member_blocks

        # 更新週期與截止日
        template["body"]["contents"][1]["text"] = f"{format_date(start_of_week)} - {format_date(end_of_week)}"
        template["body"]["contents"][6]["contents"][1]["text"] = today.strftime("%Y/%m/%d")

        flex_container = FlexContainer.from_json(json.dumps(template))
        flex_message = FlexMessage(alt_text="📊 任務週報", contents=flex_container)

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(PushMessageRequest(
                to=group_id,
                messages=[flex_message]
            ))

    except Exception as e:
        log.append("❌ 發送報表失敗")
        log.append(str(e))
        import traceback
        log.append(traceback.format_exc())
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            send_debug_message(line_bot_api, group_id, log)

