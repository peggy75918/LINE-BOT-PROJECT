import os
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
from linebot.v3.messaging import FlexMessage, FlexContainer

load_dotenv()

supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def format_date(d): return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    try:
        # 📅 取得本週區間（台灣時間）
        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 🔍 查詢群組最新的 project_id
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return TextMessage(text="⚠️ 尚未建立專案")
        project_id = project_res.data[0]["id"]

        # 👥 專案成員
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        members = {
            m["user_id"]: {"name": m["real_name"], "weekly_checklist": 0, "weekly_task": 0, "total_task": 0, "completed_task": 0}
            for m in member_res.data
        }

        # 📋 任務資料
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for task in task_res.data:
            uid = task["assignee_id"]
            if uid in members:
                task_map[task["id"]] = uid
                members[uid]["total_task"] += 1

        # ✅ checklist
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map)).execute()
        task_done_tracker = set()
        for c in checklist_res.data:
            uid = task_map[c["task_id"]]
            if c["is_done"]:
                members[uid]["weekly_checklist"] += 1
                if c["completed_at"]:
                    completed = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                    if start_of_week <= completed <= end_of_week:
                        # 每個 checklist count 一次；任務完成只算一次
                        if c["task_id"] not in task_done_tracker:
                            members[uid]["weekly_task"] += 1
                            task_done_tracker.add(c["task_id"])
                members[uid]["completed_task"] += 1

        # 🧾 組合 FlexMessage JSON
        contents = []
        for m in members.values():
            contents += [
                {"type": "text", "text": m["name"], "color": "#153448"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448"},
                        {"type": "text", "text": f"{m['weekly_checklist']}項", "size": "sm", "color": "#153448", "align": "end"}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448"},
                        {"type": "text", "text": f"{m['weekly_task']}項", "size": "sm", "color": "#153448", "align": "end"}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448"},
                        {"type": "text", "text": f"{m['completed_task']} / {m['total_task']}", "size": "sm", "color": "#153448", "align": "end"}
                    ]
                },
                {"type": "separator", "margin": "lg"}
            ]

        flex_json = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "📊 任務週報", "weight": "bold", "size": "xl", "color": "#153448"},
                    {"type": "text", "text": f"{format_date(start_of_week)} - {format_date(end_of_week)}", "size": "md", "color": "#aaaaaa", "weight": "bold"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": contents},
                    {"type": "separator", "margin": "lg"},
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "md",
                        "contents": [
                            {"type": "text", "text": "本次週報截至", "size": "xs", "color": "#aaaaaa"},
                            {"type": "text", "text": end_of_week.strftime("%Y/%m/%d"), "size": "xs", "color": "#aaaaaa"}
                        ]
                    }
                ]
            }
        }

        return FlexMessage(alt_text="任務週報", contents=FlexContainer.from_json(flex_json))

    except Exception as e:
        return TextMessage(text=f"❌ 週報產生失敗：{e}")
