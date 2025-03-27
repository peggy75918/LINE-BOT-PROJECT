import os
import json
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
from linebot.v3.messaging import FlexMessage, FlexContainer

# Load environment variables
load_dotenv()

# Supabase config
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

# Format date function
def format_date(d):
    return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    debug_logs = []
    try:
        debug_logs.append("\ud83d\udccc 1\ufe0f\ufe0f \u67e5\u8a62\u6700\u65b0\u5c08\u6848\u4e2d...")
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return "\u26a0\ufe0f \u672c\u7fa4\u7d44\u5c1a\u672a\u5efa\u7acb\u4efb\u4f55\u5c08\u6848"

        project_id = project_res.data[0]["id"]
        debug_logs.append(f"\u2705 \u5c08\u6848 ID: {project_id}")

        debug_logs.append("\ud83d\uddcc 2\ufe0f\ufe0f \u67e5\u8a62\u5c08\u6848\u6210\u54e1...")
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        if not member_res.data:
            return "\u26a0\ufe0f \u5c1a\u672a\u52a0\u5165\u4efb\u4f55\u6210\u54e1"

        members = {m["user_id"]: {
            "name": m["real_name"],
            "checklist_total": 0,
            "checklist_weekly": 0,
            "task_total": 0,
            "task_weekly": 0
        } for m in member_res.data}
        debug_logs.append(f"\ud83d\udc65 \u6210\u54e1\u6578\u91cf: {len(members)}")

        debug_logs.append("\ud83d\uddcc 3\ufe0f\ufe0f \u67e5\u8a62\u4efb\u52d9...")
        task_res = supabase_client.table("tasks").select("id, assignee_id, created_at").eq("project_id", project_id).execute()
        task_map = {}

        today = datetime.utcnow() + timedelta(hours=8)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid
                try:
                    created_at = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                    if start_of_week <= created_at <= end_of_week:
                        members[uid]["task_weekly"] += 1
                except Exception as e:
                    debug_logs.append(f"\u26a0\ufe0f \u4efb\u52d9\u89e3\u6790\u932f\u8aa4: {str(e)}")

        debug_logs.append(f"\u2705 \u6709\u6548\u4efb\u52d9\u6578: {len(task_map)}")

        debug_logs.append("\ud83d\uddcc 4\ufe0f\ufe0f \u67e5\u8a62 checklist...")
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute()

        for c in checklist_res.data:
            uid = task_map.get(c["task_id"])
            if uid:
                members[uid]["checklist_total"] += 1
                if c["is_done"] and c["completed_at"]:
                    try:
                        complete_time = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + timedelta(hours=8)
                        if start_of_week <= complete_time <= end_of_week:
                            members[uid]["checklist_weekly"] += 1
                    except Exception as e:
                        debug_logs.append(f"\u26a0\ufe0f \u6e05\u55ae\u89e3\u6790\u932f\u8aa4: {str(e)}")

        debug_logs.append("\ud83e\udde9 \u8b80\u53d6 Flex \u6a21\u677f...")
        try:
            with open("weekly.json", "r", encoding="utf-8") as f:
                template = json.load(f)
        except Exception as e:
            debug_logs.append(f"\u274c Flex \u6a21\u677f\u8b80\u53d6\u5931\u6557: {str(e)}")
            return "\n".join(debug_logs)

        try:
            template["body"]["contents"][1]["text"] = f"{format_date(start_of_week)} - {format_date(end_of_week)}"
            template["body"]["contents"][-1]["contents"][1]["text"] = end_of_week.strftime("%Y/%m/%d")
            members_box = template["body"]["contents"][3]["contents"]

            for i, data in enumerate(members.values()):
                if i > 0:
                    members_box.append({"type": "separator", "margin": "lg"})
                members_box.append({"type": "text", "text": data["name"], "margin": "lg", "color": "#153448"})
                members_box.append({"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "\u672c\u9031\u5b8c\u6210\u6e05\u55ae", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['checklist_weekly']}\u9805", "size": "sm", "color": "#153448", "align": "end"}
                ]})
                members_box.append({"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "\u672c\u9031\u5b8c\u6210\u4efb\u52d9", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['task_weekly']}\u9805", "size": "sm", "color": "#153448", "align": "end"}
                ]})
                members_box.append({"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "\u5c08\u6848\u4efb\u52d9\u9032\u5ea6", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['task_total']} / {data['task_total']}", "size": "sm", "color": "#153448", "align": "end"}
                ]})

            debug_logs.append("\u2705 Flex \u6a21\u677f\u5b8c\u6210")

            return template  # ✅ 回傳 JSON dict

        except Exception as e:
            debug_logs.append(f"\u274c Flex \u6a21\u677f\u932f\u8aa4: {str(e)}")
            return "\n".join(debug_logs)

    except Exception as e:
        debug_logs.append(f"\u274c \u767c\u9001\u9031\u5831\u5931\u6557: {str(e)}")
        return "\n".join(debug_logs)

