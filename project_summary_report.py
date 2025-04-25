import os
import json
from datetime import datetime, timezone
from supabase import create_client
from dotenv import load_dotenv

# 讀取 .env 環境變數
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def format_date(d):
    return d.strftime("%m/%d")

def generate_project_summary(project_id):
    try:
        # 檢查專案資訊
        project_res = supabase_client.table("projects").select("name, completed_at").eq("id", project_id).maybe_single().execute()
        project = project_res.data
        if not project:
            return "⚠️ 找不到該專案"

        name = project["name"]
        completed_at = project.get("completed_at")
        completed_date = datetime.fromisoformat(completed_at) + timezone.utc.utcoffset(datetime.now()) if completed_at else datetime.now()

        # 取成員
        members_res = supabase_client.table("project_members").select("user_id, real_name, attributes").eq("project_id", project_id).execute()
        members = {m["user_id"]: {
            "name": m["real_name"],
            "attributes": m.get("attributes", ""),
            "resource_count": 0,
            "comment_count": 0,
            "rating_sum": 0,
            "rating_count": 0,
            "task_total": 0,
            "task_completed": 0
        } for m in members_res.data}

        # 取 tasks
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        # 取 checklist 狀態
        task_ids = list(task_map.keys())
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done").in_("task_id", task_ids).execute()
        checklist_map = {}
        for c in checklist_res.data:
            checklist_map.setdefault(c["task_id"], []).append(c["is_done"])

        for tid, checks in checklist_map.items():
            if all(checks):
                uid = task_map[tid]
                members[uid]["task_completed"] += 1

        # 評分
        feedbacks = supabase_client.table("task_feedbacks").select("user_id, rating").in_("task_id", task_ids).eq("is_reflection", False).execute()
        for f in feedbacks.data:
            uid = f["user_id"]
            if uid in members and f.get("rating"):
                members[uid]["rating_sum"] += f["rating"]
                members[uid]["rating_count"] += 1

        # 資源
        resources = supabase_client.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in resources.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # 留言
        replies = supabase_client.table("resource_replies").select("user_id").execute()
        for r in replies.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # 讀取模板
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        # 設定模板頁首信息
        template["body"]["contents"][1]["text"] = completed_date.strftime("%m/%d")  # 時間
        details = template["body"]["contents"][3]["contents"]

        # 所有 tasks 數量
        total_tasks = sum(m["task_total"] for m in members.values())
        total_resources = sum(m["resource_count"] for m in members.values())
        all_names = "、".join(m["name"] for m in members.values())

        details[0]["contents"][1]["text"] = name
        details[1]["contents"][1]["text"] = f"{total_tasks} 項"
        details[2]["contents"][1]["text"] = f"{total_resources} 項"
        details[3]["contents"][1]["text"] = all_names

        # 成員執行數據
        member_section = template["body"]["contents"][5:]
        template["body"]["contents"] = template["body"]["contents"][:5]  # 清空原本內容

        for m in members.values():
            avg_rating = f"⭐ {round(m["rating_sum"] / m["rating_count"], 1)}" if m["rating_count"] > 0 else "--"
            block = json.loads(json.dumps(member_section))  # deepcopy
            block[0]["text"] = m["name"]
            block[1]["contents"][1]["text"] = m["attributes"] or "--"
            block[2]["contents"][1]["text"] = f"{m['task_completed']} / {m['task_total']}"
            block[3]["contents"][1]["text"] = f"{m['resource_count']} 項"
            block[4]["contents"][1]["text"] = f"{m['comment_count']} 次"
            block[5]["contents"][1]["text"] = avg_rating
            template["body"]["contents"] += block + [{"type": "separator", "margin": "lg"}]

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"