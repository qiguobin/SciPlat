"""文件存储抽象层。

一期使用本地磁盘；二期如需远端存储（S3 等）或与 AI 技能链对接，
保持 save / abs_path / delete / read 接口不变即可替换实现。
"""
import uuid
from pathlib import Path

from .. import config


class LocalStorage:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file_data: bytes, original_name: str) -> tuple[str, str]:
        """保存文件，返回 (相对路径, 安全文件名)。"""
        folder = uuid.uuid4().hex
        safe_name = Path(original_name).name or "file"
        target = self.base_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / safe_name).write_bytes(file_data)
        return f"{folder}/{safe_name}", safe_name

    def abs_path(self, rel: str) -> Path:
        p = (self.base_dir / rel).resolve()
        if not p.is_relative_to(self.base_dir.resolve()):
            raise ValueError("非法存储路径")
        return p

    def read(self, rel: str) -> bytes:
        return self.abs_path(rel).read_bytes()

    def delete(self, rel: str) -> None:
        p = self.abs_path(rel)
        if p.exists():
            p.unlink()
        try:
            p.parent.rmdir()  # 清理空文件夹
        except OSError:
            pass


storage = LocalStorage(config.FILES_DIR)
