"""pytest 全局配置：在导入 app 之前设置独立临时数据目录，每个测试用全新数据库。"""
import os
import tempfile

import pytest

os.environ["SCI_DATA_DIR"] = tempfile.mkdtemp(prefix="sciplat-test-")


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试开始前重建全部表，保证测试互相隔离、顺序无关。"""
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
