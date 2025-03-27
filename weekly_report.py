import os
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(supabase_url, supabase_key)

def format_date(d): return d.strftime("%m/%d")

def generate_weekly_report(group_id):
    log = []
    try:
        log.append("📌 1️⃣ 查詢最新專案中...")

        project_res = supabase_client.table("projects").select("id").eq("group_id", group_id).order("created_at", desc=True).limit(1).execute()
        if not project_res.data:
            return "⚠️ 本群組尚未建立任何專案"

        project_id = project_res.data[0]["id"]
        log.append(f"✅ 專案 ID: {project_id}")

        log.append("📌 2️⃣ 查詢專案成員...")
        member_res = supabase_client.table("project_members").select("user_id, real_name").eq("project_id", project_id).execute()
        if not member_res.data:
            return "⚠️ 尚未加入任何成員"

        members = {
            m["user_id"]: {
                "name": m["real_name"],
                "weekly_checklist_done": 0,
                "weekly_task_done": 0,
                "task_done": 0,
                "task_total": 0
            } for m in member_res.data
        }
        log.append(f"✅ 成員數量: {len(members)}")

        log.append("📌 3️⃣ 查詢任務資料...")
        task_res = supabase_client.table("tasks").select("id, assignee_id").eq("project_id", project_id).execute()
        task_map = {t["id"]: t["assignee_id"] for t in task_res.data if t["assignee_id"] in members}
        log.append(f"✅ 任務數: {len(task_map)}")

        log.append("📌 4️⃣ 查詢 checklist...")
        checklist_res = supabase_client.table("task_checklists").select("task_id, is_done, completed_at").in_("task_id", list(task_map.keys())).execute()

        tz_tw = timedelta(hours=8)
        today = (datetime.utcnow() + tz_tw).replace(tzinfo=None)
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 📌 檢查任務 checklist 是否全部完成
        checklist_group = {}  # {task_id: [checklist, checklist, ...]}
        for c in checklist_res.data:
            checklist_group.setdefault(c["task_id"], []).append(c)

            # 統計本週完成的 checklist
            if c["is_done"] and c["completed_at"]:
                complete_time = (
                    datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + tz_tw
                ).replace(tzinfo=None)
                if start_of_week <= complete_time <= end_of_week:
                    uid = task_map.get(c["task_id"])
                    if uid:
                        members[uid]["weekly_checklist_done"] += 1

        # 📌 遍歷每個任務判斷完成情況
        for task_id, checklists in checklist_group.items():
            uid = task_map[task_id]
            members[uid]["task_total"] += 1

            if all(c["is_done"] for c in checklists):
                members[uid]["task_done"] += 1

                # 檢查這筆任務的最後完成 checklist 是否在本週
                completed_times = [
                    datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00")) + tz_tw
                    for c in checklists if c["completed_at"]
                ]
                if completed_times:
                    latest = max(completed_times).replace(tzinfo=None)
                    if start_of_week <= latest <= end_of_week:
                        members[uid]["weekly_task_done"] += 1

        log.append("📌 5️⃣ 組合回報訊息")
        header = f"📊 任務週報（{format_date(start_of_week)} - {format_date(end_of_week)}）"
        lines = []
        for data in members.values():
            lines.append(
                f"{data['name']}："
                f"{data['task_done']} / {data['task_total']} 🧩（本週完成任務 {data['weekly_task_done']} 筆 / 清單 {data['weekly_checklist_done']} 項）"
            )

        return header + "\n" + "\n".join(lines)

    except Exception as e:
        log.append(f"❌ 發生錯誤: {str(e)}")
        return "\n".join(log)
