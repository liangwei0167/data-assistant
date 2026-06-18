#!/bin/bash
# 数智助手 - 一键启动脚本

source venv/bin/activate
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-76bc13bcc8444432aebb3915de225238}"

echo "🚀 启动数智助手..."
echo ""

# 启动后端
echo "📡 启动 FastAPI 后端 (端口 8000)..."
uvicorn src.data_assistant.app:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

sleep 2

# 启动前端
echo "🌐 启动 Streamlit 前端 (端口 8501)..."
streamlit run streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false &
FRONTEND_PID=$!

echo ""
echo "============================================"
echo "  ✅ 数智助手 已启动"
echo "  🌐 打开浏览器: http://localhost:8501"
echo "  📊 API 文档:   http://localhost:8000/docs"
echo "  👤 默认账号:   admin / admin123"
echo "============================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '已停止'" EXIT
wait
