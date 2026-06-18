# ============================================
# Day 3 任务：db.py（数据库操作模块）
# 文件位置：src/data_assistant/db.py
# ============================================

"""
数据助手 - 数据库操作模块

这个模块的作用是：
封装所有数据库操作，让后面的 SQL Agent 通过调用这些函数来操作数据库，
而不是直接写 SQL——这样更安全，也更容易维护。

整个项目的数据库操作都通过这一个模块来完成：
创建表、插入数据、查询数据、获取表结构信息。
"""

import sqlite3
# sqlite3 是 Python 内置的 SQLite 数据库模块，不需要 pip install
# SQLite 是"嵌入式数据库"——不需要装服务器，数据库就是一个 .db 文件

from pathlib import Path
# Path 是面向对象的文件路径工具
# 用 Path("data") / "sales.db" 代替 "data/sales.db"，更清晰，跨平台

from typing import Optional
# Optional[str] 表示"可能是 str，也可能是 None"
# 用在这里：查询时可能查到结果，也可能查不到（返回 None）


class Database:
    """
    数据库操作类

    为什么要用类？
    因为一个数据库连接（conn）需要在整个生命周期中保持打开，
    用类来管理它——打开连接、执行查询、关闭连接——最合适。

    后面 Sprint 4 的 SQL Agent 会直接使用这个类的实例来操作数据库。

    使用示例：
        db = Database("data/sales.db")          # 1. 创建实例，连上数据库
        db.create_tables()                      # 2. 创建表（如果还不存在）
        rows = db.query("SELECT * FROM products") # 3. 执行查询
        db.close()                              # 4. 关闭连接
    """

    def __init__(self, db_path: str):
        """
        初始化方法——创建 Database 对象时自动调用。

        参数：
            db_path: 数据库文件的路径，比如 "data/sales.db"

        做了什么：
            1. 把路径存到 self.db_path，方便后续使用
            2. 如果数据库文件所在的目录不存在，自动创建
            3. 连接到 SQLite 数据库文件（如果文件不存在，SQLite 会自动创建）
        """
        self.db_path = Path(db_path)
        # Path(db_path) → 把字符串路径转成 Path 对象
        # self.db_path → self 表示"这个对象自己的属性"
        # 类的每个方法里，self 代表当前对象本身
        # 比如 db = Database("data/sales.db")，那么 db 就是 self

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # .parent → 获取父目录，比如 Path("data/sales.db").parent → Path("data")
        # .mkdir(parents=True, exist_ok=True)
        #   → 创建目录，parents=True 表示上级目录不存在也一并创建
        #   → exist_ok=True 表示目录已存在也不报错

        self.conn = sqlite3.connect(str(self.db_path))
        # sqlite3.connect() → 连接到 SQLite 数据库文件
        # 如果文件不存在，SQLite 会自动创建
        # 把 Path 对象转回字符串（sqlite3 不认识 Path 对象，只认字符串）

        self.conn.row_factory = sqlite3.Row
        # row_factory → 控制查询结果每一行的"包装方式"
        # 默认是元组 → (1, '键盘', 299.0)，只能靠位置访问 row[0], row[1]
        # 改成 sqlite3.Row → 可以像字典一样用列名访问 row["name"], row["price"]
        # 这是 Python 风格的查询结果，可读性大幅提升

    def execute(self, sql: str, params: Optional[tuple] = None):
        """
        执行一条 SQL 语句（INSERT、UPDATE、DELETE 等不返回数据的操作）。

        参数：
            sql: 要执行的 SQL 语句，比如 "INSERT INTO products VALUES (?, ?, ?)"
            params: SQL 语句中 ? 占位符对应的值
                    用 ? 而不是直接拼接字符串，可以防止 SQL 注入攻击

        为什么用 ? 占位符？
            坏写法：f"INSERT INTO products VALUES ({id}, '{name}', {price})"
                   如果 name 是 "键盘'; DROP TABLE products;--"，
                   整个表就被删了——这就是 SQL 注入。
            好写法：sql = "INSERT INTO products VALUES (?, ?, ?)"
                   params = (4, '键盘', 299)
                   数据库自动转义特殊字符，安全。

        返回：游标对象，可以通过它获取 lastrowid（最后插入的行 id）
        """
        if params is None:
            # 如果 params 没传（就是 None），直接执行 SQL
            return self.conn.execute(sql)
        else:
            # 如果传了 params，把 params 里的值填到 SQL 的 ? 位置，然后执行
            return self.conn.execute(sql, params)

    def query(self, sql: str, params: Optional[tuple] = None) -> list[dict]:
        """
        执行一条 SELECT 查询，返回结果列表。

        参数：
            sql: 查询 SQL 语句
            params: 占位符参数

        返回：
            一个列表，每个元素是一个字典（代表一行数据）
            比如 [{"name": "键盘", "price": 299}, {"name": "鼠标", "price": 149}]

        为什么返回 list[dict] 而不是 sqlite3 原始结果？
            1. 字典比原始 Row 对象更容易序列化（转 JSON 给前端用）
            2. Agent 的 function calling 需要 JSON 格式的数据
            3. 外面用的人不需要知道底层是 sqlite3
        """
        if params is None:
            cursor = self.conn.execute(sql)
            # 没参数，直接执行
        else:
            cursor = self.conn.execute(sql, params)
            # 有参数，把参数填到 ? 里再执行

        # 下面是把原始查询结果转成 list[dict] 的过程
        rows = cursor.fetchall()
        # cursor.fetchall() → 取出所有查询结果
        # 因为设置了 row_factory = sqlite3.Row，
        # 每行是一个 Row 对象，可以用 row["列名"] 访问

        return [dict(row) for row in rows]
        # 这是一个"列表推导式"（list comprehension）
        # 翻译成 for 循环就是：
        #   result = []
        #   for row in rows:
        #       result.append(dict(row))
        #   return result
        # dict(row) → 把每行的 Row 对象转成 Python 字典

    def query_one(self, sql: str, params: Optional[tuple] = None) -> Optional[dict]:
        """
        执行查询，只返回第一行。适合"按 id 查找某条记录"。

        返回：
            一个字典（如果找到了），或者 None（如果没找到）
        """
        if params is None:
            cursor = self.conn.execute(sql)
        else:
            cursor = self.conn.execute(sql, params)

        row = cursor.fetchone()
        # cursor.fetchone() → 只取第一行结果
        # 如果查询没结果，返回 None

        if row is None:
            return None
            # 没查到数据，返回 None（Python 里表示"空"）
        return dict(row)
        # 查到了，把 Row 对象转成字典返回

    def get_tables(self) -> list[str]:
        """
        获取数据库里所有表的名字。

        用途：Agent 拿到一个陌生的数据库时，
        先调这个函数了解有哪些表、什么结构，再决定怎么查。
        """
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        # sqlite_master 是 SQLite 内置的系统表，记录了所有用户创建的表
        # SELECT name → 只要表名
        # WHERE type='table' → 过滤掉索引等其他对象，只要表
        # ORDER BY name → 按表名字母排序

        return [row["name"] for row in rows]
        # 列表推导式：把每行里的 "name" 值取出来，组成一个新列表
        # 比如 [{"name": "orders"}, {"name": "products"}] → ["orders", "products"]

    def get_columns(self, table_name: str) -> list[dict]:
        """
        获取某张表的列信息（列名、类型、是否允许为空等）。

        用途：Agent 需要知道表的列名才能写正确的 SELECT 语句。
        比如用户问"查销量"，Agent 要先知道表里有没有"销量"这一列。

        参数：
            table_name: 表名

        返回：
            列表，每个元素是一个字典，包含列名(name)、类型(type)、
            是否允许为空(notnull)、默认值(default)、是否主键(pk)
        """
        rows = self.query(f"PRAGMA table_info('{table_name}')")
        # PRAGMA table_info 是 SQLite 的特殊命令，获取表的列信息
        # 注意：这里 table_name 用 f-string 拼进去是安全的，
        # 因为 table_name 不是用户直接输入的，而是我们先从 get_tables() 拿到的系统表名
        # 如果是从用户输入直接拼接，必须用 ? 占位符防注入

        columns = []
        # 新建一个空列表，装结果

        for row in rows:
            # 遍历 PRAGMA 返回的每一列信息
            columns.append({
                "name": row["name"],
                # 列名，比如 "id"、"product_id"、"quantity"
                "type": row["type"],
                # 列的数据类型，比如 "INTEGER"、"TEXT"、"REAL"
                "notnull": bool(row["notnull"]),
                # 是否 NOT NULL（不允许为空），转成 Python 的 True/False
                "default": row["dflt_value"],
                # 默认值，如果建表时没设默认值，就是 None
                "pk": bool(row["pk"]),
                # 是否是主键（PRIMARY KEY），同样转成 True/False
            })

        return columns

    def close(self):
        """
        关闭数据库连接。

        每次用完数据库后都应该调用 close()，释放系统资源。
        虽然程序退出时 Python 会自动关闭连接，
        但显式关闭是好习惯——特别是数据写入后需要 close() 来确保数据真正落到磁盘。
        """
        self.conn.close()
        # conn.close() → 关闭 SQLite 连接
        # 关闭后不能再执行查询，除非重新 connect()


# ============================================
# 下面是"直接运行此文件时"的测试代码
# ============================================
if __name__ == "__main__":
    """
    如果直接运行 python -m src.data_assistant.db，会执行下面的测试代码。
    如果别人 import 这个模块（from src.data_assistant.db import Database），
    下面的代码不会执行——因为 __name__ 不等于 "__main__"。
    """

    # ===== 创建示例数据库 =====
    db = Database("data/sales.db")
    # 创建一个 Database 实例，数据库文件存在 data/sales.db
    # 如果文件不存在，sqlite3 会自动创建一个空数据库
    # data/ 目录如果不存在，__init__ 里也会自动创建

    # ===== 创建表 =====
    db.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    # CREATE TABLE IF NOT EXISTS → 如果表已经存在，就不重复创建
    # 这样测试代码可以多次运行，不会第一次之后都报错

    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # ===== 插入数据 =====
    # 先检查是否已有数据，避免重复插入
    existing = db.query("SELECT COUNT(*) AS count FROM products")
    # SELECT COUNT(*) → 统计行数
    # AS count → 结果起别名 count，方便后面 data["count"] 访问

    if existing[0]["count"] == 0:
        # 表是空的，插入初始数据

        db.execute("INSERT INTO products VALUES (1, '键盘', 299)")
        db.execute("INSERT INTO products VALUES (2, '鼠标', 149)")
        db.execute("INSERT INTO products VALUES (3, '显示器', 1299)")

        db.execute("INSERT INTO orders VALUES (1, 1, 5, '2026-05-01')")
        db.execute("INSERT INTO orders VALUES (2, 2, 3, '2026-05-03')")
        db.execute("INSERT INTO orders VALUES (3, 1, 2, '2026-05-05')")
        db.execute("INSERT INTO orders VALUES (4, 3, 1, '2026-05-07')")
        db.execute("INSERT INTO orders VALUES (5, 2, 10, '2026-05-10')")

        # 提交事务
        db.conn.commit()
        # SQLite 默认是事务模式：INSERT 之后数据没有立刻写入磁盘
        # commit() 才真正把数据写进去

    # ===== 测试查询 =====
    print("=" * 40)
    print("1. 所有产品：")
    products = db.query("SELECT * FROM products")
    # 查询 products 表的所有行
    for p in products:
        # 遍历每个产品，用列名访问字段
        print(f"  ID: {p['id']}, 名称: {p['name']}, 价格: ¥{p['price']}")

    print()
    # 空行，让输出更好看

    print("=" * 40)
    print("2. 各产品总销量：")
    sales = db.query("""
        SELECT p.name, SUM(o.quantity) AS total_qty
        FROM products p
        INNER JOIN orders o ON p.id = o.product_id
        GROUP BY p.name
        ORDER BY total_qty DESC
    """)
    # 这里有新玩法——为表起别名：
    #   FROM products p → 把 products 表简称为 p
    #   INNER JOIN orders o → 把 orders 表简称为 o
    # 好处：不用写 products.name，直接 p.name，简洁很多
    for s in sales:
        print(f"  {s['name']}: {s['total_qty']} 件")

    print()
    print("=" * 40)
    print("3. 数据库里的表：")
    tables = db.get_tables()
    # 调用我们自己写的方法，获取所有表名
    for t in tables:
        print(f"  表名: {t}")
        columns = db.get_columns(t)
        # 获取每张表的列信息
        for col in columns:
            pk_mark = " [主键]" if col["pk"] else ""
            # 如果是主键，后面标 [主键]
            print(f"    - {col['name']} ({col['type']}){pk_mark}")

    print()
    print("=" * 40)
    print("4. 单行查询测试：")
    product = db.query_one("SELECT * FROM products WHERE id = ?", (1,))
    # 查找 id=1 的产品
    # (1,) 是一个单元素元组，逗号不能省——没有逗号就是普通的括号 (1)
    print(f"  {product}")

    not_found = db.query_one("SELECT * FROM products WHERE id = ?", (999,))
    # 查找 id=999 的产品 → 不存在，返回 None
    print(f"  查不存在的 id 返回: {not_found}")

    # ===== 关闭连接 =====
    db.close()
    print()
    print("数据库连接已关闭。")


# ============================================
# 测试命令（在终端执行）
# ============================================
# python -m src.data_assistant.db
