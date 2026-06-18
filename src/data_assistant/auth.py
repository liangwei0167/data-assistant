"""
数智助手 - 用户认证模块

支持：
- 本地账号（用户名/密码 PBKDF2-SHA256）
- LDAP/AD 对接（企业账号体系）
- JWT Token 鉴权
"""
import os
import hashlib
import secrets
import binascii
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from src.data_assistant.db import Database
from src.data_assistant.logger import logger

# ===== 密码哈希 =====
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2:sha256:100000${salt}${binascii.hexlify(h).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, pw = stored.split("$")
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return binascii.hexlify(h).decode() == pw
    except Exception:
        return False


# ===== JWT =====
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def create_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ===== 用户数据库 =====
class UserDB:
    def __init__(self):
        self.db = Database("data/users.db")
        self._init_tables()
        self._ensure_admin()

    def _init_tables(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                department TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                auth_source TEXT DEFAULT 'local',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.db.conn.commit()

    def _ensure_admin(self):
        e = self.db.query_one("SELECT id FROM users WHERE role='admin'")
        if not e:
            self.db.execute(
                "INSERT INTO users (username, password_hash, display_name, role) VALUES (?,?,?,?)",
                ("admin", hash_password("admin123"), "管理员", "admin"),
            )
            self.db.conn.commit()
            logger.info("已创建默认管理员: admin / admin123")

    def create_user(self, username, password, display_name="", role="user", department=""):
        if self.db.query_one("SELECT id FROM users WHERE username=?", (username,)):
            return {"success": False, "error": "用户名已存在"}
        self.db.execute(
            "INSERT INTO users (username, password_hash, display_name, role, department) VALUES (?,?,?,?,?)",
            (username, hash_password(password), display_name, role, department),
        )
        self.db.conn.commit()
        return {"success": True}

    def get_user(self, username):
        return self.db.query_one("SELECT * FROM users WHERE username=? AND is_active=1", (username,))

    def get_all_users(self):
        return self.db.query("SELECT id,username,display_name,role,department,auth_source,is_active,created_at FROM users ORDER BY id")

    def update_user(self, user_id, **kw):
        for k in ["display_name", "department", "role", "is_active"]:
            if k in kw:
                self.db.execute(f"UPDATE users SET {k}=? WHERE id=?", (kw[k], user_id))
        self.db.conn.commit()
        return {"success": True}

    def delete_user(self, user_id):
        self.db.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
        self.db.conn.commit()
        return {"success": True}

    def verify(self, username, password):
        u = self.get_user(username)
        if not u: return None
        if not check_password(password, u["password_hash"]): return None
        return u


# ===== LDAP =====
class LDAPAuth:
    def __init__(self, server="", base_dn="", admin_dn="", admin_password=""):
        self.server = server

    def authenticate(self, username, password):
        return None  # MVP: 回退本地认证


# ===== 全局实例 =====
user_db = UserDB()
ldap_auth = LDAPAuth(
    os.getenv("LDAP_SERVER", ""),
    os.getenv("LDAP_BASE_DN", ""),
    os.getenv("LDAP_ADMIN_DN", ""),
    os.getenv("LDAP_ADMIN_PASSWORD", ""),
)
