"""数据助手 - 异常处理示例"""

import csv

def read_csv_safe(file_path: str) -> list[dict]:
    """
    安全地读取 CSV 文件。
    如果文件不存在，不会崩溃，而是返回空列表并记录错误。
    """
    rows: list[dict] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

    except FileNotFoundError:
        #捕获文件不存在错误
        print(f"[错误]文件不存在：{file_path}")
        print(f"[提示]请检查文件路径是否正确")
    
    except PermissionError:
        #捕获“没有权限文件”
        print(f"[错误]没有权限读取文件: {file_path}")

    except Exception as e:
        #捕获所有其它意外错误
        print(f"[未知错误]{type(e).__name__}: {e}")
    else:
        print(f"[成功]读取了{len(rows)}行数据")
    finally:
        print(f"[结束]read_csv_safe执行完毕")
    return rows


def divide(a: float, b: float) -> float:
    if b==0:
        raise ValueError("除数不能为0")
    return a / b
