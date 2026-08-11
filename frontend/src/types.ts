export interface Project {
  id: number
  title: string
  ptype: string
  status: string
  description: string
  start_date: string | null
  end_date: string | null
  created_at: string
  updated_at: string
  paper_count?: number
  material_count?: number
  milestone_count?: number
}

export interface Milestone {
  id: number
  project_id: number
  title: string
  due_date: string
  status: string
  note: string
  goal: string
  scope: string
  progress: number
}

export interface TimelinePoint {
  id: number
  project_id: number
  title: string
  point_date: string
  note: string
  sort_order: number
}

export interface ProjectDetail extends Project {
  milestones: Milestone[]
  timeline_points: TimelinePoint[]
  papers: Paper[]
  materials: Material[]
  phases: PhaseDetail[]
}

// ---------------- 项目阶段 ----------------
export interface Phase {
  id: number
  project_id: number
  name: string
  description: string
  start_date: string | null
  end_date: string | null
  status: string
  sort_order: number
  is_default: boolean
}

export interface Experiment {
  id: number
  phase_id: number
  title: string
  date: string
  purpose: string
  method: string
  result: string
  conclusion: string
  reflection: string
  hypothesis: string
  variables: string
  controls: string
  material_ids: string
  created_at: string
}

export interface PhaseDetail extends Phase {
  experiments: Experiment[]
  reference_ids: number[]
  todo_ids: number[]
}

// ---------------- 学生档案 ----------------
export interface Profile {
  id: number
  name: string
  student_id: string
  school: string
  college: string
  major: string
  advisor: string
  research_direction: string
  enrollment_year: number | null
  expected_graduation: number | null
  contact: string
  photo_path: string | null
  updated_at: string
}

// ---------------- 待办 ----------------
export interface Todo {
  id: number
  date: string
  title: string
  description: string
  status: string
  priority: string
  project_id: number | null
  project_title: string | null
  repeat: string
  created_at: string
  completed_at: string | null
}

// ---------------- 日程 ----------------
export interface ScheduleSummary {
  period: string
  label: string
  stats: {
    todos_done: number
    todos_pending: number
    experiments: number
    refs_added: number
    writing_days: number
    writing_total: number
    phases_done: number
  }
  sections: { title: string; items: string[] }[]
  markdown: string
  ai?: boolean
}

export interface SchedulePhaseOverview {
  project_id: number
  project_title: string
  phases: { id: number; name: string; status: string; sort_order: number }[]
  done: number
  total: number
}

export interface HeatmapData {
  year: number
  days: { date: string; count: number }[]
}

// ---------------- 成果 ----------------
export interface Achievement {
  id: number
  synced?: boolean
  atype: string
  title: string
  status: string
  date: string | null
  venue: string
  identifier: string
  authors: string
  detail: string
  link: string
  notes: string
  file_name: string | null
}

// ---------------- 灵感 ----------------
export interface Idea {
  id: number
  content: string
  tags: string
  status: string
  created_at: string
}

// ---------------- 导师沟通 ----------------
export interface AdvisorMeeting {
  id: number
  date: string
  topic: string
  summary: string
  action_items: string[]
  created_at: string
}

// ---------------- 写作打卡 ----------------
export interface WritingLog {
  id: number
  date: string
  paper_id: number | null
  word_count: number
  note: string
}

// ---------------- 文献增强 ----------------
export interface ReferenceTextInfo {
  id: number
  reference_id: number
  text: string
  summary: string
  keywords: string
  extracted_at: string
}

export interface Paper {
  id: number
  title: string
  project_id: number | null
  project_title?: string | null
  paper_type: string
  paper_scale: string
  abstract: string
  keywords: string
  status: string
  target_journal: string
  journal_quartile: string
  journal_if: string
  submission_deadline: string | null
  created_at: string
  updated_at: string
}

export interface PaperVersion {
  id: number
  paper_id: number
  version_no: number
  file_name: string
  file_size: number
  changelog: string
  created_at: string
}

export interface ReviewRound {
  id: number
  paper_id: number
  round_no: number
  decision: string
  summary: string
  review_date: string | null
  file_name: string | null
}

export interface PaperDetail extends Paper {
  versions: PaperVersion[]
  review_rounds: ReviewRound[]
  next_statuses: string[]
  sections: PaperSection[]
}

export interface PaperSection {
  id: number
  paper_id: number
  title: string
  order_no: number
  target_words: number
  status: string
  content: string
  written_words: number
}

// ---------------- 文献增强 V3 ----------------
export interface DeepReading {
  id: number
  reference_id: number
  question: string
  method: string
  conclusion: string
  insight: string
  updated_at: string
}

export interface DuplicateGroup {
  ids: number[]
  reason: string
}

export interface TimelineEvent {
  date: string
  type: 'phase' | 'milestone' | 'deadline' | 'todo'
  title: string
  status: string
  link: string
}

export interface NoteGraphData {
  nodes: { key: string; label: string; kind: string }[]
  links: { source: string; target: string }[]
}

// ---------------- V4 类型 ----------------
export interface ProjectReview {
  id: number
  project_id: number
  goal_achievement: string
  difficulties: string
  lessons: string
  reusable_methods: string
}

export interface ProjectRisk {
  id: number
  project_id: number
  phase_id: number | null
  title: string
  severity: string
  status: string
  resolution: string
  created_at: string
  resolved_at: string | null
}

export interface PhaseSuggestion {
  phase_id: number
  phase_name: string
  experiments: number
  tasks_done: number
  tasks_total: number
  task_rate: number
  suggestion: string
  next_phase_id: number | null
  next_phase_name: string | null
}

export interface Journal {
  id: number
  name: string
  quartile: string
  impact_factor: string
  review_weeks: number | null
  notes: string
}

export interface StatusLog {
  id: number
  paper_id: number
  from_status: string
  to_status: string
  created_at: string
}

export interface QueueItem {
  id: number
  title: string
  year: number | null
  venue: string
  queue_priority: number
  queue_date: string | null
  read_status: string
  reading_progress: number
}

export interface PdfAnnotation {
  id: number
  reference_id: number
  page: number
  color: string
  rect: string
  note: string
  created_at: string
}

export interface MaterialVersion {
  id: number
  material_id: number
  version_no: number
  file_name: string
  size: number
  created_at: string
}

export interface Material {
  id: number
  project_id: number | null
  project_title?: string | null
  category: string
  name: string
  description: string
  tags: string
  file_name: string
  size: number
  mime: string
  created_at: string
}

export interface Reference {
  id: number
  title: string
  authors: string[]
  year: number | null
  venue: string
  doi: string
  bibkey: string
  tags: string
  read_status: string
  category: string
  quartile: string
  journal_if: string
  jcr_quartile: string
  cas_quartile: string
  xinrui_quartile: string
  fulltext_source: string
  reading_progress: number
  file_name: string | null
  created_at: string
  updated_at: string
}

export interface Note {
  id: number
  target_type: string
  target_id: number
  content: string
  created_at: string
  updated_at: string
}

export interface DeadlineItem {
  type: 'milestone' | 'journal'
  title: string
  extra: string
  date: string
  link: string
  days_left: number
}

export interface Stats {
  projects: { total: number; by_status: Record<string, number> }
  papers: { total: number; by_status: Record<string, number> }
  references: { total: number; read: Record<string, number> }
  materials: { total: number; total_size: number }
  deadlines: DeadlineItem[]
  recent: { kind: string; id: number; title: string; updated_at: string }[]
}

export interface SearchResults {
  projects: { id: number; title: string; status: string }[]
  papers: { id: number; title: string; status: string }[]
  materials: { id: number; name: string; category: string }[]
  references: { id: number; title: string; read_status: string }[]
}

// ---------------- 关联图谱 ----------------
export interface NetworkNode {
  id: number
  title: string
  tags: string
  read_status: string
  author_count: number
}

export interface NetworkLink {
  source: number
  target: number
  weight: number
  factors: string[]
  citation: boolean
  ai?: boolean
  reason?: string
  ai_tags?: string[]
}

export interface NetworkData {
  nodes: NetworkNode[]
  links: NetworkLink[]
}

export interface NetworkStats {
  node_count: number
  link_count: number
  citation_link_count: number
  citations_fetched: number
  citation_records: number
}

export const FACTOR_LABELS: Record<string, string> = {
  tags: '共享标签',
  authors: '共享作者',
  venue: '同期刊/会议',
  year: '年份相近',
  citation: '引用关系',
  related: '手动关联',
  ai: 'AI 语义关联',
}

// ---------------- V5 类型 ----------------
export interface ExperimentStep {
  id: number
  experiment_id: number
  title: string
  status: string
  order_no: number
  duration_min: number | null
  note: string
}

export interface ExperimentTemplate {
  id: number
  title: string
  category: string
  body: {
    purpose?: string
    method?: string
    hypothesis?: string
    variables?: string
    controls?: string
    steps?: { title: string; duration_min?: number }[]
  }
}

export interface ExperimentComment {
  id: number
  experiment_id: number
  content: string
  created_at: string
}

export interface Collection {
  id: number
  name: string
  count: number
}

export interface SavedView {
  id: number
  name: string
  filters: Record<string, string>
}

export interface LabResource {
  id: number
  name: string
  rtype: string
  quantity: number
  unit: string
  low_threshold: number | null
  location: string
  expiry_date: string | null
  status: string
  notes: string
}

export interface CanvasNode {
  id: number
  canvas_id: number
  ntype: string
  title: string
  ref_id: number | null
  x: number
  y: number
  w: number
  h: number
}

export interface CanvasEdge {
  id: number
  canvas_id: number
  from_node: number
  to_node: number
}

export interface CanvasData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

export interface Template {
  id: number
  ttype: string
  name: string
  content: Record<string, unknown>
}
