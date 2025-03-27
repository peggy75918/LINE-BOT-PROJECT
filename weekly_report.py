import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def format_date(d): return d.strftime("%m/%d")

def build_flex_message(summary):
    body_contents = [
        {
            "type": "text",
            "text": "📊 任務週報",
            "weight": "bold",
            "size": "xl",
            "margin": "md",
            "color": "#153448"
        },
        {
            "type": "text",
            "text": summary["date_range"],
            "size": "md",
            "color": "#aaaaaa",
            "wrap": True,
            "weight": "bold"
        },
        {"type": "separator", "margin": "lg"},
        {
            "type": "box",
            "layout": "vertical",
            "margin": "lg",
            "spacing": "sm",
            "contents": []
        }
    ]

    for idx, m in enumerate(summary["members"]):
        body_contents[3]["contents"].extend([
            {
                "type": "text",
                "text": m["name"],
                "color": "#153448",
                "margin": "lg" if idx != 0 else "none",
                "weight": "bold"
            },
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{m['weekly_checklist_done']}項", "size": "sm", "color": "#153448", "align": "end"}
                ]
            },
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{m['weekly_tasks_done']}項", "size": "sm", "color": "#153448", "align": "end"}
                ]
            },
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{m['total_tasks_done']} / {m['total_tasks']}", "size": "sm", "color": "#153448", "align": "end"}
                ]
            },
            {"type": "separator", "margin": "lg"}
        ])

    # 結尾
    body_contents.append({"type": "separator", "margin": "lg"})
    body_contents.append({
        "type": "box",
        "layout": "horizontal",
        "margin": "md",
        "contents": [
            {
                "type": "text",
                "text": "本次週報截至",
                "size": "xs",
                "color": "#aaaaaa",
                "flex": 0
            },
            {
                "type": "text",
                "text": summary["cutoff"],
                "color": "#aaaaaa",
                "size": "xs"
            }
        ]
    })

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": body_contents
        },
        "styles": {"footer": {"separator": True}}
    }


def generate_weekly_report(group_id):
    today = datetime.utcnow() + timedelta(hours=8)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    try:
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            raise ValueError("⚠️ 本群組尚未建立任何專案")
        project_id = project_res.data[0]["id"]

        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        members = {m["user_id"]: {
            "name": m["real_name"],
            "weekly_checklist_done": 0,
            "weekly_tasks_done": 0,
            "total_tasks_done": 0,
            "total_tasks": 0
        } for m in member_res.data}

        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            if t["assignee_id"] in members:
                task_map[t["id"]] = t["assignee_id"]
                members[t["assignee_id"]]["total_tasks"] += 1

        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute()
        completed_tasks_set = set()

        for c in checklist_res.data:
            uid = task_map.get(c["task_id"])
            if uid:
                if c["is_done"]:
                    members[uid]["total_tasks_done"] += 1
                    if c["completed_at"]:
                        complete_time = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                        if start_of_week <= complete_time <= end_of_week:
                            members[uid]["weekly_checklist_done"] += 1
                            completed_tasks_set.add(c["task_id"])

        for tid in completed_tasks_set:
            uid = task_map.get(tid)
            if uid:
                members[uid]["weekly_tasks_done"] += 1

        # 組合 FlexMessage JSON
        result = {
            "date_range": f"{format_date(start_of_week)} - {format_date(end_of_week)}",
            "members": list(members.values()),
            "cutoff": today.strftime("%Y/%m/%d")
        }

        return build_flex_message(result)

    except Exception as e:
        print(f"❌ 錯誤：{e}")
        return {
            "type": "text",
            "text": f"⚠️ 發生錯誤：{str(e)}"
        }

        return TextMessage(text=f"❌ 週報產生失敗：{e}")
