"""ORM 模型定义。"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now()


class Project(Base):
    """科研项目：学位课题 / 基金 / 课程 / 其他。"""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    ptype: Mapped[str] = mapped_column(String(50), default="其他")
    status: Mapped[str] = mapped_column(String(20), default="进行中")  # 进行中/暂停/已完成/已放弃
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Milestone.due_date"
    )
    timeline_points: Mapped[list["TimelinePoint"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="TimelinePoint.sort_order"
    )
    papers: Mapped[list["Paper"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    materials: Mapped[list["Material"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    phases: Mapped[list["ProjectPhase"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectPhase.sort_order"
    )


class Milestone(Base):
    """项目里程碑（冲刺化）：驱动 deadline 提醒 + 目标/范围/进度。"""
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="未开始")  # 未开始/进行中/已完成/延期
    note: Mapped[str] = mapped_column(Text, default="")
    # V5 迁移列：冲刺化
    goal: Mapped[str] = mapped_column(Text, default="")       # 目标
    scope: Mapped[str] = mapped_column(Text, default="")      # 范围
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100

    project: Mapped[Project] = relationship(back_populates="milestones")


class TimelinePoint(Base):
    """项目关键时间线节点（开题/中期/答辩等）。"""
    __tablename__ = "timeline_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    point_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="timeline_points")


class Paper(Base):
    """论文：覆盖投稿全生命周期。"""
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    paper_type: Mapped[str] = mapped_column(String(30), default="期刊")  # 期刊/会议/学位论文/预印本
    abstract: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")  # 逗号分隔
    status: Mapped[str] = mapped_column(String(30), default="Draft")
    target_journal: Mapped[str] = mapped_column(String(200), default="")
    journal_quartile: Mapped[str] = mapped_column(String(20), default="")  # 分区，自由填
    journal_if: Mapped[str] = mapped_column(String(20), default="")  # 影响因子，自由填
    submission_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # V7 迁移列：大/小论文
    paper_scale: Mapped[str] = mapped_column(String(20), default="小论文")  # 大论文/小论文
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    project: Mapped[Optional[Project]] = relationship(back_populates="papers")
    versions: Mapped[list["PaperVersion"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", order_by="PaperVersion.version_no"
    )
    review_rounds: Mapped[list["ReviewRound"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", order_by="ReviewRound.round_no"
    )
    sections: Mapped[list["PaperSection"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", order_by="PaperSection.order_no"
    )
    status_logs: Mapped[list["PaperStatusLog"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", order_by="PaperStatusLog.created_at"
    )
    cited_references: Mapped[list["PaperReference"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class PaperStatusLog(Base):
    """投稿历程：状态流转日志（状态机变更时自动记录）。"""
    __tablename__ = "paper_status_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    from_status: Mapped[str] = mapped_column(String(30), default="")
    to_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    paper: Mapped[Paper] = relationship(back_populates="status_logs")


class PaperReference(Base):
    """论文-文献引用关联（写作引用证据链）。"""
    __tablename__ = "paper_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))

    paper: Mapped[Paper] = relationship(back_populates="cited_references")
    reference: Mapped["Reference"] = relationship()


class PaperSection(Base):
    """论文章节进度：标题/顺序/目标字数/状态。"""
    __tablename__ = "paper_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    order_no: Mapped[int] = mapped_column(Integer, default=0)
    target_words: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="未开始")  # 未开始/撰写中/完成
    # V7 迁移列：章节分区记录（正文/要点）
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    paper: Mapped[Paper] = relationship(back_populates="sections")


class PaperVersion(Base):
    """论文草稿版本。"""
    __tablename__ = "paper_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    changelog: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    paper: Mapped[Paper] = relationship(back_populates="versions")


class ReviewRound(Base):
    """论文审稿轮次记录。"""
    __tablename__ = "review_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    round_no: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(30))  # Major Revision/Minor Revision/Accept/Reject 等
    summary: Mapped[str] = mapped_column(Text, default="")
    review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    stored_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="review_rounds")


class Material(Base):
    """科研材料文件：数据/代码/图表/实验记录/文档/其他。"""
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(30), default="其他")
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(300), default="")  # 逗号分隔
    file_name: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    project: Mapped[Optional[Project]] = relationship(back_populates="materials")


class Reference(Base):
    """文献条目。"""
    __tablename__ = "references"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(String(200), default="")
    doi: Mapped[str] = mapped_column(String(200), default="")
    bibkey: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[str] = mapped_column(String(300), default="")  # 逗号分隔
    read_status: Mapped[str] = mapped_column(String(20), default="未读")  # 未读/在读/已读
    # 以下四列为 V2 迁移列（database.py 中 ALTER TABLE ADD COLUMN）
    category: Mapped[str] = mapped_column(String(50), default="其他")  # 分类：经典必读/综述/方法/数据/工具/其他
    quartile: Mapped[str] = mapped_column(String(20), default="")      # 分区 Q1-Q4（旧字段，兼容保留）
    journal_if: Mapped[str] = mapped_column(String(20), default="")    # 影响因子
    fulltext_source: Mapped[str] = mapped_column(String(10), default="")  # 全文来源：auto/manual
    # V6 迁移列：文献等级标签（JCR/中科院/新锐分区，均可手动修改）
    jcr_quartile: Mapped[str] = mapped_column(String(20), default="")    # JCR 分区 Q1-Q4
    cas_quartile: Mapped[str] = mapped_column(String(20), default="")    # 中科院分区 1-4区
    xinrui_quartile: Mapped[str] = mapped_column(String(20), default="")  # 新锐分区 1-4区
    # V3 迁移列：阅读进度
    reading_progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    # V4 迁移列：阅读队列
    queue_priority: Mapped[int] = mapped_column(Integer, default=0)  # 0=不在队列，1-3 优先级
    queue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    stored_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    citations: Mapped[list["ReferenceCitation"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan"
    )
    text: Mapped[Optional["ReferenceText"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan", uselist=False
    )
    deep_reading: Mapped[Optional["DeepReading"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan", uselist=False
    )
    annotations: Mapped[list["PdfAnnotation"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan"
    )


class PdfAnnotation(Base):
    """PDF 高亮批注：归一化矩形坐标 + 备注。"""
    __tablename__ = "pdf_annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(20), default="#FDE047")  # 荧光黄/绿/粉
    rect: Mapped[str] = mapped_column(String(200))  # 归一化 x,y,w,h（0-1，逗号分隔）
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    reference: Mapped[Reference] = relationship(back_populates="annotations")


class DeepReading(Base):
    """文献精读记录（问题/方法/结论/启发模板，每篇一行）。"""
    __tablename__ = "deep_reading"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"), unique=True)
    question: Mapped[str] = mapped_column(Text, default="")   # 研究问题
    method: Mapped[str] = mapped_column(Text, default="")     # 方法
    conclusion: Mapped[str] = mapped_column(Text, default="")  # 结论
    insight: Mapped[str] = mapped_column(Text, default="")    # 对我的启发
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    reference: Mapped[Reference] = relationship(back_populates="deep_reading")


class ReadingSession(Base):
    """文献阅读时长记录（阅读器打开计时，关闭上报）。"""
    __tablename__ = "reading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatMessage(Base):
    """AI 对话式文献精读：每篇文献一个持久化问答线程。"""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user / assistant
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReferenceCitation(Base):
    """文献引用记录（OpenAlex 抓取）：该 ref 引用了 cited_doi。"""
    __tablename__ = "reference_citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    cited_doi: Mapped[str] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    reference: Mapped[Reference] = relationship(back_populates="citations")


class ReferenceText(Base):
    """文献全文提取文本（PDF → 文本，供摘要视图与技能链导出）。"""
    __tablename__ = "reference_texts"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")   # 启发式摘要（离线）
    keywords: Mapped[str] = mapped_column(Text, default="")  # 提取的关键词
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    reference: Mapped[Reference] = relationship(back_populates="text")


# ---------------- 学生档案 ----------------
class StudentProfile(Base):
    """学生信息（单例行）。"""
    __tablename__ = "student_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    student_id: Mapped[str] = mapped_column(String(50), default="")
    school: Mapped[str] = mapped_column(String(100), default="")
    college: Mapped[str] = mapped_column(String(100), default="")
    major: Mapped[str] = mapped_column(String(100), default="")
    advisor: Mapped[str] = mapped_column(String(50), default="")
    research_direction: Mapped[str] = mapped_column(String(200), default="")
    enrollment_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_graduation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contact: Mapped[str] = mapped_column(String(100), default="")
    photo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------- 待办 ----------------
class Todo(Base):
    """每日待办事项（驱动日历、科研动态、周报）。"""
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="待办")  # 待办/进行中/已完成
    priority: Mapped[str] = mapped_column(String(10), default="中")  # 高/中/低
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    repeat: Mapped[str] = mapped_column(String(10), default="none")  # V3 迁移列：none/daily/weekly
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    project: Mapped[Optional[Project]] = relationship()


# ---------------- 项目阶段 ----------------
class ProjectPhase(Base):
    """项目阶段（开题设计/想法验证/实验/分析/总结，预置五阶段可自定义）。"""
    __tablename__ = "project_phases"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="未开始")  # 未开始/进行中/已完成/延期
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(default=False)  # 预置阶段标记

    project: Mapped[Project] = relationship(back_populates="phases")
    experiments: Mapped[list["PhaseExperiment"]] = relationship(
        back_populates="phase", cascade="all, delete-orphan", order_by="PhaseExperiment.date"
    )
    references: Mapped[list["PhaseReference"]] = relationship(
        back_populates="phase", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["PhaseTask"]] = relationship(
        back_populates="phase", cascade="all, delete-orphan"
    )


class PhaseExperiment(Base):
    """阶段实验记录（结构化字段：目的/方法/结果/结论/复盘 + 材料图表关联）。"""
    __tablename__ = "phase_experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("project_phases.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    # 以下六列为 V2 迁移列（database.py 中 ALTER TABLE ADD COLUMN）
    purpose: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    conclusion: Mapped[str] = mapped_column(Text, default="")
    reflection: Mapped[str] = mapped_column(Text, default="")  # 复盘/失败经验
    material_ids: Mapped[str] = mapped_column(String(500), default="")  # 逗号分隔的材料 id
    # V3 迁移列：预注册实验模板
    hypothesis: Mapped[str] = mapped_column(Text, default="")  # 假设
    variables: Mapped[str] = mapped_column(Text, default="")   # 变量
    controls: Mapped[str] = mapped_column(Text, default="")    # 对照组
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    phase: Mapped[ProjectPhase] = relationship(back_populates="experiments")
    steps: Mapped[list["ExperimentStep"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentStep.order_no"
    )
    comments: Mapped[list["ExperimentComment"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentComment.created_at"
    )


class ExperimentStep(Base):
    """实验步骤工作流（eLabFTW Steps）：checklist 逐步推进。"""
    __tablename__ = "experiment_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("phase_experiments.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="未开始")  # 未开始/进行中/已完成
    order_no: Mapped[int] = mapped_column(Integer, default=0)
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    experiment: Mapped[PhaseExperiment] = relationship(back_populates="steps")


class ExperimentComment(Base):
    """实验评论（eLabFTW 评论）：协作讨论与反思。"""
    __tablename__ = "experiment_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("phase_experiments.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    experiment: Mapped[PhaseExperiment] = relationship(back_populates="comments")


class ExperimentTemplate(Base):
    """实验模板库（eLabFTW 模板）：预注册结构一键复用。"""
    __tablename__ = "experiment_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="其他")
    body: Mapped[dict] = mapped_column(JSON, default=dict)  # {purpose, method, hypothesis, variables, controls, steps: [{title, duration_min}]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PhaseReference(Base):
    """阶段-文献证据关联。"""
    __tablename__ = "phase_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("project_phases.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))

    phase: Mapped[ProjectPhase] = relationship(back_populates="references")
    reference: Mapped[Reference] = relationship()


class PhaseTask(Base):
    """阶段-待办任务关联。"""
    __tablename__ = "phase_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("project_phases.id", ondelete="CASCADE"))
    todo_id: Mapped[int] = mapped_column(ForeignKey("todos.id", ondelete="CASCADE"))

    phase: Mapped[ProjectPhase] = relationship(back_populates="tasks")
    todo: Mapped[Todo] = relationship()


# ---------------- 成果 ----------------
class Achievement(Base):
    """成果管理：论文（同步）/专利/软件/获奖/其他。"""
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    atype: Mapped[str] = mapped_column(String(20), default="其他")  # 论文/专利/软件/获奖/其他
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="")
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue: Mapped[str] = mapped_column(String(200), default="")
    identifier: Mapped[str] = mapped_column(String(100), default="")  # 专利号/软著号/DOI
    authors: Mapped[str] = mapped_column(String(500), default="")  # 逗号分隔
    detail: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    # V4 迁移列：附件
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    stored_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------- 项目复盘 / 风险 ----------------
class ProjectReview(Base):
    """项目结项复盘（每项目一行）。"""
    __tablename__ = "project_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    goal_achievement: Mapped[str] = mapped_column(Text, default="")   # 目标达成情况
    difficulties: Mapped[str] = mapped_column(Text, default="")       # 困难与对策
    lessons: Mapped[str] = mapped_column(Text, default="")            # 经验教训
    reusable_methods: Mapped[str] = mapped_column(Text, default="")   # 可复用方法
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ProjectRisk(Base):
    """项目风险与阻塞问题。"""
    __tablename__ = "project_risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    phase_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project_phases.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(10), default="中")   # 高/中/低
    status: Mapped[str] = mapped_column(String(20), default="未解决")  # 未解决/处理中/已解决
    resolution: Mapped[str] = mapped_column(Text, default="")          # 解决记录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------- 期刊库 ----------------
class Journal(Base):
    """目标期刊库：分区/IF/审稿周期预设。"""
    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    quartile: Mapped[str] = mapped_column(String(20), default="")
    impact_factor: Mapped[str] = mapped_column(String(20), default="")
    review_weeks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 设置 ----------------
class Setting(Base):
    """键值设置（写作周目标、主题偏好等）。"""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------- LLM 用量与模型元数据 ----------------
class LlmUsageLog(Base):
    """LLM 调用用量日志：每次成功调用记一行（状态栏 tokens/费用统计）。"""
    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="openai")  # openai / ollama
    model: Mapped[str] = mapped_column(String(100), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0)   # 缓存命中（DeepSeek 等）
    cost: Mapped[float] = mapped_column(Float, default=0.0)             # 折算费用（估算）
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class LlmModelMeta(Base):
    """模型元数据：上下文窗口 + 单价（预设种子 + 可编辑）。"""
    __tablename__ = "llm_model_meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(100), unique=True)
    context_window: Mapped[int] = mapped_column(Integer, default=0)        # 0=未知
    input_price_per_m: Mapped[float] = mapped_column(Float, default=0.0)   # 每百万 tokens 输入价
    output_price_per_m: Mapped[float] = mapped_column(Float, default=0.0)  # 每百万 tokens 输出价
    cache_price_per_m: Mapped[float] = mapped_column(Float, default=0.0)   # 缓存命中价（0=同输入价）
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------- 材料版本 ----------------
class MaterialVersion(Base):
    """材料历史版本（覆盖上传时保留旧文件）。"""
    __tablename__ = "material_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 文献集合 / 手动关联 / 保存视图 ----------------
class Collection(Base):
    """文献集合（Zotero Collections）：多对多。"""
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    links: Mapped[list["ReferenceCollectionLink"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class ReferenceCollectionLink(Base):
    __tablename__ = "reference_collection_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))

    collection: Mapped[Collection] = relationship(back_populates="links")


class RelatedReference(Base):
    """手动关联文献（Zotero Related）：无向边。"""
    __tablename__ = "related_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_a: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    ref_b: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))


class ReferenceAiLink(Base):
    """AI 自动关联（本地相似度预筛 + LLM 语义评分）：无向边，weight 0-100。"""
    __tablename__ = "reference_ai_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_a: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    ref_b: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    weight: Mapped[int] = mapped_column(Integer, default=0)          # 关联强度 0-100
    reason: Mapped[str] = mapped_column(String(500), default="")     # LLM 关联理由
    tags: Mapped[list] = mapped_column(JSON, default=list)           # 语义标签（方法相似/结论互补/同领域…）
    method: Mapped[str] = mapped_column(String(20), default="local")  # local / llm
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SavedView(Base):
    """保存的搜索视图（Zotero Saved Searches）。"""
    __tablename__ = "saved_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 资源库存 ----------------
class LabResource(Base):
    """实验室资源库存（eLabFTW 资源库）：试剂/设备/耗材。"""
    __tablename__ = "lab_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    rtype: Mapped[str] = mapped_column(String(20), default="试剂")  # 试剂/设备/耗材/其他
    quantity: Mapped[float] = mapped_column(default=0)
    unit: Mapped[str] = mapped_column(String(20), default="个")
    low_threshold: Mapped[Optional[float]] = mapped_column(nullable=True)  # 低库存阈值
    location: Mapped[str] = mapped_column(String(100), default="")
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="正常")  # 正常/低库存/已耗尽/过期
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 科研画布 ----------------
class CanvasNode(Base):
    """画布节点（Obsidian Canvas）：项目/实验/灵感/文献/笔记/文本卡。"""
    __tablename__ = "canvas_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    canvas_id: Mapped[int] = mapped_column(Integer, default=1)
    ntype: Mapped[str] = mapped_column(String(20), default="text")  # project/experiment/idea/reference/note/text
    title: Mapped[str] = mapped_column(String(300))
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 对应对象 id
    x: Mapped[float] = mapped_column(default=0)
    y: Mapped[float] = mapped_column(default=0)
    w: Mapped[float] = mapped_column(default=180)
    h: Mapped[float] = mapped_column(default=90)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CanvasEdge(Base):
    """画布连线。"""
    __tablename__ = "canvas_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    canvas_id: Mapped[int] = mapped_column(Integer, default=1)
    from_node: Mapped[int] = mapped_column(ForeignKey("canvas_nodes.id", ondelete="CASCADE"))
    to_node: Mapped[int] = mapped_column(ForeignKey("canvas_nodes.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 统一模板系统 ----------------
class Template(Base):
    """统一模板（Obsidian Templates）：实验/笔记/待办/项目。"""
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    ttype: Mapped[str] = mapped_column(String(20), default="实验")  # 实验/笔记/待办/项目
    name: Mapped[str] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 灵感收集箱 ----------------
class Idea(Base):
    """灵感/想法收集箱：可转化为待办或实验记录。"""
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="待处理")  # 待处理/已转化/搁置
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 导师沟通 ----------------
class AdvisorMeeting(Base):
    """导师沟通记录：action_items 可转为待办。"""
    __tablename__ = "advisor_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    topic: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    action_items: Mapped[list] = mapped_column(JSON, default=list)  # [str, ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 写作打卡 ----------------
class WritingLog(Base):
    """每日写作字数打卡。"""
    __tablename__ = "writing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    paper_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    section_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # V3 迁移列：关联章节
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    paper: Mapped[Optional[Paper]] = relationship()


class Note(Base):
    """笔记：挂到 reference（阅读笔记）/ project（实验记录）。"""
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # reference / project
    target_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------- 系统通知 ----------------
class Notification(Base):
    """操作记录与系统通知：前端写操作自动上报。"""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(20), default="info")  # info/success/warning
    target_type: Mapped[str] = mapped_column(String(30), default="")   # project/paper/reference/todo...
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 科研追踪 ----------------
class TrackingSource(Base):
    """科研动态订阅源：arXiv 关键词/分类 或 RSS URL。"""
    __tablename__ = "tracking_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    stype: Mapped[str] = mapped_column(String(30), default="arxiv_keyword")  # arxiv_keyword/arxiv_category/rss
    query: Mapped[str] = mapped_column(String(500))  # arXiv 查询串 或 RSS URL
    active: Mapped[bool] = mapped_column(default=True)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class TrackingItem(Base):
    """追踪到的条目（论文/动态），external_id 去重。"""
    __tablename__ = "tracking_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("tracking_sources.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(200))  # arXiv ID 或 RSS guid
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSON, default=list)
    abstract: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(600), default="")
    published: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_new: Mapped[bool] = mapped_column(default=False)  # 是否新发现（未读标记）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------- 组会记录 ----------------
class GroupMeeting(Base):
    """组会记录：关联项目/文献 + 元信息 + PPT 附件 + 纪要 + AI 问答式笔记。"""
    __tablename__ = "group_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    topic: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")          # 要点记录 / AI 纪要
    qa_notes: Mapped[str] = mapped_column(Text, default="")          # AI 问答式笔记（Markdown）
    ppt_file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    ppt_stored_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # V7 迁移列：项目挂钩 + 元信息
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    meeting_type: Mapped[str] = mapped_column(String(20), default="组会")  # 组会/进展汇报/文献汇报/开题/中期/预答辩
    status: Mapped[str] = mapped_column(String(20), default="已安排")       # 已安排/已召开/已归档
    attendees: Mapped[str] = mapped_column(String(500), default="")         # 参会人，逗号分隔
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agenda: Mapped[str] = mapped_column(Text, default="")             # 议程
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MeetingReference(Base):
    """组会-文献关联（多对多）。"""
    __tablename__ = "meeting_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("group_meetings.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))


# ---------------- 系统事件（状态栏错误监控） ----------------
class SystemEvent(Base):
    """系统事件：异常中间件记录未处理 5xx，状态栏据此展示错误计数。"""
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(10), default="error")  # error / info
    source: Mapped[str] = mapped_column(String(200), default="")     # 来源（接口路径等）
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
