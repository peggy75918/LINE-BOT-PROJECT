import os
import json
from datetime import datetime, timedelta, timezone
from supabase import create_client
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def format_tw_date(iso_str):
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")) + timedelta(hours=8)
    return dt.strftime("%m/%d")

def generate_project_summary(project_id):
    try:
        # 查詢專案資料（包含建立和完成日期）
        project_res = supabase.table("projects") \
            .select("name, created_at, completed_at") \
            .eq("id", project_id).maybe_single().execute()

        if not project_res.data:
            return "❌ 找不到指定專案"

        project = project_res.data
        name = project["name"]
        created = format_tw_date(project["created_at"])
        completed = format_tw_date(project["completed_at"]) if project["completed_at"] else created
        date_range = f"{created} - {completed}"

        # 查詢成員
        members_res = supabase.table("project_members") \
            .select("user_id, real_name, attribute_tags") \
            .eq("project_id", project_id).execute()

        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "attributes": " ".join(f"#{tag}" for tag in (m.get("attribute_tags") or [])),
                "task_total": 0,
                "task_completed": 0,
                "resource_count": 0,
                "comment_count": 0,
                "rating_sum": 0,
                "rating_count": 0,
            } for m in members_res.data
        }

        # 查詢任務
        task_res = supabase.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {}
        for t in task_res.data:
            uid = t["assignee_id"]
            if uid in members:
                members[uid]["task_total"] += 1
                task_map[t["id"]] = uid

        # 任務完成情況
        checklist_res = supabase.table("task_checklists").select("task_id, is_done").in_("task_id", list(task_map)).execute()
        checklist_map = {}
        for c in checklist_res.data:
            checklist_map.setdefault(c["task_id"], []).append(c["is_done"])

        for tid, checks in checklist_map.items():
            if all(checks):
                uid = task_map[tid]
                members[uid]["task_completed"] += 1

        # 評分
        rating_res = supabase.table("task_feedbacks").select("user_id, rating").in_("task_id", list(task_map)).eq("is_reflection", False).execute()
        for f in rating_res.data:
            uid = f["user_id"]
            if uid in members and f.get("rating") is not None:
                members[uid]["rating_sum"] += f["rating"]
                members[uid]["rating_count"] += 1

        # 資源
        resource_res = supabase.table("shared_resources").select("user_id").eq("project_id", project_id).execute()
        for r in resource_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["resource_count"] += 1

        # 留言
        reply_res = supabase.table("resource_replies").select("user_id").execute()
        for r in reply_res.data:
            uid = r["user_id"]
            if uid in members:
                members[uid]["comment_count"] += 1

        # 套用樣板
        with open("project_summary_template.json", "r", encoding="utf-8") as f:
            template = json.load(f)

        # ⬆️ 標題與日期
        template["body"]["contents"][1]["text"] = date_range

        # ⬆️ 專案資訊
        details = template["body"]["contents"][3]["contents"]
        details[0]["contents"][1]["text"] = name
        details[1]["contents"][1]["text"] = f"{sum(m['task_total'] for m in members.values())} 項"
        details[2]["contents"][1]["text"] = f"{sum(m['resource_count'] for m in members.values())} 項"
        details[3]["contents"][1]["text"] = "、".join(m["name"] for m in members.values())

        # 移除「項目後 separator」
        template["body"]["contents"] = template["body"]["contents"][:5]

        # ⬇️ 成員統計
        for m in members.values():
            rating = f"⭐ {round(m['rating_sum']/m['rating_count'], 1)}" if m["rating_count"] > 0 else "—"
            block = [
                { "type": "text", "text": m["name"], "color": "#153448", "size": "md" },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "專案角色屬性", "size": "sm", "color": "#153448", "flex": 0 },
                        { "type": "text", "text": m["attributes"] or "—", "size": "sm", "color": "#153448", "align": "end", "margin": "md", "wrap": True }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "任務完成數與總數", "size": "sm", "color": "#153448", "flex": 0 },
                        { "type": "text", "text": f"{m['task_completed']} / {m['task_total']}", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "分享專案資源數", "size": "sm", "color": "#153448", "flex": 0 },
                        { "type": "text", "text": f"{m['resource_count']} 項", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "建議與反思留言數", "size": "sm", "color": "#153448", "flex": 0 },
                        { "type": "text", "text": f"{m['comment_count']} 次", "size": "sm", "color": "#153448", "align": "end" }
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "contents": [
                        { "type": "text", "text": "任務平均評分", "size": "sm", "color": "#153448" },
                        { "type": "text", "text": rating, "size": "sm", "color": "#153448", "align": "end" }
                    ]
                }
            ]
            template["body"]["contents"] += [
                { "type": "separator", "margin": "lg" },
                { "type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": block }
            ]

        # 最後一個感謝區塊
        template["body"]["contents"] += [
            { "type": "separator", "margin": "lg" },
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "感謝大家對此專案的努力與貢獻！",
                        "size": "md",
                        "color": "#153448",
                        "flex": 0
                    }
                ]
            }
        ]

        return template

    except Exception as e:
        return f"❌ 生成報表失敗: {str(e)}"




