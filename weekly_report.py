import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import supabase

# 載入 .env
load_dotenv()

# Supabase 設定
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = supabase.create_client(supabase_url, supabase_key)

# 將 UTC 時間轉為台灣時間（+8）
def taiwan_time(dt):
    return dt + timedelta(hours=8)

# 時間區段：本週（一～日）
today = taiwan_time(datetime.utcnow())
start_of_week = today - timedelta(days=today.weekday())  # 本週一
end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

def format_date(d): return d.strftime("%m/%d")

async def generate_weekly_report(group_id):
    # 1️⃣ 找出此群組的最新專案
    project_res = supabase_client.table("projects") \
        .select("id") \
        .eq("group_id", group_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if not project_res.data:
        return "⚠️ 本群組尚未建立任何專案"

    project_id = project_res.data[0]["id"]

    # 2️⃣ 取得該專案的所有成員
    member_res = supabase_client.table("project_members") \
        .select("user_id, real_name") \
        .eq("project_id", project_id) \
        .execute()

    members = {
        m["user_id"]: {
            "name": m["real_name"],
            "total": 0,
            "completed": 0,
            "weekly_done": 0
        }
        for m in member_res.data
    }

    # 3️⃣ 查詢所有任務，建立任務與負責人對照
    task_res = supabase_client.table("tasks") \
        .select("id, assignee_id") \
        .eq("project_id", project_id) \
        .execute()

    task_map = {
        t["id"]: t["assignee_id"]
        for t in task_res.data
        if t["assignee_id"] in members
    }

    # 4️⃣ 查詢所有 checklist 並累加統計
    checklist_res = supabase_client.table("task_checklists") \
        .select("task_id, is_done, completed_at") \
        .in_("task_id", list(task_map.keys())) \
        .execute()

    for c in checklist_res.data:
        uid = task_map[c["task_id"]]
        members[uid]["total"] += 1
        if c["is_done"]:
            members[uid]["completed"] += 1
            if c["completed_at"]:
                completed_time = taiwan_time(
                    datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00"))
                )
                if start_of_week <= completed_time <= end_of_week:
                    members[uid]["weekly_done"] += 1

    # 5️⃣ 組合文字訊息
    header = f"📋 本週任務結算報告\n（{format_date(start_of_week)} - {format_date(end_of_week)}）\n"
    body = "\n".join([
        f"{m['name']}：{m['completed']} / {m['total']} ✅（本週完成 {m['weekly_done']}）"
        for m in members.values()
    ])

    return header + body
