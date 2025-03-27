import os
import json
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def format_date(d):
    return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    try:
        # 1️⃣ 查詢專案
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return "⚠️ 本群組尚未建立任何專案"

        project_id = project_res.data[0]["id"]

        # 2️⃣ 查詢成員
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "checklist_weekly": 0,
                "task_total": 0,
                "task_completed": 0,
                "task_weekly": 0
            } for m in member_res.data
        }

        # 3️⃣ 查詢任務
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        task_ids = list(task_map.keys())

        # 4️⃣ 查詢 checklist
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", task_ids).execute()

        # ⏰ 時間區段
        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 5️⃣ 整理 checklist
        task_checklists = {}
        for c in checklist_res.data:
            task_checklists.setdefault(c["task_id"], []).append(c)

        for task_id, checklists in task_checklists.items():
            uid = task_map[task_id]
            # 計算 checklist 本週完成
            for c in checklists:
                if c["is_done"] and c["completed_at"]:
                    complete_time = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                    if start_of_week <= complete_time <= end_of_week:
                        members[uid]["checklist_weekly"] += 1

            # 判斷任務是否已完成
            all_done = all(c["is_done"] for c in checklists)
            if all_done:
                members[uid]["task_completed"] += 1
                # 抓最後完成時間是否在本週
                completed_times = [c["completed_at"] for c in checklists if c["completed_at"]]
                if completed_times:
                    latest_time = max(datetime.fromisoformat(t.replace("Z", "+00:00")) + timedelta(hours=8) for t in completed_times)
                    if start_of_week <= latest_time <= end_of_week:
                        members[uid]["task_weekly"] += 1

        # 6️⃣ 套用 Flex 樣板
        with open("weekly.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        template["body"]["contents"][1]["text"] = f"{format_date(start_of_week)} - {format_date(end_of_week)}"
        template["body"]["contents"][-1]["contents"][1]["text"] = today.strftime("%Y/%m/%d")

        members_box = template["body"]["contents"][3]["contents"]
        for i, data in enumerate(members.values()):
            if i > 0:
                members_box.append({ "type": "separator", "margin": "lg" })
            members_box.extend([
                { "type": "text", "text": data["name"], "margin": "lg", "color": "#153448" },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448" },
                        { "type": "text", "text": f"{data['checklist_weekly']}項", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448" },
                        { "type": "text", "text": f"{data['task_weekly']}項", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448" },
                        { "type": "text", "text": f"{data['task_completed']} / {data['task_total']}", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                }
            ])

        return template

    except Exception as e:
        return f"❌ 發送週報失敗: {str(e)}"

