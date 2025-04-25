from datetime import datetime, timezone
import json
import os
from dotenv import load_dotenv
from supabase import create_client

# 載入 .env 環境變數
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supabase_url, supabase_key)

def safe_text(value, default="--"):
    return str(value) if value is not None else default

def generate_project_summary(project_id):
    try:
        # ✅ 專案基本資料
        project_res = supabase.table("projects").select("name, completed_at").eq("id", project_id).maybe_single().execute()
        project = project_res.data
        if not project:
            return "⚠️ 找不到該專案"

        project_name = project["name"]
        completed_date = (
            datetime.fromisoformat(project["completed_at"]) if project.get("completed_at")
            else datetime.now()
        ).astimezone(timezone.utc)

        # ✅ 專案成員
        members_res = supabase.table("project_members").select("user_id, real_name, attribute_tags").eq("project_id", project_id).execute()
        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "attributes": m.get("attribute_tags") or "--",
                "resource_count": 0,
                "comment_count": 0,
                "rating_sum": 0,
                "rating_count": 0,
                "task_total": 0,
                "task_completed": 0,
            }
            for m in members_res.data
        }

        # ✅ 任務
        task_res = supabase.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for task in task_res.data:
            uid = task["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[task["id"]] = uid

        # ✅ checklist 完成數
        checklist_res = supabase.table("task_checklists").select("task_id, is_done").in_("task_id", list(task_map.keys())).execute()
        task_checklist_map = {}
        for item in checklist_res.data:
            task_checklist_map.setdefault(item["task_id"], []).append(item["is_done"])

        for task_id, checks in task_checklist_map.items():
            if all(checks):
                uid = task_map[task_id]
                members[uid]["task_completed"] += 1

        # ✅ 評分
        feedbacks = supabase.table("task_feedbacks").select("user_id, rating").in_("task_id", list(task_map.keys())).eq("is_reflection", False).execute()
        for f in feedbacks.data:
            uid = f["user_id"]
            if uid in members and f.get("rating") is not None:
                members[uid]["rating_sum"] += f["rating"]
                members[uid]["rating_count"] += 1

        # ✅ 分享的資源
        resources = supabase.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in resources.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # ✅ 留言建議
        replies = supabase.table("resource_replies").select("user_id").execute()
        for r in replies.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # ✅ 套用樣板
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        template["body"]["contents"][1]["text"] = completed_date.strftime("%m/%d")  # 日期
        detail_blocks = template["body"]["contents"][3]["contents"]
        detail_blocks[0]["contents"][1]["text"] = project_name
        detail_blocks[1]["contents"][1]["text"] = f"{sum(m['task_total'] for m in members.values())} 項"
        detail_blocks[2]["contents"][1]["text"] = f"{sum(m['resource_count'] for m in members.values())} 項"
        detail_blocks[3]["contents"][1]["text"] = "、".join(m["name"] for m in members.values())

        # ✅ 移除原有的成員區塊與尾端
        preserved = template["body"]["contents"][:5]
        preserved.append({"type": "separator", "margin": "lg"})
        template["body"]["contents"] = preserved

        for m in members.values():
            avg_rating = f"⭐ {round(m['rating_sum'] / m['rating_count'], 1)}" if m["rating_count"] > 0 else "--"

            block = {
                "type": "box",
                "layout": "vertical",
                "margin": "lg",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": safe_text(m["name"]), "color": "#153448", "size": "md"},
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "專案角色屬性", "size": "sm", "color": "#153448", "flex": 0},
                            {"type": "text", "text": safe_text(m["attributes"]), "size": "sm", "color": "#153448", "align": "end", "wrap": True}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "任務完成數與總數", "size": "sm", "color": "#153448", "flex": 0},
                            {"type": "text", "text": f"{m['task_completed']} / {m['task_total']}", "size": "sm", "color": "#153448", "align": "end"}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "分享專案資源數", "size": "sm", "color": "#153448", "flex": 0},
                            {"type": "text", "text": f"{m['resource_count']} 項", "size": "sm", "color": "#153448", "align": "end"}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "建議與反思留言數", "size": "sm", "color": "#153448", "flex": 0},
                            {"type": "text", "text": f"{m['comment_count']} 次", "size": "sm", "color": "#153448", "align": "end"}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "任務平均評分", "size": "sm", "color": "#153448"},
                            {"type": "text", "text": avg_rating, "size": "sm", "color": "#153448", "align": "end"}
                        ]
                    }
                ]
            }

            template["body"]["contents"].append(block)
            template["body"]["contents"].append({"type": "separator", "margin": "lg"})

        # ✅ 感謝文字
        template["body"]["contents"].append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "contents": [{
                "type": "text",
                "text": "感謝大家對此專案的努力與貢獻！",
                "size": "md",
                "color": "#153448",
                "flex": 0
            }]
        })

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"



