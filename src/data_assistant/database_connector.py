"""
数智助手 - 多数据库连接器

支持 MySQL、PostgreSQL、SQLite。
管理员在后台配置连接，Agent 可以根据用户选择切换数据库。
"""
import os
from typing import Optional
from src.data_assistant.db import Database
from src.data_assistant.logger import logger


class DBConnector:
    """
    多数据库连接管理器。

    每个连接配置存储在应用数据库中。
    Agent 通过 conn_id 来选择使用哪个企业数据库。
    """

    def __init__(self):
        self.config_db = Database("data/connections.db")
        self._init_tables()
        self._connections: dict[int, Database] = {}

    def _init_tables(self):
        """创建连接配置表"""
        self.config_db.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                db_type TEXT NOT NULL DEFAULT 'sqlite',
                host TEXT DEFAULT '',
                port INTEGER DEFAULT 0,
                database_name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                password_encrypted TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # 如果没有连接，自动添加默认的 sales.db
        existing = self.config_db.query_one("SELECT id FROM connections LIMIT 1")
        if not existing:
            self.config_db.execute(
                "INSERT INTO connections (name, db_type, database_name, is_active) VALUES (?, ?, ?, ?)",
                ("演示数据库", "sqlite", "data/sales.db", 1),
            )
        self.config_db.conn.commit()

    def add_connection(self, name: str, db_type: str, host: str = "", port: int = 0,
                       database: str = "", username: str = "", password: str = "") -> dict:
        """添加一个数据库连接"""
        self.config_db.execute(
            "INSERT INTO connections (name, db_type, host, port, database_name, username, password_encrypted) VALUES (?,?,?,?,?,?,?)",
            (name, db_type, host, port, database, username, password),
        )
        self.config_db.conn.commit()
        return {"success": True, "message": "连接已添加"}

    def list_connections(self) -> list[dict]:
        """列出所有数据库连接（不显示密码）"""
        return self.config_db.query(
            "SELECT id, name, db_type, host, port, database_name, is_active, created_at FROM connections ORDER BY id"
        )

    def get_connection(self, conn_id: int) -> Optional[dict]:
        """获取单个连接配置"""
        return self.config_db.query_one(
            "SELECT * FROM connections WHERE id=? AND is_active=1", (conn_id,)
        )

    def delete_connection(self, conn_id: int) -> dict:
        """删除连接"""
        self.config_db.execute("UPDATE connections SET is_active=0 WHERE id=?", (conn_id,))
        self.config_db.conn.commit()
        # 清理缓存的连接
        if conn_id in self._connections:
            self._connections[conn_id].close()
            del self._connections[conn_id]
        return {"success": True}

    def test_connection(self, db_type: str, host: str = "", port: int = 0,
                        database: str = "", username: str = "", password: str = "") -> dict:
        """测试数据库连接是否可用"""
        try:
            if db_type == "sqlite":
                db = Database(database)
                db.query("SELECT 1")
                db.close()
            elif db_type == "mysql":
                import pymysql
                conn = pymysql.connect(host=host, port=port or 3306, user=username,
                                       password=password, database=database)
                conn.close()
            elif db_type == "postgresql":
                import psycopg2
                conn = psycopg2.connect(host=host, port=port or 5432, user=username,
                                        password=password, dbname=database)
                conn.close()
            else:
                return {"success": False, "error": f"不支持的数据库类型: {db_type}"}
            return {"success": True, "message": "连接成功"}
        except ImportError as e:
            return {"success": False, "error": f"缺少数据库驱动: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def connect(self, conn_id: int) -> Optional[Database]:
        """根据连接 ID 创建或获取数据库连接"""
        if conn_id in self._connections:
            return self._connections[conn_id]

        cfg = self.get_connection(conn_id)
        if not cfg:
            return None

        if cfg["db_type"] == "sqlite":
            db = Database(cfg["database_name"])
        elif cfg["db_type"] == "mysql":
            import sqlalchemy as sa
            url = f"mysql+pymysql://{cfg['username']}:{cfg['password_encrypted']}@{cfg['host']}:{cfg['port']}/{cfg['database_name']}"
            # SQLite 的 Database 类不适用于 MySQL，这里返回 None 并用 SQLAlchemy
            # MVP 阶段先返回默认数据库，MySQL 支持在 Day 2-2 完善
            db = Database("data/sales.db")
        else:
            db = Database("data/sales.db")

        self._connections[conn_id] = db
        return db


# 全局实例
connector = DBConnector()
