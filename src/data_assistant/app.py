"""
数智助手 - FastAPI 应用入口

启动：uvicorn src.data_assistant.app:app --reload
文档：http://localhost:8000/docs
"""
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from pydantic import BaseModel

from src.data_assistant.db import Database
from src.data_assistant.agent import DataAgent
from src.data_assistant.rag import RAGService
from src.data_assistant.auth import user_db, ldap_auth, create_token, decode_token
from src.data_assistant.database_connector import connector
from src.data_assistant.logger import logger

# ===== 配置 =====
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ===== 应用实例 =====
app = FastAPI(
    title="数智助手 API",
    description="企业级 AI 数据分析助手",
    version="1.0.0",
)

# 允许跨域（Streamlit 前端需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 服务实例 =====
db = Database("data/sales.db")
agent = DataAgent(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
rag = RAGService(api_key=DEEPSEEK_API_KEY)


# ===== 请求/响应模型 =====
class ChatRequest(BaseModel):
    message: str
    conversation_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    chart: str = ""  # base64 图片
    table: Optional[dict] = None  # {"columns": [...], "rows": [...]}


class DBConfigRequest(BaseModel):
    db_type: str  # mysql, postgresql, sqlite
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""


# ===== 健康检查 =====
@app.get("/")
def read_root():
    return {"message": "数智助手 API 运行中", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "rag_documents": rag.get_document_count(),
    }


# ===== 核心对话接口 =====
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Agent 对话接口——整个产品的核心。

    接收用户的自然语言问题，Agent 自动：
    1. 检索数据字典
    2. 决定查数据库 / 画图 / 写报告
    3. 返回结果（文字 + 可选图表 + 可选表格）
    """
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="请先设置 DEEPSEEK_API_KEY 环境变量")

    try:
        result = agent.chat(request.message)
        return ChatResponse(
            reply=result["reply"],
            chart=result.get("chart", ""),
            table=result.get("table"),
        )
    except Exception as e:
        logger.error(f"对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")


@app.post("/api/chat/clear")
def clear_chat():
    """清除对话历史"""
    agent.clear_history()
    return {"status": "ok"}


# ===== 数据字典管理 =====
@app.post("/api/rag/upload")
def upload_document(file_path: str):
    """
    上传数据字典文档。

    参数：file_path - 文档的本地路径
    返回：索引结果（成功/失败、片段数）
    """
    result = rag.add_document(file_path)
    return result


@app.get("/api/rag/status")
def rag_status():
    """查看数据字典状态"""
    return {
        "document_count": rag.get_document_count(),
        "persist_dir": rag.persist_dir,
    }


# ===== 数据库产品接口（保留原有的） =====
class ProductResponse(BaseModel):
    id: int
    name: str
    price: float


class SalesSummary(BaseModel):
    name: str
    total_qty: int


class CreateProductRequest(BaseModel):
    name: str
    price: float


@app.get("/api/products", response_model=list[ProductResponse])
def get_products():
    return db.query("SELECT id, name, price FROM products ORDER BY id")


@app.get("/api/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int):
    row = db.query_one("SELECT id, name, price FROM products WHERE id = ?", (product_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"产品 ID {product_id} 不存在")
    return row


@app.get("/api/sales", response_model=list[SalesSummary])
def get_sales():
    return db.query("""
        SELECT p.name, SUM(o.quantity) AS total_qty
        FROM products p
        INNER JOIN orders o ON p.id = o.product_id
        GROUP BY p.name
        ORDER BY total_qty DESC
    """)


@app.post("/api/products", response_model=ProductResponse, status_code=201)
def create_product(request: CreateProductRequest):
    cursor = db.execute(
        "INSERT INTO products (name, price) VALUES (?, ?)",
        (request.name, request.price),
    )
    db.conn.commit()
    new_id = cursor.lastrowid
    return db.query_one("SELECT id, name, price FROM products WHERE id = ?", (new_id,))


# ==========================================
# 认证相关接口
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    display_name: str = ""


@app.post("/api/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """用户登录——先试 LDAP，再试本地账号"""
    # 先尝试 LDAP
    ldap_user = ldap_auth.authenticate(request.username, request.password)
    if ldap_user:
        token = create_token(ldap_user.get("id", 0), request.username, ldap_user.get("role", "user"))
        return LoginResponse(token=token, username=request.username,
                             role=ldap_user.get("role", "user"),
                             display_name=ldap_user.get("display_name", ""))

    # 回退到本地账号
    user = user_db.verify(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(user["id"], user["username"], user["role"])
    return LoginResponse(token=token, username=user["username"],
                         role=user["role"], display_name=user.get("display_name", ""))


# ==========================================
# 管理员接口
# ==========================================

class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "user"
    department: str = ""


@app.get("/api/admin/users")
def list_users():
    return user_db.get_all_users()


@app.post("/api/admin/users")
def create_user(request: CreateUserRequest):
    result = user_db.create_user(request.username, request.password,
                                  request.display_name, request.role, request.department)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, role: str = "", is_active: bool = True):
    kwargs = {}
    if role:
        kwargs["role"] = role
    kwargs["is_active"] = 1 if is_active else 0
    user_db.update_user(user_id, **kwargs)
    return {"success": True}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int):
    user_db.delete_user(user_id)
    return {"success": True}


# ==========================================
# 数据库连接管理接口
# ==========================================

class ConnectionRequest(BaseModel):
    name: str
    db_type: str = "sqlite"
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""


@app.get("/api/admin/connections")
def list_connections():
    return connector.list_connections()


@app.post("/api/admin/connections")
def add_connection(request: ConnectionRequest):
    return connector.add_connection(request.name, request.db_type, request.host,
                                     request.port, request.database, request.username,
                                     request.password)


@app.delete("/api/admin/connections/{conn_id}")
def delete_connection(conn_id: int):
    return connector.delete_connection(conn_id)


@app.post("/api/admin/connections/test")
def test_connection(request: ConnectionRequest):
    return connector.test_connection(request.db_type, request.host, request.port,
                                      request.database, request.username, request.password)


# ==========================================
# 数据字典管理接口
# ==========================================

@app.post("/api/rag/upload")
def upload_document(file_path: str):
    return rag.add_document(file_path)


@app.get("/api/rag/status")
def rag_status():
    return {"document_count": rag.get_document_count()}
