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