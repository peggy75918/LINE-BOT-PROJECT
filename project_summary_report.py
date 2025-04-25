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
        # 取得專案資訊
        project_res = supabase_client.table("projects").select("name, completed_at").eq("id", project_id).maybe_single().execute()
        project = project_res.data
        if not project:
            return "\u26a0\ufe0f \u627e\u4e0d\u5230\u8a72\u5c08\u6848"

        name = project["name"]
        completed_at = project.get("completed_at")
        completed_date = datetime.fromisoformat(completed_at) if completed_at else datetime.now()

        # 專案成員
        members_res = supabase_client.table("project_members").select("user_id, real_name, attribute_tags").eq("project_id", project_id).execute()
        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "attributes": m.get("attribute_tags", "") or "--",
                "resource_count": 0,
                "comment_count": 0,
                "rating_sum": 0,
                "rating_count": 0,
                "task_total": 0,
                "task_completed": 0
            } for m in members_res.data
        }

        # 任務資訊
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        # checklist 狀態
        task_ids = list(task_map.keys())
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done").in_("task_id", task_ids).execute()
        checklist_map = {}
        for c in checklist_res.data:
            checklist_map.setdefault(c["task_id"], []).append(c["is_done"])

        for tid, checks in checklist_map.items():
            if all(checks):
                uid = task_map[tid]
                members[uid]["task_completed"] += 1

        # 任務評分
        feedbacks = supabase_client.table("task_feedbacks").select("user_id, rating").in_("task_id", task_ids).eq("is_reflection", False).execute()
        for f in feedbacks.data:
            uid = f["user_id"]
            if uid in members and f.get("rating") is not None:
                members[uid]["rating_sum"] += f["rating"]
                members[uid]["rating_count"] += 1

        # 專案資源
        resources = supabase_client.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in resources.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # 回覆留言
        replies = supabase_client.table("resource_replies").select("user_id").execute()
        for r in replies.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # 讀取 Flex 樣板
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        contents = template.get("body", {}).get("contents", [])
        if len(contents) < 6:
            return "\u274c Flex \u6a21\u677f\u5167\u5bb9\u4e0d\u8db3\uff0c\u8acb\u78ba\u8a8d project_summary_template.json \u7d50\u69cb"

        # 設定上方摘要內容
        template["body"]["contents"][1]["text"] = completed_date.strftime("%m/%d")
        summary_section = contents[3].get("contents", [])

        total_tasks = sum(m["task_total"] for m in members.values())
        total_resources = sum(m["resource_count"] for m in members.values())
        all_names = "\u3001".join(m["name"] for m in members.values())

        summary_section[0]["contents"][1]["text"] = name
        summary_section[1]["contents"][1]["text"] = f"{total_tasks} \u9805"
        summary_section[2]["contents"][1]["text"] = f"{total_resources} \u9805"
        summary_section[3]["contents"][1]["text"] = all_names

        # 成員資料樣板區塊
        member_block_template = contents[5:len(contents)-2]  # 去掉 separator + footer
        footer_block = contents[-1]

        # 重建內容
        template["body"]["contents"] = contents[:5]

        member_blocks = []
        for i, m in enumerate(members.values()):
            avg_rating = f"\u2b50 {round(m['rating_sum'] / m['rating_count'], 1)}" if m["rating_count"] > 0 else "0"
            block = json.loads(json.dumps(member_block_template))

            block[0]["text"] = m["name"]
            block[1]["contents"][1]["text"] = m["attributes"]
            block[2]["contents"][1]["text"] = f"{m['task_completed']} / {m['task_total']}"
            block[3]["contents"][1]["text"] = f"{m['resource_count']} \u9805"
            block[4]["contents"][1]["text"] = f"{m['comment_count']} \u6b21"
            block[5]["contents"][1]["text"] = avg_rating

            member_blocks.extend(block)
            member_blocks.append({"type": "separator", "margin": "lg"})

        template["body"]["contents"].extend(member_blocks)
        template["body"]["contents"].append(footer_block)

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"
