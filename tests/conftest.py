"""测试环境：隔离 PostgreSQL 测试库并提供 LLM 密钥。"""
import os

import psycopg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ["DATABASE_URL"] = "postgresql+asyncpg://ynfight:ynfight@localhost:5432/ynfight_test"
os.environ["DB_POOL_ENABLED"] = "false"
# 限流阈值在测试中放开：TestClient 同源 IP 共享计数，避免与业务断言无关的 429；
# 限流行为本身由对运行实例的手动验收覆盖（见 docs/plans/2026-09-12-hardening-p0.md）。
os.environ["RATELIMIT_LOGIN"] = "10000/minute"
os.environ["RATELIMIT_REGISTER"] = "10000/minute"
os.environ["RATELIMIT_CHALLENGE"] = "10000/minute"
private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
os.environ["LLM_PROFILE_PRIVATE_KEY"] = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
os.environ["LLM_PROFILE_STORAGE_KEY"] = Fernet.generate_key().decode()
try:
    admin_conn = psycopg.connect("postgresql://ynfight:ynfight@localhost:5432/postgres", autocommit=True)
    admin_conn.execute("DROP DATABASE IF EXISTS ynfight_test WITH (FORCE)")
    admin_conn.execute("CREATE DATABASE ynfight_test")
    admin_conn.close()
except psycopg.Error as exc:
    raise RuntimeError("测试需要本地 Docker PostgreSQL") from exc
