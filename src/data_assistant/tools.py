"""
数智助手 - 工具集

Agent 可以调用的所有工具：
- 安全 SQL 执行（只读，防注入）
- 图表生成（matplotlib）
- 分析报告生成
"""
import re
import io
import base64
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # 不需要显示器，后端生成图片
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from openai import OpenAI

from src.data_assistant.db import Database
from src.data_assistant.logger import logger


# ===== 查找中文字体 =====
def _find_chinese_font() -> Optional[str]:
    """在系统里找中文字体，找不到就用默认的"""
    for f in fm.fontManager.ttflist:
        if any(k in f.name.lower() for k in ["heiti", "pingfang", "noto sans cjk", "simhei", "microsoft yahei"]):
            return f.name
    return None

CN_FONT = _find_chinese_font()
if CN_FONT:
    plt.rcParams["font.family"] = CN_FONT
plt.rcParams["axes.unicode_minus"] = False  # 防止负号显示为方块


# ===== 禁止的 SQL 关键词 =====
FORBIDDEN_SQL = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class SafeSQL:
    """
    安全 SQL 执行器。

    只允许 SELECT 查询，禁止任何修改操作。
    同时在沙箱中执行——出错不影响主程序。
    """

    def __init__(self, db: Database):
        self.db = db

    def validate(self, sql: str) -> None:
        """检查 SQL 是否包含危险关键词。如果有，直接抛出异常拒绝执行"""
        if FORBIDDEN_SQL.search(sql):
            raise ValueError(f"禁止操作：SQL 包含不允许的关键词。只允许 SELECT 查询。SQL: {sql[:100]}")

    def execute(self, sql: str) -> dict:
        """
        执行一条只读 SQL 查询。

        返回格式：
            {"success": True, "columns": [...], "rows": [...], "row_count": N}
        或
            {"success": False, "error": "..."}
        """
        try:
            self.validate(sql)
            rows = self.db.query(sql)
            columns = list(rows[0].keys()) if rows else []
            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
        except Exception as e:
            logger.error(f"SQL 执行失败: {e}")
            return {"success": False, "error": str(e)}

    def get_schema(self) -> list[dict]:
        """获取所有表的列信息，Agent 靠这个理解数据库结构"""
        schemas = []
        for table in self.db.get_tables():
            schemas.append({
                "table": table,
                "columns": self.db.get_columns(table),
            })
        return schemas


class ChartGenerator:
    """
    图表生成器。

    根据查询结果自动生成图表，返回 base64 编码的 PNG 图片，
    可以直接嵌入前端页面。
    """

    @staticmethod
    def generate(data: dict, chart_type: str = "bar", title: str = "") -> str:
        """
        生成图表。

        参数：
            data: SQL 查询结果，格式 {"columns": [...], "rows": [...]}
            chart_type: 图表类型 (bar/line/pie/scatter)
            title: 图表标题

        返回：base64 编码的图片字符串，前端用 <img src="data:image/png;base64,..."> 显示
        """
        if not data.get("rows"):
            return ""

        rows = data["rows"]
        columns = data["columns"]

        fig, ax = plt.subplots(figsize=(10, 5))

        # 取第一列当 X 轴，后面的数值列当数据
        x = [row[columns[0]] for row in rows]

        if chart_type == "pie":
            values = [float(row[columns[1]]) if len(columns) > 1 else 1 for row in rows]
            ax.pie(values, labels=x, autopct="%1.1f%%")
            if title:
                ax.set_title(title)
        elif chart_type == "line":
            for i, col in enumerate(columns[1:], 1):
                values = [float(row[col]) if row[col] is not None else 0 for row in rows]
                ax.plot(x, values, marker="o", label=col)
            ax.legend()
            ax.set_title(title or "趋势图")
            plt.xticks(rotation=45)
        elif chart_type == "scatter":
            for i, col in enumerate(columns[1:], 1):
                x_vals = range(len(x))
                y_vals = [float(row[col]) if row[col] is not None else 0 for row in rows]
                ax.scatter(x_vals, y_vals, label=col)
            ax.set_xticks(range(len(x)))
            ax.set_xticklabels(x, rotation=45)
            ax.legend()
            ax.set_title(title or "散点图")
        else:  # bar
            for i, col in enumerate(columns[1:], 1):
                values = [float(row[col]) if row[col] is not None else 0 for row in rows]
                offset = (i - 1) * 0.2
                positions = [j + offset for j in range(len(x))]
                ax.bar(positions, values, width=0.2, label=col)
            ax.set_xticks(range(len(x)))
            ax.set_xticklabels(x, rotation=45)
            ax.legend()
            ax.set_title(title or "柱状图")

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()


class ReportGenerator:
    """
    分析报告生成器。

    把数据结果喂给 DeepSeek，生成结构化的分析报告。
    使用独立的 OpenAI 客户端，不依赖 Agent 的客户端。
    """

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, question: str, sql_result: dict, sql: str = "") -> str:
        """
        根据用户问题和数据结果生成分析报告。

        返回：Markdown 格式的分析文字
        """
        if not sql_result.get("rows"):
            return "暂无数据，无法生成分析报告。"

        rows_str = str(sql_result["rows"][:20])  # 最多取 20 行
        row_count = sql_result.get("row_count", 0)

        prompt = f"""你是一个专业的数据分析师。请根据以下信息，写一段简洁的分析报告（100-300字）。
用中文回复，直接写分析内容，不要写"分析报告"标题。

用户问题：{question}
执行SQL：{sql}
查询结果（共{row_count}行，展示前20行）：{rows_str}

分析要点：数据概览、关键发现、趋势或异常、建议。"""

        try:
            resp = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return f"报告生成失败：{e}"
