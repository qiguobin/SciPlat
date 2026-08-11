"""CSV 数据导出（utf-8-sig BOM，Excel 中文兼容）。"""
import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(rows: list[list], headers: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    # utf-8-sig 加 BOM，Excel 直接打开不乱码
    data = "\ufeff" + buf.getvalue()
    from urllib.parse import quote
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        iter([data.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


@router.get("/csv")
def export_csv(kind: str, db: Session = Depends(get_db)):
    if kind == "todos":
        rows = [[t.id, t.date, t.title, t.status, t.priority, t.project.title if t.project else "",
                 t.completed_at.strftime("%Y-%m-%d %H:%M") if t.completed_at else ""]
                for t in db.query(models.Todo).order_by(models.Todo.date.desc()).all()]
        return _csv_response(rows, ["ID", "日期", "内容", "状态", "优先级", "项目", "完成时间"], "待办.csv")
    if kind == "experiments":
        rows = [[e.id, e.date, e.title, e.purpose, e.method, e.result, e.conclusion, e.reflection]
                for e in db.query(models.PhaseExperiment).order_by(models.PhaseExperiment.date.desc()).all()]
        return _csv_response(rows, ["ID", "日期", "标题", "目的", "方法", "结果", "结论", "复盘"], "实验记录.csv")
    if kind == "achievements":
        rows = [[a.atype, a.title, a.status, a.date, a.venue, a.identifier, a.authors]
                for a in db.query(models.Achievement).order_by(models.Achievement.date.desc()).all()]
        return _csv_response(rows, ["类型", "标题", "状态", "日期", "期刊/机构", "编号", "作者"], "成果.csv")
    if kind == "references":
        rows = [[r.id, r.title, "、".join(r.authors or []), r.year, r.venue, r.doi, r.category,
                 r.quartile, r.journal_if, r.read_status]
                for r in db.query(models.Reference).order_by(models.Reference.created_at.desc()).all()]
        return _csv_response(rows, ["ID", "标题", "作者", "年份", "期刊", "DOI", "分类", "分区", "IF", "阅读状态"], "文献.csv")
    if kind == "writing":
        rows = [[w.date, w.word_count, w.paper.title if w.paper else "", w.note]
                for w in db.query(models.WritingLog).order_by(models.WritingLog.date.desc()).all()]
        return _csv_response(rows, ["日期", "字数", "论文", "备注"], "写作打卡.csv")
    raise HTTPException(400, f"不支持的导出类型：{kind}")
