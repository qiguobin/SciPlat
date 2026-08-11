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
