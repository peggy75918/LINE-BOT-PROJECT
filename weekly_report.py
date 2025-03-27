# weekly_report.py
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import supabase

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = supabase.create_client(supabase_url, supabase_key)

def format_date(d): return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    today = datetime.utcnow() + timedelta(hours=8)
    start_of_week = today - timedelta(days=today.weekday())  # 週一
    end_of_week = start_of_week + timedelta(days=6)

    # 找最新專案
    project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
    if not project_res.data:
        return "⚠️ 本群組尚未建立任何專案"

    project_id = project_res.data[0]["id"]

    # 查所有成員
    member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
    members = {m["user_id"]: {"name": m["real_name"], "total": 0, "completed": 0, "weekly_done": 0} for m in member_res.data}

    # 查所有任務
    task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
    task_map = {t["id"]: t["assignee_id"] for t in task_res.data if t["assignee_id"] in members}

    # 查所有 checklist
    checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute()
    for c in checklist_res.data:
        uid = task_map[c["task_id"]]
        members[uid]["total"] += 1
        if c["is_done"]:
            members[uid]["completed"] += 1
            if c["completed_at"]:
                complete_time = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                if start_of_week <= complete_time <= end_of_week:
                    members[uid]["weekly_done"] += 1

    # 組合訊息
    header = f"🧾 本週任務週報（{format_date(start_of_week)} - {format_date(end_of_week)}）\n"
    lines = []
    for uid, data in members.items():
        lines.append(f"{data['name']}：{data['completed']} / {data['total']} ✅（本週完成 {data['weekly_done']}）")

    return header + "\n".join(lines)

