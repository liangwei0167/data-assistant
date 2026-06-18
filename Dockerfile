FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY src/ src/
COPY streamlit_app.py .
COPY start.sh .

# 暴露端口
EXPOSE 8000 8501

CMD ["bash", "start.sh"]
