import os
from datetime import datetime, timedelta
from linebot.v3 import Configuration, ApiClient
from linebot.v3.messaging import MessagingApi, PushMessageRequest, TextMessage
import supabase
from dotenv import load_dotenv

load_dotenv()

# LINE 設定
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID", "Cff5327a9fc9323dd8344c1a8789329d9")
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))

# Supabase 設定
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = supabase.create_client(supabase_url, supabase_key)

def format_date(d):
    return d.strftime("%m/%d")

def handler(request):
    try:
        # 1️⃣ 台灣時間（週一～週日）
        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 2️⃣ 取得最新專案
        project_res = supabase_client.table("projects")\
            .select("id")\
            .eq("group_id", LINE_GROUP_ID)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        if not project_res.data:
            return {"statusCode": 200, "body": "⚠️ 尚未建立任何專案"}

        project_id = project_res.data[0]["id"]

        # 3️⃣ 取得成員清單
        member_res = supabase_client.table("project_members")\
            .select("user_id, real_name")\
            .eq("project_id", project_id)\
            .execute()

        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "total": 0,
                "completed": 0,
                "weekly_done": 0
            } for m in member_res.data
        }

        # 4️⃣ 任務與 checklist
        task_res = supabase_client.table("tasks")\
            .select("id, assignee_id")\
            .eq("project_id", project_id)\
            .execute()

        task_map = {t["id"]: t["assignee_id"] for t in task_res.data if t["assignee_id"] in members}

        checklist_res = supabase_client.table("task_checklists")\
            .select("task_id, is_done, completed_at")\
            .in_("task_id", list(task_map.keys()))\
            .execute()

        for c in checklist_res.data:
            uid = task_map[c["task_id"]]
            members[uid]["total"] += 1
            if c["is_done"]:
                members[uid]["completed"] += 1
                if c["completed_at"]:
                    complete_time = datetime.fromisoformat(
                        c["completed_at"].replace("Z", "+00:00")
                    ) + timedelta(hours=8)
                    if start_of_week <= complete_time <= end_of_week:
                        members[uid]["weekly_done"] += 1

        # 5️⃣ 組合訊息
        header = f"🧾 本週任務週報（{format_date(start_of_week)} - {format_date(end_of_week)}）\n"
        lines = []
        for data in members.values():
            lines.append(
                f"{data['name']}：{data['completed']} / {data['total']} ✅（本週完成 {data['weekly_done']}）"
            )
        report = header + "\n".join(lines)

        # 6️⃣ 發送 LINE
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=LINE_GROUP_ID,
                    messages=[TextMessage(text=report)]
                )
            )

        return {"statusCode": 200, "body": "✅ 週報已發送"}
    except Exception as e:
        print("❌ 發送週報時錯誤：", e)
        return {"statusCode": 500, "body": "❌ 發送週報失敗"}


