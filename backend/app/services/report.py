"""周报/月报自动生成：聚合待办完成、实验记录、文献新增、写作量、阶段推进。"""
from datetime import date, datetime, timedelta


def period_range(period: str, today: date) -> tuple[date, date, str]:
    """返回 [start, end) 区间与中文标签。"""
    if period == "month":
        start = today.replace(day=1)
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        return start, end, f"{today.year} 年 {today.month} 月"
    start = today - timedelta(days=6)
    end = today + timedelta(days=1)
    return start, end, f"{start.month}/{start.day} - {today.month}/{today.day}"


def build_report(db, period: str, today: date | None = None) -> dict:
    """生成周期科研进展汇报（结构化 + Markdown 文案）。"""
    from .. import models

    today = today or date.today()
    start, end, label = period_range(period, today)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    todos = db.query(models.Todo).filter(models.Todo.date >= start, models.Todo.date < end).all()
    done = [t for t in todos if t.status == "已完成"]
    pending = [t for t in todos if t.status != "已完成"]
    experiments = (
        db.query(models.PhaseExperiment)
        .filter(models.PhaseExperiment.date >= start, models.PhaseExperiment.date < end)
        .all()
    )
    refs = (
        db.query(models.Reference)
        .filter(models.Reference.created_at >= start_dt, models.Reference.created_at < end_dt)
        .all()
    )
    writing = (
        db.query(models.WritingLog)
        .filter(models.WritingLog.date >= start, models.WritingLog.date < end)
        .all()
    )
    phases_done = db.query(models.ProjectPhase).filter(models.ProjectPhase.status == "已完成").all()

    sections: list[dict] = []
    sections.append({"title": "待办完成", "items": [t.title for t in done]})
    sections.append({"title": "待办进行中", "items": [t.title for t in pending]})
    sections.append({"title": "实验记录", "items": [f"{e.date} · {e.title}" for e in experiments]})
    sections.append({"title": "新增文献", "items": [r.title for r in refs]})
    if writing:
        sections.append({
            "title": "写作",
            "items": [f"打卡 {len(writing)} 天，累计 {sum(w.word_count for w in writing)} 字"],
        })
    sections.append({"title": "阶段推进", "items": [f"{p.project.title} · {p.name}" for p in phases_done]})
    sections = [s for s in sections if s["items"]]

    lines = [f"# {label} 科研进展汇报", ""]
    for s in sections:
        lines.append(f"## {s['title']}")
        lines += [f"- {it}" for it in s["items"][:20]]
        lines.append("")
    if not sections:
        lines.append("本周期暂无进展记录，去完成一些待办吧。")

    return {
        "period": period,
        "label": label,
        "stats": {
            "todos_done": len(done),
            "todos_pending": len(pending),
            "experiments": len(experiments),
            "refs_added": len(refs),
            "writing_days": len(writing),
            "writing_total": sum(w.word_count for w in writing),
            "phases_done": len(phases_done),
        },
        "sections": sections,
        "markdown": "\n".join(lines),
    }


def build_report_ai(db, period: str, today: date | None = None) -> dict:
    """AI 版周报/月报：确定性数据聚合 + LLM 润色为结构化报告。

    LLM 未配置或调用失败时自动降级为 build_report 的模板文案（永不报错）。
    返回结构同 build_report，额外带 ai 标记。
    """
    base = build_report(db, period, today)
    from . import llm as llm_service

    if not llm_service.is_configured(db):
        return {**base, "ai": False}

    stats = base["stats"]
    sec_lines: list[str] = []
    for s in base["sections"]:
        sec_lines.append(f"## {s['title']}")
        sec_lines += [f"- {it}" for it in s["items"][:20]]
    context = (
        f"周期：{base['label']}\n"
        f"数据：完成待办 {stats['todos_done']} 项（进行中 {stats['todos_pending']} 项）、实验记录 {stats['experiments']} 条、"
        f"新增文献 {stats['refs_added']} 篇、写作 {stats['writing_days']} 天共 {stats['writing_total']} 字、"
        f"完成阶段 {stats['phases_done']} 个\n\n"
        + ("\n".join(sec_lines) or "本周期暂无进展记录")
    )
    kind = "周报" if period == "week" else "月报"
    system = (
        f"你是科研助理。根据给定数据与条目，撰写一篇结构化{kind}（Markdown）："
        "## 本周概况（2-3 句总结）/ ## 数据摘要（要点式）/ ## 主要进展与成果 / ## 存在问题与反思 / ## 下一步计划。"
        "语言精炼学术，条目如实引用数据，不要编造数据。"
    )
    try:
        markdown = llm_service.chat(db, system, [{"role": "user", "content": context}], max_tokens=2000)
        return {**base, "markdown": markdown, "ai": True}
    except Exception:
        return {**base, "ai": False}


def _term_range(year: int, semester: int) -> tuple[date, date]:
    if semester == 1:
        return date(year, 1, 1), date(year, 7, 1)
    return date(year, 7, 1), date(year + 1, 1, 1)


def build_term_report(db, year: int, semester: int) -> dict:
    """学期科研总结报告：跨模块全维度统计。"""
    from .. import models

    start, end = _term_range(year, semester)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    label = f"{year} 年{'春' if semester == 1 else '秋'}学期"

    def _count(query) -> int:
        return query.count()

    stats = {
        "projects_created": _count(db.query(models.Project).filter(models.Project.created_at >= start_dt, models.Project.created_at < end_dt)),
        "phases_done": _count(db.query(models.ProjectPhase).filter(models.ProjectPhase.status == "已完成")),
        "papers_total": _count(db.query(models.Paper)),
        "papers_published": _count(db.query(models.Paper).filter(models.Paper.status.in_(("Accepted", "Published")))),
        "refs_added": _count(db.query(models.Reference).filter(models.Reference.created_at >= start_dt, models.Reference.created_at < end_dt)),
        "refs_read": _count(db.query(models.Reference).filter(models.Reference.read_status == "已读")),
        "experiments": _count(db.query(models.PhaseExperiment).filter(models.PhaseExperiment.date >= start, models.PhaseExperiment.date < end)),
        "todos_done": _count(db.query(models.Todo).filter(models.Todo.completed_at >= start_dt, models.Todo.completed_at < end_dt)),
        "writing_total": sum(w.word_count for w in db.query(models.WritingLog).filter(models.WritingLog.date >= start, models.WritingLog.date < end).all()),
        "achievements": _count(db.query(models.Achievement)),
        "reading_minutes": sum(s.seconds for s in db.query(models.ReadingSession).filter(models.ReadingSession.started_at >= start_dt, models.ReadingSession.started_at < end_dt).all()) // 60,
    }

    lines = [
        f"# {label} 科研总结报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 数据总览",
        "",
        f"- 新建项目 {stats['projects_created']} 个，完成阶段 {stats['phases_done']} 个",
        f"- 论文共 {stats['papers_total']} 篇，其中已接收/发表 {stats['papers_published']} 篇",
        f"- 新增文献 {stats['refs_added']} 篇，累计已读 {stats['refs_read']} 篇",
        f"- 实验记录 {stats['experiments']} 条",
        f"- 完成待办 {stats['todos_done']} 项，写作累计 {stats['writing_total']} 字",
        f"- 成果 {stats['achievements']} 项，文献阅读 {stats['reading_minutes']} 分钟",
        "",
    ]
    return {"label": label, "stats": stats, "markdown": "\n".join(lines)}


def build_meeting_material(db, today: date | None = None) -> dict:
    """组会材料：本周进展 + 新增文献（含摘要）+ 下周计划 + 待讨论事项。"""
    from .. import models

    today = today or date.today()
    week = build_report(db, "week", today)
    next_week_start = today + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=7)

    plan_todos = (
        db.query(models.Todo)
        .filter(models.Todo.date >= next_week_start, models.Todo.date < next_week_end,
                models.Todo.status != "已完成")
        .order_by(models.Todo.date)
        .all()
    )
    # 待讨论：未转化的导师意见
    discussions: list[str] = []
    for m in db.query(models.AdvisorMeeting).order_by(models.AdvisorMeeting.date.desc()).all():
        for item in (m.action_items or []):
            if not item.startswith("✓"):
                discussions.append(f"{m.date} · {item}")

    lines = [
        f"# 组会材料（{today.strftime('%Y-%m-%d')}）",
        "",
        f"## 本周进展（{week['label']}）",
        "",
        f"- 完成待办 {week['stats']['todos_done']} 项，进行中 {week['stats']['todos_pending']} 项",
        f"- 实验记录 {week['stats']['experiments']} 条，新增文献 {week['stats']['refs_added']} 篇",
        f"- 写作 {week['stats']['writing_total']} 字",
        "",
    ]
    for s in week["sections"]:
        if s["items"]:
            lines.append(f"### {s['title']}")
            lines += [f"- {it}" for it in s["items"][:15]]
            lines.append("")
    lines.append("## 下周计划")
    lines += [f"- [{t.date}] {t.title}" for t in plan_todos] or ["- （未安排）"]
    lines.append("")
    lines.append("## 待讨论事项")
    lines += [f"- {d}" for d in discussions] or ["- （无）"]
    lines.append("")

    return {
        "date": today.isoformat(),
        "stats": week["stats"],
        "plan_count": len(plan_todos),
        "discussions": discussions,
        "markdown": "\n".join(lines),
    }
