"""LLM 方案 api_key 加解密：前端 jsencrypt(RSA) 传输 → 后端私钥解密 → Fernet 落库加密；使用时内存解密。

密钥管理：环境变量 LLM_PROFILE_PRIVATE_KEY / LLM_PROFILE_STORAGE_KEY 优先；否则首次启动自动生成，
持久化到 <项目根>/data/llm_profile_keys.json（gitignore），重启不失效。真实部署（如 Docker 无持久卷）
应显式配置环境变量，否则容器重建后旧密文不可解。
"""

import base64
import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_KEYS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "llm_profile_keys.json"

_lock = threading.Lock()
_state: dict | None = None


def _load_or_create() -> dict:
    private_key_pem = os.getenv("LLM_PROFILE_PRIVATE_KEY", "")
    storage_key = os.getenv("LLM_PROFILE_STORAGE_KEY", "")
    if not private_key_pem or not storage_key:
        if _KEYS_FILE.exists():
            saved = json.loads(_KEYS_FILE.read_text(encoding="utf-8"))
            private_key_pem = private_key_pem or saved.get("private_key_pem", "")
            storage_key = storage_key or saved.get("storage_key", "")
    if not private_key_pem or not storage_key:
        if not private_key_pem:
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            private_key_pem = private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode()
        if not storage_key:
            storage_key = Fernet.generate_key().decode()
        _KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEYS_FILE.write_text(
            json.dumps({"private_key_pem": private_key_pem, "storage_key": storage_key}),
            encoding="utf-8",
        )
    return {"private_key_pem": private_key_pem, "storage_key": storage_key}


def _ensure() -> dict:
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                _state = _load_or_create()
    return _state


def _private_key():
    pem = _ensure()["private_key_pem"]
    return serialization.load_pem_private_key(pem.encode(), password=None)


def _fernet() -> Fernet:
    return Fernet(_ensure()["storage_key"].encode())


def get_public_key_pem() -> str:
    """前端 jsencrypt 加密用的 RSA 公钥（公开信息）。"""
    return _private_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def decrypt_transit(ciphertext_b64: str) -> str:
    """解密前端 jsencrypt 传输的 RSA 密文（base64）；非法输入抛 ValueError。"""
    plaintext = _private_key().decrypt(base64.b64decode(ciphertext_b64), padding.PKCS1v15())
    return plaintext.decode()


def encrypt_storage(plaintext: str) -> str:
    """落库前加密（Fernet），返回 urlsafe base64 密文。"""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_storage(ciphertext: str) -> str:
    """使用时内存解密；密文非法抛 cryptography.fernet.InvalidToken。"""
    return _fernet().decrypt(ciphertext.encode()).decode()
