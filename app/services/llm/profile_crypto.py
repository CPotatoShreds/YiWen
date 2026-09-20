"""LLM 方案 api_key 加解密：前端 jsencrypt(RSA) 传输 → 后端私钥解密 → Fernet 落库加密；使用时内存解密。

密钥管理：`LLM_PROFILE_PRIVATE_KEY` / `LLM_PROFILE_STORAGE_KEY` 配置项（.env 或环境变量）优先，
PEM 中的换行可写作字面 `\\n`；否则首次使用时自动生成，持久化到 app/data/llm_profile_keys.json
（gitignore）供本地开发零配置。生产/Docker 部署应显式配置——容器重建会丢文件，旧密文不可解。
"""

import base64
import json
import threading
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import get_settings

_KEYS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "llm_profile_keys.json"

_lock = threading.Lock()
_state: dict | None = None


def _configured_keys() -> tuple[str, str]:
    """从配置读取显式密钥，统一还原为 PEM 形态。

    私钥支持两种写法：完整 PEM（含首尾行），或仅 base64 主体（.env 单行友好——
    纯字母数字，无空格/横线/换行，不会被 dotenv 解析器截断）。
    """
    s = get_settings()
    private_key_pem = s.LLM_PROFILE_PRIVATE_KEY.strip().replace("\\n", "\n")
    if private_key_pem and not private_key_pem.startswith("-----BEGIN"):
        body = "".join(private_key_pem.split())
        lines = [body[i : i + 64] for i in range(0, len(body), 64)]
        private_key_pem = (
            "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
        )
    return private_key_pem, s.LLM_PROFILE_STORAGE_KEY


def _load_or_create() -> dict:
    private_key_pem, storage_key = _configured_keys()
    if (not private_key_pem or not storage_key) and _KEYS_FILE.exists() and _KEYS_FILE.stat().st_size > 0:
        # 空文件（写入中断残留）视同不存在：重新生成并覆盖，避免 json.loads 抛错卡死整域
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
