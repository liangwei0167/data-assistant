"""
数智助手 - AI Agent

核心引擎：DeepSeek + Function Calling

从 Vanna 学到的最重要思路：
1. 用 RAG 检索数据字典 → 拼入 LLM Prompt → SQL 更精准
2. Agent 不是一次性生成 SQL，而是可以多次调用工具、根据结果继续思考
3. 数据字典（DDL + 文档 + SQL 示例）是准确率的保证
"""
import json
from typing import Optional
from openai import OpenAI

from src.data_assistant.db import Database
from src.data_assistant.tools import SafeSQL, ChartGenerator, ReportGenerator
from src.data_assistant.rag import RAGService
from src.data_assistant.logger import logger


# ===== Agent 可用的工具定义（Function Calling Schema） =====
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "执行一条只读 SQL 查询，获取数据库中的数据。只允许 SELECT 语句。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL 查询语句。必须是 SELECT 语句。",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "获取数据库中所有表和列的结构信息。在不确定表名、列名时先调用这个。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": "根据 SQL 查询结果生成图表。用户要求画图、做可视化时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "用于获取图表数据的 SQL 查询。",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "scatter"],
                        "description": "图表类型：bar=柱状图, line=折线图, pie=饼图, scatter=散点图",
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题",
                    },
                },
                "required": ["sql", "chart_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "根据 SQL 查询结果生成数据分析报告。用户要求写分析、做总结时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "用于获取分析数据的 SQL 查询。",
                    },
                    "question": {
                        "type": "string",
                        "description": "用户最初的问题，用于确定分析角度。",
                    },
                },
                "required": ["sql", "question"],
            },
        },
    },
]


class DataAgent:
    """
    数智助手 Agent。

    工作流程：
    1. 用户输入问题
    2. RAG 检索相关数据字典片段
    3. 将问题 + 检索上下文 + 工具列表发给 DeepSeek
    4. DeepSeek 决定调用哪个工具（或直接回答）
    5. 执行工具，将结果发回 DeepSeek
    6. DeepSeek 生成最终回复（可能包含文字解读、图表、表格）

    借鉴 Vanna 的设计：
    - 数据字典存在 RAG 里，每次提问自动检索
    - Agent 拥有多个工具（查库、画图、写报告）
    - 所有 SQL 只读执行，安全可控
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

        # 工具
        self.db = Database("data/sales.db")
        self.sql_tool = SafeSQL(self.db)
        self.chart_tool = ChartGenerator()
        self.report_tool = ReportGenerator(api_key=api_key, base_url=base_url)

        # RAG（数据字典检索）
        self.rag = RAGService(api_key=api_key)

        # 对话历史
        self.messages: list[dict] = []

    def _build_system_prompt(self, user_question: str) -> str:
        """
        构建系统 Prompt。

        这是 Agent 的"大脑设定"——告诉它它是谁、能做什么、数据库长什么样、
        企业有哪些特殊规则。
        """
        # 1. 获取数据库结构
        schema_info = ""
        try:
            schemas = self.sql_tool.get_schema()
            for s in schemas:
                cols = ", ".join(f"{c['name']}({c['type']})" for c in s["columns"])
                schema_info += f"- {s['table']}: {cols}\n"
        except Exception:
            schema_info = "无法获取数据库结构"

        # 2. 检索数据字典（Vanna 的核心思路）
        rag_context = ""
        rag_items = self.rag.search(user_question, top_k=3)
        if rag_items:
            rag_context = "\n".join(
                f"[来源: {item['source']}] {item['content'][:300]}"
                for item in rag_items
            )

        prompt = f"""你是"数智助手"，一个企业级数据分析 AI。你的用户是不懂 SQL 的业务人员。

## 数据库结构
{schema_info}

## 企业数据字典（从上传的文档中检索，优先参考）
{rag_context if rag_context else "（暂无数据字典，请基于数据库结构推断）"}

## 核心规则
1. 只执行 SELECT 查询，不允许修改数据
2. 生成 SQL 前先参考数据字典——企业的表名、字段名、计算公式以字典为准
3. 如果用户问题模糊，先调用 get_database_schema 了解表结构再写 SQL
4. 查询结果用中文解读，让业务人员看得懂
5. 如果用户要求画图，调用 generate_chart
6. 如果用户要求写报告/分析，调用 generate_report
7. 不要暴露内部 SQL 给用户（除非用户明确问）
8. 数据为空时诚实地告诉用户，不要编造
9. 如果用户问的问题跟数据无关（比如闲聊），正常回复即可"""
        return prompt

    def chat(self, user_message: str, conversation_id: Optional[str] = None) -> dict:
        """
        处理一次用户对话。

        参数：
            user_message: 用户输入的自然语言

        返回：
            {
                "reply": "AI 的文字回复",
                "chart": "base64 图片或空字符串",
                "table": {"columns": [...], "rows": [...]} 或 None,
            }
        """
        logger.info(f"用户提问: {user_message[:100]}")

        # 构建消息列表
        system_prompt = self._build_system_prompt(user_message)
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        chart_b64 = ""
        table_data = None

        # 最多 5 轮工具调用（防止死循环）
        for _ in range(5):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOLS,
                    temperature=0.1,  # 低温度 = 更稳定可靠
                    max_tokens=2000,
                )
            except Exception as e:
                logger.error(f"DeepSeek API 调用失败: {e}")
                return {"reply": f"AI 服务暂时不可用，请稍后重试。错误：{e}", "chart": "", "table": None}

            choice = resp.choices[0]
            msg = choice.message

            # 如果 LLM 决定调用工具
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Agent 调用工具: {func_name}")

                    # 执行对应的工具
                    tool_result = self._execute_tool(func_name, func_args, user_message)

                    # 把工具调用和结果加入对话历史，让 LLM 知道发生了什么
                    self.messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                        ],
                    })
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                    })

                    # 如果是图表生成，保存图片数据
                    if func_name == "generate_chart" and "chart" in tool_result:
                        chart_b64 = tool_result["chart"]

                    # 如果是查询数据库，保存表格数据
                    if func_name == "query_database" and tool_result.get("success"):
                        table_data = {
                            "columns": tool_result.get("columns", []),
                            "rows": tool_result.get("rows", []),
                        }
            else:
                # LLM 直接返回文字回复，对话结束
                reply = msg.content or ""
                return {"reply": reply, "chart": chart_b64, "table": table_data}

        # 超过最大轮数
        return {"reply": "抱歉，处理您的请求需要太多步骤。请尝试说得更具体一些。", "chart": "", "table": None}

    def _execute_tool(self, func_name: str, args: dict, user_question: str) -> dict:
        """执行工具调用，返回结果字典"""
        try:
            if func_name == "query_database":
                result = self.sql_tool.execute(args["sql"])
                return result

            elif func_name == "get_database_schema":
                schemas = self.sql_tool.get_schema()
                return {"schemas": schemas}

            elif func_name == "generate_chart":
                sql_result = self.sql_tool.execute(args["sql"])
                if not sql_result.get("success"):
                    return {"error": sql_result.get("error", "查询失败")}

                chart_type = args.get("chart_type", "bar")
                title = args.get("title", "")
                chart_b64 = self.chart_tool.generate(sql_result, chart_type, title)
                return {"chart": chart_b64, "data": sql_result}

            elif func_name == "generate_report":
                sql_result = self.sql_tool.execute(args["sql"])
                if not sql_result.get("success"):
                    return {"error": sql_result.get("error", "查询失败")}

                report = self.report_tool.generate(
                    question=args.get("question", user_question),
                    sql_result=sql_result,
                    sql=args["sql"],
                )
                return {"report": report, "data": sql_result}

            else:
                return {"error": f"未知工具: {func_name}"}

        except Exception as e:
            logger.error(f"工具执行失败 ({func_name}): {e}")
            return {"error": str(e)}

    def clear_history(self):
        """清除对话历史"""
        self.messages = []

    def get_conversation_title(self) -> str:
        """从第一轮对话生成会话标题"""
        if self.messages:
            first_msg = self.messages[1]["content"] if len(self.messages) > 1 else ""
            return first_msg[:30] + ("..." if len(first_msg) > 30 else "")
        return "新对话"
