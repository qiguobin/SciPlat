"""Pydantic 请求/响应模型。"""
from datetime import date, datetime
from datetime import date as dt_date  # 字段名 date 会遮蔽类型名，需别名
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- 项目 ----------------
class MilestoneCreate(BaseModel):
    title: str
    due_date: date
    status: str = "未开始"
    note: str = ""
    goal: str = ""
    scope: str = ""
    progress: int = 0


class MilestoneUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    note: Optional[str] = None
    goal: Optional[str] = None
    scope: Optional[str] = None
    progress: Optional[int] = None


class MilestoneOut(ORMModel):
    id: int
    project_id: int
    title: str
    due_date: date
    status: str
    note: str
    goal: str = ""
    scope: str = ""
    progress: int = 0


class TimelineCreate(BaseModel):
    title: str
    point_date: date
    note: str = ""
    sort_order: int = 0


class TimelineUpdate(BaseModel):
    title: Optional[str] = None
    point_date: Optional[date] = None
    note: Optional[str] = None
    sort_order: Optional[int] = None


class TimelineOut(ORMModel):
    id: int
    project_id: int
    title: str
    point_date: date
    note: str
    sort_order: int


class ProjectCreate(BaseModel):
    title: str
    ptype: str = "其他"
    status: str = "进行中"
    description: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    ptype: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ProjectOut(ORMModel):
    id: int
    title: str
    ptype: str
    status: str
    description: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    paper_count: int = 0
    material_count: int = 0
    milestone_count: int = 0


class ProjectDetailOut(ProjectOut):
    milestones: List[MilestoneOut] = []
    timeline_points: List[TimelineOut] = []
    papers: List["PaperOut"] = []
    materials: List["MaterialOut"] = []
    phases: List["PhaseDetailOut"] = []


# ---------------- 论文 ----------------
class PaperCreate(BaseModel):
    title: str
    project_id: Optional[int] = None
    paper_type: str = "期刊"
    paper_scale: str = "小论文"  # 大论文/小论文
    abstract: str = ""
    keywords: str = ""
    status: str = "Draft"
    target_journal: str = ""
    journal_quartile: str = ""
    journal_if: str = ""
    submission_deadline: Optional[date] = None


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[int] = None
    paper_type: Optional[str] = None
    paper_scale: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    status: Optional[str] = None
    target_journal: Optional[str] = None
    journal_quartile: Optional[str] = None
    journal_if: Optional[str] = None
    submission_deadline: Optional[date] = None


class StatusChange(BaseModel):
    to: str


class PaperOut(ORMModel):
    id: int
    title: str
    project_id: Optional[int] = None
    project_title: Optional[str] = None
    paper_type: str
    paper_scale: str = "小论文"
    abstract: str
    keywords: str
    status: str
    target_journal: str
    journal_quartile: str
    journal_if: str
    submission_deadline: Optional[date] = None
    created_at: datetime
    updated_at: datetime


class PaperVersionOut(ORMModel):
    id: int
    paper_id: int
    version_no: int
    file_name: str
    file_size: int
    changelog: str
    created_at: datetime


class ReviewRoundOut(ORMModel):
    id: int
    paper_id: int
    round_no: int
    decision: str
    summary: str
    review_date: Optional[date] = None
    file_name: Optional[str] = None


class ReviewRoundCreate(BaseModel):
    decision: str
    summary: str = ""
    review_date: Optional[date] = None


class PaperDetailOut(PaperOut):
    versions: List[PaperVersionOut] = []
    review_rounds: List[ReviewRoundOut] = []
    next_statuses: List[str] = []
    sections: List["PaperSectionOut"] = []


# ---------------- 论文章节 ----------------
class PaperSectionCreate(BaseModel):
    title: str
    order_no: int = 0
    target_words: int = 0
    status: str = "未开始"


class PaperSectionUpdate(BaseModel):
    title: Optional[str] = None
    order_no: Optional[int] = None
    target_words: Optional[int] = None
    status: Optional[str] = None
    content: Optional[str] = None


class PaperSectionOut(ORMModel):
    id: int
    paper_id: int
    title: str
    order_no: int
    target_words: int
    status: str
    content: str = ""
    written_words: int = 0  # 该章节已打卡字数（查询时填充）


# ---------------- 文献精读与引用 ----------------
class DeepReadingUpdate(BaseModel):
    question: Optional[str] = None
    method: Optional[str] = None
    conclusion: Optional[str] = None
    insight: Optional[str] = None


class DeepReadingOut(ORMModel):
    id: int
    reference_id: int
    question: str
    method: str
    conclusion: str
    insight: str
    updated_at: datetime


class CitationRequest(BaseModel):
    ids: List[int]
    format: str = "gbt7714"


# ---------------- 材料 ----------------
class MaterialOut(ORMModel):
    id: int
    project_id: Optional[int] = None
    project_title: Optional[str] = None
    category: str
    name: str
    description: str
    tags: str
    file_name: str
    size: int
    mime: str
    created_at: datetime


class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None


# ---------------- 文献 ----------------
class ReferenceCreate(BaseModel):
    title: str
    authors: List[str] = []
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    bibkey: str = ""
    tags: str = ""
    read_status: str = "未读"
    category: str = "其他"
    quartile: str = ""
    journal_if: str = ""
    jcr_quartile: str = ""
    cas_quartile: str = ""
    xinrui_quartile: str = ""


class ReferenceUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    bibkey: Optional[str] = None
    tags: Optional[str] = None
    read_status: Optional[str] = None
    category: Optional[str] = None
    quartile: Optional[str] = None
    journal_if: Optional[str] = None
    jcr_quartile: Optional[str] = None
    cas_quartile: Optional[str] = None
    xinrui_quartile: Optional[str] = None


class ReferenceOut(ORMModel):
    id: int
    title: str
    authors: List[str]
    year: Optional[int] = None
    venue: str
    doi: str
    bibkey: str
    tags: str
    read_status: str
    category: str = "其他"
    quartile: str = ""
    journal_if: str = ""
    jcr_quartile: str = ""
    cas_quartile: str = ""
    xinrui_quartile: str = ""
    fulltext_source: str = ""
    reading_progress: int = 0
    file_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReferenceTextOut(ORMModel):
    id: int
    reference_id: int
    text: str
    summary: str
    keywords: str
    extracted_at: datetime


class DoiRequest(BaseModel):
    doi: str


# ---------------- 学生档案 ----------------
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    student_id: Optional[str] = None
    school: Optional[str] = None
    college: Optional[str] = None
    major: Optional[str] = None
    advisor: Optional[str] = None
    research_direction: Optional[str] = None
    enrollment_year: Optional[int] = None
    expected_graduation: Optional[int] = None
    contact: Optional[str] = None


class ProfileOut(ORMModel):
    id: int
    name: str
    student_id: str
    school: str
    college: str
    major: str
    advisor: str
    research_direction: str
    enrollment_year: Optional[int] = None
    expected_graduation: Optional[int] = None
    contact: str
    photo_path: Optional[str] = None
    updated_at: datetime


# ---------------- 待办 ----------------
class TodoCreate(BaseModel):
    date: date
    title: str
    description: str = ""
    status: str = "待办"
    priority: str = "中"
    project_id: Optional[int] = None
    repeat: str = "none"


class TodoUpdate(BaseModel):
    date: Optional[date] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    project_id: Optional[int] = None
    repeat: Optional[str] = None


class TodoStatusChange(BaseModel):
    status: str


class TodoOut(ORMModel):
    id: int
    date: date
    title: str
    description: str
    status: str
    priority: str
    project_id: Optional[int] = None
    project_title: Optional[str] = None
    repeat: str = "none"
    created_at: datetime
    completed_at: Optional[datetime] = None


# ---------------- 项目阶段 ----------------
class PhaseCreate(BaseModel):
    name: str
    description: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str = "未开始"
    sort_order: int = 0


class PhaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class PhaseOut(ORMModel):
    id: int
    project_id: int
    name: str
    description: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str
    sort_order: int
    is_default: bool


class ExperimentCreate(BaseModel):
    title: str
    date: dt_date
    purpose: str = ""
    method: str = ""
    result: str = ""
    conclusion: str = ""
    reflection: str = ""
    material_ids: str = ""


class ExperimentUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[dt_date] = None
    purpose: Optional[str] = None
    method: Optional[str] = None
    result: Optional[str] = None
    conclusion: Optional[str] = None
    reflection: Optional[str] = None
    material_ids: Optional[str] = None


class ExperimentOut(ORMModel):
    id: int
    phase_id: int
    title: str
    date: dt_date
    purpose: str
    method: str
    result: str
    conclusion: str
    reflection: str
    material_ids: str
    created_at: datetime


class PhaseDetailOut(PhaseOut):
    experiments: List[ExperimentOut] = []
    reference_ids: List[int] = []
    todo_ids: List[int] = []


class PhaseRefLink(BaseModel):
    reference_id: int


class PhaseTaskLink(BaseModel):
    todo_id: int


# ---------------- 成果 ----------------
class AchievementCreate(BaseModel):
    atype: str = "其他"
    title: str
    status: str = ""
    date: Optional[dt_date] = None
    venue: str = ""
    identifier: str = ""
    authors: str = ""
    detail: str = ""
    link: str = ""
    notes: str = ""


class AchievementUpdate(BaseModel):
    atype: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    date: Optional[dt_date] = None
    venue: Optional[str] = None
    identifier: Optional[str] = None
    authors: Optional[str] = None
    detail: Optional[str] = None
    link: Optional[str] = None
    notes: Optional[str] = None


class AchievementOut(ORMModel):
    id: int
    atype: str
    title: str
    status: str
    date: Optional[dt_date] = None
    venue: str
    identifier: str
    authors: str
    detail: str
    link: str
    notes: str
    file_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------- 灵感 ----------------
class IdeaCreate(BaseModel):
    content: str
    tags: str = ""
    status: str = "待处理"


class IdeaUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None


class IdeaOut(ORMModel):
    id: int
    content: str
    tags: str
    status: str
    created_at: datetime


class IdeaConvertBody(BaseModel):
    target: str  # todo / experiment
    date: Optional[dt_date] = None
    priority: str = "中"
    project_id: Optional[int] = None
    phase_id: Optional[int] = None


# ---------------- 导师沟通 ----------------
class MeetingCreate(BaseModel):
    date: dt_date
    topic: str = ""
    summary: str = ""
    action_items: List[str] = []


class MeetingUpdate(BaseModel):
    date: Optional[dt_date] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[List[str]] = None


class MeetingOut(ORMModel):
    id: int
    date: dt_date
    topic: str
    summary: str
    action_items: List[str]
    created_at: datetime


# ---------------- 写作打卡 ----------------
class WritingLogCreate(BaseModel):
    date: dt_date
    paper_id: Optional[int] = None
    section_id: Optional[int] = None
    word_count: int = 0
    note: str = ""


class WritingLogUpdate(BaseModel):
    date: Optional[dt_date] = None
    paper_id: Optional[int] = None
    section_id: Optional[int] = None
    word_count: Optional[int] = None
    note: Optional[str] = None


class WritingLogOut(ORMModel):
    id: int
    date: dt_date
    paper_id: Optional[int] = None
    section_id: Optional[int] = None
    word_count: int
    note: str
    created_at: datetime


# ---------------- 项目复盘 / 风险 ----------------
class ReviewUpdate(BaseModel):
    goal_achievement: Optional[str] = None
    difficulties: Optional[str] = None
    lessons: Optional[str] = None
    reusable_methods: Optional[str] = None


class ReviewOut(ORMModel):
    id: int
    project_id: int
    goal_achievement: str
    difficulties: str
    lessons: str
    reusable_methods: str
    updated_at: datetime


class RiskCreate(BaseModel):
    title: str
    severity: str = "中"
    status: str = "未解决"
    resolution: str = ""
    phase_id: Optional[int] = None


class RiskUpdate(BaseModel):
    title: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    phase_id: Optional[int] = None


class RiskOut(ORMModel):
    id: int
    project_id: int
    phase_id: Optional[int] = None
    title: str
    severity: str
    status: str
    resolution: str
    created_at: datetime
    resolved_at: Optional[datetime] = None


# ---------------- 期刊库 ----------------
class JournalCreate(BaseModel):
    name: str
    quartile: str = ""
    impact_factor: str = ""
    review_weeks: Optional[int] = None
    notes: str = ""


class JournalUpdate(BaseModel):
    name: Optional[str] = None
    quartile: Optional[str] = None
    impact_factor: Optional[str] = None
    review_weeks: Optional[int] = None
    notes: Optional[str] = None


class JournalOut(ORMModel):
    id: int
    name: str
    quartile: str
    impact_factor: str
    review_weeks: Optional[int] = None
    notes: str


# ---------------- 设置 ----------------
class SettingUpdate(BaseModel):
    value: str


class SettingOut(ORMModel):
    key: str
    value: str
    updated_at: datetime


# ---------------- 材料版本 ----------------
class MaterialVersionOut(ORMModel):
    id: int
    material_id: int
    version_no: int
    file_name: str
    size: int
    created_at: datetime


# ---------------- PDF 批注 ----------------
class AnnotationCreate(BaseModel):
    page: int = 0
    color: str = "#FDE047"
    rect: str
    note: str = ""


class AnnotationUpdate(BaseModel):
    note: Optional[str] = None
    color: Optional[str] = None


class AnnotationOut(ORMModel):
    id: int
    reference_id: int
    page: int
    color: str
    rect: str
    note: str
    created_at: datetime


# ---------------- 论文引用文献 ----------------
class PaperRefLink(BaseModel):
    reference_id: int


# ---------------- 投稿历程 ----------------
class StatusLogOut(ORMModel):
    id: int
    paper_id: int
    from_status: str
    to_status: str
    created_at: datetime


# ---------------- 笔记 ----------------
class NoteCreate(BaseModel):
    target_type: str
    target_id: int
    content: str


class NoteUpdate(BaseModel):
    content: str


class NoteOut(ORMModel):
    id: int
    target_type: str
    target_id: int
    content: str
    created_at: datetime
    updated_at: datetime


# ---------------- V5：实验步骤/模板/评论 ----------------
class StepCreate(BaseModel):
    title: str
    status: str = "未开始"
    order_no: int = 0
    duration_min: Optional[int] = None
    note: str = ""


class StepUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    order_no: Optional[int] = None
    duration_min: Optional[int] = None
    note: Optional[str] = None


class StepOut(ORMModel):
    id: int
    experiment_id: int
    title: str
    status: str
    order_no: int
    duration_min: Optional[int] = None
    note: str


class ExperimentTemplateCreate(BaseModel):
    title: str
    category: str = "其他"
    body: dict = {}


class ExperimentTemplateOut(ORMModel):
    id: int
    title: str
    category: str
    body: dict
    created_at: datetime


class CommentCreate(BaseModel):
    content: str


class CommentOut(ORMModel):
    id: int
    experiment_id: int
    content: str
    created_at: datetime


# ---------------- V5：集合 / 手动关联 / 保存视图 ----------------
class CollectionCreate(BaseModel):
    name: str


class CollectionOut(ORMModel):
    id: int
    name: str


class RelatedLink(BaseModel):
    reference_id: int


class SavedViewCreate(BaseModel):
    name: str
    filters: dict = {}


# ---------------- V5：资源库存 ----------------
class ResourceCreate(BaseModel):
    name: str
    rtype: str = "试剂"
    quantity: float = 0
    unit: str = "个"
    low_threshold: Optional[float] = None
    location: str = ""
    expiry_date: Optional[date] = None
    status: str = "正常"
    notes: str = ""


class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    rtype: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    low_threshold: Optional[float] = None
    location: Optional[str] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ResourceOut(ORMModel):
    id: int
    name: str
    rtype: str
    quantity: float
    unit: str
    low_threshold: Optional[float] = None
    location: str
    expiry_date: Optional[date] = None
    status: str
    notes: str


# ---------------- V5：画布 ----------------
class CanvasNodeCreate(BaseModel):
    ntype: str = "text"
    title: str
    ref_id: Optional[int] = None
    x: float = 0
    y: float = 0
    w: float = 180
    h: float = 90


class CanvasNodeUpdate(BaseModel):
    title: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None


class CanvasNodeOut(ORMModel):
    id: int
    canvas_id: int
    ntype: str
    title: str
    ref_id: Optional[int] = None
    x: float
    y: float
    w: float
    h: float


class CanvasEdgeCreate(BaseModel):
    from_node: int
    to_node: int


class CanvasEdgeOut(ORMModel):
    id: int
    canvas_id: int
    from_node: int
    to_node: int


# ---------------- V5：统一模板 ----------------
class TemplateCreate(BaseModel):
    ttype: str = "实验"
    name: str
    content: dict = {}


class TemplateOut(ORMModel):
    id: int
    ttype: str
    name: str
    content: dict
