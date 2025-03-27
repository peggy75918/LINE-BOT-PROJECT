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
        debug_logs.append("📌 1️⃣ 查詢最新專案中...")
        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return "⚠️ 本群組尚未建立任何專案"

        project_id = project_res.data[0]["id"]
        debug_logs.append(f"✅ 專案 ID: {project_id}")

        debug_logs.append("📌 2️⃣ 查詢專案成員...")
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        if not member_res.data:
            return "⚠️ 尚未加入任何成員"

        members = {m["user_id"]: {
            "name": m["real_name"],
            "checklist_total": 0,
            "checklist_weekly": 0,
            "task_total": 0,
            "task_weekly": 0
        } for m in member_res.data}
        debug_logs.append(f"👥 成員數量: {len(members)}")

        debug_logs.append("📌 3️⃣ 查詢任務...")
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
                    debug_logs.append(f"⚠️ 任務解析錯誤: {str(e)}")

        debug_logs.append(f"✅ 有效任務數: {len(task_map)}")

        debug_logs.append("📌 4️⃣ 查詢 checklist...")
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
                        debug_logs.append(f"⚠️ 清單解析錯誤: {str(e)}")

        debug_logs.append("🧩 讀取 Flex 樣板...")
        try:
            with open("weekly.json", "r", encoding="utf-8") as f:
                template = json.load(f)
        except Exception as e:
            debug_logs.append(f"❌ Flex 樣板讀取失敗: {str(e)}")
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
                    {"type": "text", "text": "本週完成清單", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['checklist_weekly']}項", "size": "sm", "color": "#153448", "align": "end"}
                ]})
                members_box.append({"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "本週完成任務", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['task_weekly']}項", "size": "sm", "color": "#153448", "align": "end"}
                ]})
                members_box.append({"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": "專案任務進度", "size": "sm", "color": "#153448"},
                    {"type": "text", "text": f"{data['task_total']} / {data['task_total'] + 0}", "size": "sm", "color": "#153448", "align": "end"}
                ]})

            debug_logs.append("✅ Flex 樣板完成")

            return FlexMessage(
                alt_text="任務週報",
                contents=FlexContainer.from_json(json.dumps(template))
            )

        except Exception as e:
            debug_logs.append(f"❌ Flex 樣板錯誤: {str(e)}")
            return "\n".join(debug_logs)

    except Exception as e:
        debug_logs.append(f"❌ 發送週報失敗: {str(e)}")
        return "\n".join(debug_logs)


