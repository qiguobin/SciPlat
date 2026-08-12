"""数据库引擎与会话管理。"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _pragmas(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# 引擎代际计数：切换工作区（rebind）后递增，供后台线程检测引擎已更换
_engine_gen = 0


def rebind() -> None:
    """切换数据目录（工作区）后重建引擎/SessionLocal，并完成完整初始化（建表/迁移/FTS）。

    所有函数内 `from .database import SessionLocal` 的引用点（get_db、_log_system_event、
    tracker 线程等）会在下次执行 import 语句时自动拿到新实例。
    """
    global engine, SessionLocal, _engine_gen
    try:
        engine.dispose()  # 释放旧库连接（WAL 落盘）
    except Exception:
        pass
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{config.DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _pragmas)  # 重新注册 pragma 监听（事件绑定旧 engine 对象）
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _engine_gen += 1
    init_db()
    try:
        rebuild_fts()
    except Exception:
        pass


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# V2/V3 列级迁移：SQLite 的 create_all 不会给已有表加列，这里启动时检查并 ALTER
# 注意：字典键不能重复（references 曾出现两次导致前一组列被覆盖），已合并为一项
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "references": [
        ("category", "VARCHAR(50) NOT NULL DEFAULT '其他'"),
        ("quartile", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("journal_if", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("fulltext_source", "VARCHAR(10) NOT NULL DEFAULT ''"),
        ("reading_progress", "INTEGER NOT NULL DEFAULT 0"),
        ("queue_priority", "INTEGER NOT NULL DEFAULT 0"),
        ("queue_date", "DATE"),
        ("jcr_quartile", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("cas_quartile", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("xinrui_quartile", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ],
    "group_meetings": [
        ("project_id", "INTEGER"),
        ("meeting_type", "VARCHAR(20) NOT NULL DEFAULT '组会'"),
        ("status", "VARCHAR(20) NOT NULL DEFAULT '已安排'"),
        ("attendees", "VARCHAR(500) NOT NULL DEFAULT ''"),
        ("duration_min", "INTEGER"),
        ("agenda", "TEXT NOT NULL DEFAULT ''"),
    ],
    "phase_experiments": [
        ("purpose", "TEXT NOT NULL DEFAULT ''"),
        ("method", "TEXT NOT NULL DEFAULT ''"),
        ("result", "TEXT NOT NULL DEFAULT ''"),
        ("conclusion", "TEXT NOT NULL DEFAULT ''"),
        ("reflection", "TEXT NOT NULL DEFAULT ''"),
        ("material_ids", "VARCHAR(500) NOT NULL DEFAULT ''"),
        ("hypothesis", "TEXT NOT NULL DEFAULT ''"),
        ("variables", "TEXT NOT NULL DEFAULT ''"),
        ("controls", "TEXT NOT NULL DEFAULT ''"),
    ],
    "todos": [
        ("repeat", "VARCHAR(10) NOT NULL DEFAULT 'none'"),
    ],
    "writing_logs": [
        ("section_id", "INTEGER"),
    ],
    "achievements": [
        ("file_name", "VARCHAR(300)"),
        ("stored_path", "VARCHAR(500)"),
    ],
    "milestones": [
        ("goal", "TEXT NOT NULL DEFAULT ''"),
        ("scope", "TEXT NOT NULL DEFAULT ''"),
        ("progress", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "papers": [
        ("paper_scale", "VARCHAR(20) NOT NULL DEFAULT '小论文'"),
    ],
    "paper_sections": [
        ("content", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def _migrate() -> None:
    with engine.begin() as conn:
        for table, columns in _MIGRATIONS.items():
            # references 是 SQLite 保留字，表名必须加双引号
            existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table}")'))}
            for col, ddl in columns:
                if col not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {col} {ddl}'))


def init_db():
    from . import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
    _migrate()
    _ensure_fts()


# ================ FTS5 全文检索（trigram 支持中文） ================
def _ensure_fts() -> None:
    """建 refs_fts 虚拟表 + 触发器同步（references / reference_texts 增删改）。"""
    # references 为 SQLite 保留字，一律加双引号
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS refs_fts USING fts5("
            "ref_id UNINDEXED, title, authors, venue, tags, doi, body, tokenize='trigram')"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_ai AFTER INSERT ON \"references\" BEGIN "
            "INSERT INTO refs_fts(ref_id, title, authors, venue, tags, doi, body) "
            "VALUES (NEW.id, NEW.title, NEW.authors, NEW.venue, NEW.tags, NEW.doi, ''); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_ad AFTER DELETE ON \"references\" BEGIN "
            "DELETE FROM refs_fts WHERE ref_id = OLD.id; END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_au AFTER UPDATE ON \"references\" BEGIN "
            "UPDATE refs_fts SET title=NEW.title, authors=NEW.authors, venue=NEW.venue, "
            "tags=NEW.tags, doi=NEW.doi WHERE ref_id=OLD.id; END"
        ))
        # reference_texts 增删改 → 同步正文（前 8000 字符）
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_ti AFTER INSERT ON reference_texts BEGIN "
            "UPDATE refs_fts SET body = substr(COALESCE(NEW.summary,'') || ' ' || COALESCE(NEW.text,''), 1, 8000) "
            "WHERE ref_id = NEW.reference_id; END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_tu AFTER UPDATE ON reference_texts BEGIN "
            "UPDATE refs_fts SET body = substr(COALESCE(NEW.summary,'') || ' ' || COALESCE(NEW.text,''), 1, 8000) "
            "WHERE ref_id = NEW.reference_id; END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS refs_fts_td AFTER DELETE ON reference_texts BEGIN "
            "UPDATE refs_fts SET body = '' WHERE ref_id = OLD.reference_id; END"
        ))


def rebuild_fts() -> int:
    """全量重建 FTS 索引（启动后调用一次保证存量数据入库）。返回索引条数。"""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM refs_fts"))
        conn.execute(text(
            "INSERT INTO refs_fts(ref_id, title, authors, venue, tags, doi, body) "
            "SELECT r.id, r.title, r.authors, r.venue, r.tags, r.doi, "
            "substr(COALESCE(t.summary,'') || ' ' || COALESCE(t.text,''), 1, 8000) "
            "FROM \"references\" r LEFT JOIN reference_texts t ON t.reference_id = r.id"
        ))
        row = conn.execute(text("SELECT count(*) FROM refs_fts")).scalar()
    return int(row or 0)
