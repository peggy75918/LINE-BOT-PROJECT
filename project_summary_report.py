import os
import json
from datetime import datetime, timezone
from copy import deepcopy
from supabase import create_client
from dotenv import load_dotenv

# 讀取 .env 環境變數
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def generate_project_summary(project_id):
    try:
        # 查專案資訊
        project_res = supabase_client.table("projects").select("name, completed_at").eq("id", project_id).maybe_single().execute()
        project = project_res.data
        if not project:
            return "⚠️ 找不到該專案"

        name = project["name"]
        completed_at = project.get("completed_at")
        completed_date = datetime.fromisoformat(completed_at) if completed_at else datetime.now(timezone.utc)

        # 查成員
        member_res = supabase_client.table("project_members").select("user_id, real_name, attribute_tags").eq("project_id", project_id).execute()
        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "attributes": m.get("attribute_tags") or "--",
                "resource_count": 0,
                "comment_count": 0,
                "rating_sum": 0,
                "rating_count": 0,
                "task_total": 0,
                "task_completed": 0
            } for m in member_res.data
        }

        # 查任務
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        # 查 checklist 完成
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done").in_("task_id", list(task_map)).execute()
        checklist_map = {}
        for c in checklist_res.data:
            checklist_map.setdefault(c["task_id"], []).append(c["is_done"])
        for tid, checks in checklist_map.items():
            if all(checks):
                uid = task_map[tid]
                members[uid]["task_completed"] += 1

        # 查 feedback 評分
        feedback_res = supabase_client.table("task_feedbacks").select("user_id, rating").in_("task_id", list(task_map)).eq("is_reflection", False).execute()
        for f in feedback_res.data:
            uid = f["user_id"]
            if uid in members and f["rating"] is not None:
                members[uid]["rating_sum"] += f["rating"]
                members[uid]["rating_count"] += 1

        # 查資源
        res_res = supabase_client.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in res_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # 查留言
        reply_res = supabase_client.table("resource_replies").select("user_id").execute()
        for r in reply_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # 載入樣板
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        # 更新總覽欄位
        template["body"]["contents"][1]["text"] = completed_date.strftime("%m/%d")
        overview = template["body"]["contents"][3]["contents"]
        overview[0]["contents"][1]["text"] = name
        overview[1]["contents"][1]["text"] = f"{sum(m['task_total'] for m in members.values())} 項"
        overview[2]["contents"][1]["text"] = f"{sum(m['resource_count'] for m in members.values())} 項"
        overview[3]["contents"][1]["text"] = "、".join(m["name"] for m in members.values())

        # 動態成員資料模板
        base = template["body"]["contents"]
        member_template = deepcopy(base[5])
        thanks_footer = deepcopy(base[-1])
        template["body"]["contents"] = base[:5]

        for m in members.values():
            avg_rating = f"⭐ {round(m['rating_sum'] / m['rating_count'], 1)}" if m["rating_count"] else "0"
            block = deepcopy(member_template)
            block[0]["text"] = m["name"]
            block[1]["contents"][1]["text"] = m["attributes"]
            block[2]["contents"][1]["text"] = f"{m['task_completed']} / {m['task_total']}"
            block[3]["contents"][1]["text"] = f"{m['resource_count']} 項"
            block[4]["contents"][1]["text"] = f"{m['comment_count']} 次"
            block[5]["contents"][1]["text"] = avg_rating
            template["body"]["contents"].append(block)
            template["body"]["contents"].append({ "type": "separator", "margin": "lg" })

        # 加入感謝結尾
        template["body"]["contents"].append(thanks_footer)

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"

