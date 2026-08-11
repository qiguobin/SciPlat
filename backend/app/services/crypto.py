"""敏感信息加密：Fernet 密钥文件（数据目录 secret.key，随备份一起走）。

- API Key、WebDAV 密码等敏感设置以密文入库，读取时解密
- 密钥文件丢失后密文无法解密 → 提示重新配置（decrypt_text 返回空串）
- 备份密码加密：PBKDF2 从密码派生密钥（salt 前缀格式：salt16 + Fernet token）
"""
import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _key_path() -> Path:
    from .. import config

    return config.DATA_DIR / "secret.key"


def get_fernet() -> Fernet:
    """获取 Fernet 实例；密钥文件缺失时自动生成。"""
    p = _key_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(Fernet.generate_key())
    return Fernet(p.read_bytes())


def encrypt_text(plain: str) -> str:
    if not plain:
        return ""
    return get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""  # 密钥文件丢失或内容损坏 → 视为未配置，提示重新填写


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """密码加密数据：salt(16) + Fernet token。"""
    salt = os.urandom(16)
    f = Fernet(_derive_key(password, salt))
    return salt + f.encrypt(data)


def decrypt_bytes(data: bytes, password: str) -> bytes:
    """密码解密（encrypt_bytes 逆操作）；密码错误抛 InvalidToken。"""
    if len(data) < 16:
        raise InvalidToken("数据格式错误")
    salt, token = data[:16], data[16:]
    f = Fernet(_derive_key(password, salt))
    return f.decrypt(token)
