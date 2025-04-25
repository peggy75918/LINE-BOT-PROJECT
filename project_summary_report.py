import os
import json
from datetime import datetime, timezone
from supabase import create_client
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def generate_project_summary(project_id):
    try:
        # 1️⃣ 查詢專案基本資料
        project_res = supabase_client.table("projects").select("name, completed_at").eq("id", project_id).maybe_single().execute()
        project = project_res.data
        if not project:
            return "⚠️ 找不到該專案"

        name = project["name"]
        completed_at = project.get("completed_at")
        completed_date = datetime.fromisoformat(completed_at) if completed_at else datetime.now(timezone.utc)

        # 2️⃣ 查詢所有專案成員
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

        # 3️⃣ 查詢任務分配情況
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        task_ids = list(task_map.keys())

        # 4️⃣ 查詢 checklist 狀態
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done").in_("task_id", task_ids).execute()
        checklist_map = {}
        for c in checklist_res.data:
            checklist_map.setdefault(c["task_id"], []).append(c["is_done"])
        for task_id, checks in checklist_map.items():
            if all(checks):
                uid = task_map[task_id]
                members[uid]["task_completed"] += 1

        # 5️⃣ 查詢 task_feedbacks
        feedback_res = supabase_client.table("task_feedbacks").select("user_id, rating").in_("task_id", task_ids).eq("is_reflection", False).execute()
        for f in feedback_res.data:
            uid = f["user_id"]
            rating = f.get("rating")
            if uid in members and rating is not None:
                members[uid]["rating_sum"] += rating
                members[uid]["rating_count"] += 1

        # 6️⃣ 查詢 shared_resources
        resource_res = supabase_client.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in resource_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # 7️⃣ 查詢 resource_replies
        reply_res = supabase_client.table("resource_replies").select("user_id").execute()
        for r in reply_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # 8️⃣ 載入樣板 JSON
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        # 更新總結日期
        template["body"]["contents"][1]["text"] = completed_date.strftime("%m/%d")

        # 更新總覽資料
        overview = template["body"]["contents"][3]["contents"]
        overview[0]["contents"][1]["text"] = name
        overview[1]["contents"][1]["text"] = f"{sum(m['task_total'] for m in members.values())} 項"
        overview[2]["contents"][1]["text"] = f"{sum(m['resource_count'] for m in members.values())} 項"
        overview[3]["contents"][1]["text"] = "、".join(m["name"] for m in members.values())

        # 清除樣板後續內容，只保留前 7 項
        template["body"]["contents"] = template["body"]["contents"][:7]

        # 逐一加入成員統計區塊
        for m in members.values():
            avg_rating = f"⭐ {round(m['rating_sum'] / m['rating_count'], 1)}" if m["rating_count"] > 0 else "--"
            member_block = [
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "sm",
                    "contents": [
                        {"type": "text", "text": m["name"], "color": "#153448", "size": "md"},
                        {
                            "type": "box", "layout": "horizontal", "contents": [
                                {"type": "text", "text": "專案角色屬性", "size": "sm", "color": "#153448", "flex": 0},
                                {"type": "text", "text": m["attributes"], "size": "sm", "color": "#153448", "align": "end", "margin": "md", "wrap": True}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "contents": [
                                {"type": "text", "text": "任務完成數與總數", "size": "sm", "color": "#153448", "flex": 0},
                                {"type": "text", "text": f"{m['task_completed']} / {m['task_total']}", "size": "sm", "color": "#153448", "align": "end"}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "contents": [
                                {"type": "text", "text": "分享專案資源數", "size": "sm", "color": "#153448", "flex": 0},
                                {"type": "text", "text": f"{m['resource_count']} 項", "size": "sm", "color": "#153448", "align": "end"}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "contents": [
                                {"type": "text", "text": "建議與反思留言數", "size": "sm", "color": "#153448", "flex": 0},
                                {"type": "text", "text": f"{m['comment_count']} 次", "size": "sm", "color": "#153448", "align": "end"}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "contents": [
                                {"type": "text", "text": "任務平均評分", "size": "sm", "color": "#153448"},
                                {"type": "text", "text": avg_rating, "size": "sm", "color": "#153448", "align": "end"}
                            ]
                        }
                    ]
                },
                {"type": "separator", "margin": "lg"}
            ]
            template["body"]["contents"].extend(member_block)

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"


