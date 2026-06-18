"""
数智助手 - RAG 检索服务

从 Vanna 学到的核心思路：
1. 企业上传数据字典（表结构说明、字段含义、业务公式）
2. 文档分块 → 向量化 → 存入 ChromaDB
3. 用户提问时，检索最相关的元数据片段
4. 拼入 LLM 的 Prompt，让生成的 SQL 更精准
"""
import os
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI

from src.data_assistant.logger import logger


# ===== 文档解析器 =====
def parse_pdf(file_path: str) -> str:
    """解析 PDF 文件的文本"""
    from PyPDF2 import PdfReader
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(file_path: str) -> str:
    """解析 Word 文件的文本"""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs)


def parse_excel(file_path: str) -> str:
    """解析 Excel 文件，把每个 sheet 的内容转成文本"""
    import pandas as pd
    xl = pd.ExcelFile(file_path)
    parts = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet)
        parts.append(f"=== Sheet: {sheet} ===\n{df.to_string()}")
    return "\n\n".join(parts)


def parse_txt(file_path: str) -> str:
    """解析纯文本文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": parse_docx,
    ".xlsx": parse_excel,
    ".xls": parse_excel,
    ".txt": parse_txt,
    ".md": parse_txt,
    ".csv": parse_txt,
}


class RAGService:
    """
    数据字典检索服务。

    跟 Vanna 的 train() 一样：把企业文档切片 → 转向量 → 存 ChromaDB。
    用户提问时检索最相关的上下文，Agent 用它来生成精准 SQL。

    与 Vanna 的区别：
    - Vanna 用 ChromaDB + SentenceTransformer 做 Embedding
    - 我们用 DeepSeek Embedding API（中文效果更好）
    """

    def __init__(self, api_key: str, persist_dir: str = "data/rag_db"):
        self.api_key = api_key
        self.persist_dir = persist_dir
        self.openai_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        # 创建 ChromaDB 客户端
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)

        # 创建或获取 collection
        self.collection = self.client.get_or_create_collection(
            name="data_dictionary",
            metadata={"description": "企业数据字典和业务规则文档"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """
        用 DeepSeek Embedding 把文本转成向量。

        DeepSeek 的 Embedding 对中文理解好，比 SentenceTransformer 更准。
        """
        resp = self.openai_client.embeddings.create(
            model="text-embedding-ada-002",  # 兼容的 embedding 模型名
            input=texts,
        )
        return [d.embedding for d in resp.data]

    def add_document(self, file_path: str) -> dict:
        """
        添加一个文档到知识库。

        流程：解析文件 → 分块 → 向量化 → 存入 ChromaDB
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext not in PARSERS:
            return {"success": False, "error": f"不支持的格式：{ext}"}

        try:
            content = PARSERS[ext](file_path)
        except Exception as e:
            return {"success": False, "error": f"文件解析失败：{e}"}

        if not content.strip():
            return {"success": False, "error": "文件内容为空"}

        # 分块——每 500 字符一块，重叠 100 字符
        chunks = []
        chunk_size = 500
        overlap = 100
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunks.append(content[start:end])
            start += chunk_size - overlap

        if not chunks:
            return {"success": False, "error": "分块失败"}

        # 批量向量化 + 存储
        try:
            # 对每个文本块生成 embedding
            embeddings = []
            for i in range(0, len(chunks), 20):  # 分批，避免请求过大
                batch = chunks[i : i + 20]
                batch_embeddings = self._embed(batch)
                embeddings.extend(batch_embeddings)

            # 写入 ChromaDB
            self.collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=[f"{os.path.basename(file_path)}_{i}" for i in range(len(chunks))],
                metadatas=[{"source": os.path.basename(file_path)} for _ in chunks],
            )
        except Exception as e:
            return {"success": False, "error": f"向量化失败：{e}"}

        logger.info(f"文档 {os.path.basename(file_path)} 已索引：{len(chunks)} 个片段")
        return {
            "success": True,
            "chunks": len(chunks),
            "filename": os.path.basename(file_path),
        }

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        检索与用户问题最相关的数据字典片段。

        返回：[{"content": "...", "source": "..."}, ...]
        """
        if self.collection.count() == 0:
            return []

        try:
            query_embedding = self._embed([query])
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, self.collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            items = []
            if results["documents"] and results["documents"][0]:
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    items.append({
                        "content": doc,
                        "source": meta.get("source", "未知"),
                        "score": round(1 - dist, 4) if dist else 0,  # 距离转相似度
                    })
            return items
        except Exception as e:
            logger.error(f"RAG 检索失败: {e}")
            return []

    def get_document_count(self) -> int:
        """返回已索引的文档片段数"""
        return self.collection.count()

    def clear(self):
        """清空知识库，重新开始"""
        self.client.delete_collection("data_dictionary")
        self.collection = self.client.get_or_create_collection(name="data_dictionary")
