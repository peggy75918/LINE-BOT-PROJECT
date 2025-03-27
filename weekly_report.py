import os
import json
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
from linebot.v3.messaging.models import FlexMessage, FlexContainer

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

# 時區與時間處理
def format_date(d):
    return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    try:
        # ↑ 本週區間
        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 1. 查詢專案
        project = supabase.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project.data:
            return TextMessage(text="⚠️ 本群組尚未建立任何專案")

        project_id = project.data[0]["id"]

        # 2. 查詢專案成員
        members = supabase.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute().data
        member_map = {m["user_id"]: {"name": m["real_name"], "checklist": 0, "weekly_check": 0, "tasks": 0, "weekly_tasks": 0} for m in members}

        # 3. 查任務
        tasks = supabase.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute().data
        task_map = {t["id"]: t["assignee_id"] for t in tasks if t["assignee_id"] in member_map}
        for assignee_id in task_map.values():
            member_map[assignee_id]["tasks"] += 1

        # 4. 查 checklists
        checklist = supabase.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute().data

        for item in checklist:
            uid = task_map.get(item["task_id"])
            if not uid:
                continue
            member_map[uid]["checklist"] += 1
            if item["is_done"]:
                # weekly checklist 完成
                if item["completed_at"]:
                    completed_time = datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                    if start_of_week <= completed_time <= end_of_week:
                        member_map[uid]["weekly_check"] += 1

        # 本週完成的任務（所有 checklist 完成）
        for tid, uid in task_map.items():
            check_items = [c for c in checklist if c["task_id"] == tid]
            if check_items and all(c["is_done"] for c in check_items):
                if any(
                    (datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)).date() >= start_of_week.date()
                    for c in check_items if c["completed_at"]
                ):
                    member_map[uid]["weekly_tasks"] += 1

        # ↑ 整合成 FlexMessage
        with open("weekly.json", "r", encoding="utf-8") as f:
            flex_data = json.load(f)

        flex_data["body"]["contents"][1]["text"] = f"{format_date(start_of_week)} - {format_date(end_of_week)}"
        flex_data["body"]["contents"][-1]["contents"][1]["text"] = today.strftime("%Y/%m/%d")

        members_content = []
        for mem in member_map.values():
            members_content += [
                {"type": "text", "text": mem["name"], "color": "#153448"},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{mem['weekly_check']}項", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{mem['weekly_tasks']}項", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{mem['weekly_tasks']} / {mem['tasks']}", "size": "sm", "color": "#153448", "align": "end"},
                ]},
                {"type": "separator", "margin": "lg"}
            ]

        flex_data["body"]["contents"][3]["contents"] = members_content

        return FlexMessage(alt_text="本週任務週報", contents=FlexContainer.from_json(json.dumps(flex_data)))

    except Exception as e:
        return TextMessage(text=f"❌ 發生錯誤: {str(e)}")

