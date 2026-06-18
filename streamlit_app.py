"""
数智助手 - Streamlit 网页

启动：streamlit run streamlit_app.py --server.port 8501 --server.headless true
"""
import streamlit as st
import requests
import base64
import pandas as pd
import time

# ===== 配置 =====
st.set_page_config(page_title="数智助手", page_icon="📊", layout="wide")

API = "http://127.0.0.1:8000"

# ===== 初始化 session =====
if "token" not in st.session_state:
    st.session_state.token = ""
if "username" not in st.session_state:
    st.session_state.username = ""
if "role" not in st.session_state:
    st.session_state.role = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "page" not in st.session_state:
    st.session_state.page = "login"

headers = {"Authorization": f"Bearer {st.session_state.token}"}

# ===== 登录页 =====
def login_page():
    st.markdown("# 🔢 数智助手")
    st.markdown("### 企业级 AI 数据分析平台")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("用户名", placeholder="请输入企业账号")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        if st.button("登  录", use_container_width=True, type="primary"):
            try:
                resp = requests.post(f"{API}/api/auth/login", json={
                    "username": username, "password": password
                }, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.token = data["token"]
                    st.session_state.username = data["username"]
                    st.session_state.role = data["role"]
                    st.session_state.page = "chat"
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
            except requests.exceptions.ConnectionError:
                st.error("无法连接后端服务，请先启动 FastAPI")
        st.caption("默认管理员：admin / admin123")

# ===== 对话页 =====
def chat_page():
    with st.sidebar:
        st.markdown(f"## 👤 {st.session_state.username}")
        st.caption(f"角色：{st.session_state.role}")
        st.markdown("---")

        # 管理入口
        if st.session_state.role == "admin":
            if st.button("⚙️ 管理后台", use_container_width=True):
                st.session_state.page = "admin"
                st.rerun()

        st.markdown("---")

        # 引导问题
        st.markdown("### 💡 试试这些")
        suggestions = [
            "各个产品总共卖了多少件？",
            "画一个产品销量柱状图",
            "写一个销售分析报告",
            "价格超过200的产品有哪些？",
        ]
        for s in suggestions:
            if st.button(s, key=f"sug_{s[:15]}"):
                st.session_state.pending_input = s
                st.rerun()

        st.markdown("---")
        if st.button("🗑️ 清除对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
        if st.button("🚪 退出登录", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    # 主聊天区
    st.markdown("## 📊 数智助手")
    st.caption("用自然语言与企业数据对话")

    # 渲染历史
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(content)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.write(content.get("reply", ""))
                if content.get("table"):
                    df = pd.DataFrame(content["table"]["rows"])
                    if not df.empty:
                        st.dataframe(df, use_container_width=True)
                if content.get("chart"):
                    st.image(base64.b64decode(content["chart"]), caption="图表", use_container_width=True)

    # 输入
    user_input = st.chat_input("输入你的问题...")
    if "pending_input" in st.session_state:
        user_input = st.session_state.pending_input
        del st.session_state.pending_input

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.write(user_input)
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("思考中..."):
                try:
                    resp = requests.post(f"{API}/api/chat",
                        json={"message": user_input}, timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.write(data["reply"])
                        if data.get("table"):
                            df = pd.DataFrame(data["table"]["rows"])
                            if not df.empty:
                                st.dataframe(df, use_container_width=True)
                        if data.get("chart"):
                            st.image(base64.b64decode(data["chart"]), caption="图表", use_container_width=True)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": {"reply": data["reply"], "chart": data.get("chart", ""), "table": data.get("table")},
                        })
                    else:
                        st.error(f"请求失败：{resp.text}")
                except Exception as e:
                    st.error(f"连接失败：{e}")

# ===== 管理后台 =====
def admin_page():
    st.markdown("## ⚙️ 管理后台")
    with st.sidebar:
        if st.button("💬 返回对话", use_container_width=True):
            st.session_state.page = "chat"
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["📡 数据库连接", "📚 数据字典", "👥 用户管理", "🔑 LDAP配置"])

    with tab1:
        st.markdown("### 数据库连接管理")
        try:
            connections = requests.get(f"{API}/api/admin/connections", timeout=5).json()
            for conn in connections:
                cols = st.columns([3, 1, 1])
                cols[0].write(f"**{conn['name']}** ({conn['db_type']}) - {conn.get('host','')}:{conn.get('port','')}")
                cols[1].write("✅ 已连接" if conn.get("is_active") else "❌ 未连接")
                if cols[2].button("删除", key=f"del_{conn['id']}"):
                    requests.delete(f"{API}/api/admin/connections/{conn['id']}")
                    st.rerun()
        except Exception as e:
            st.warning(f"加载失败: {e}")

        with st.expander("+ 添加连接"):
            name = st.text_input("连接名称", key="conn_name")
            db_type = st.selectbox("数据库类型", ["mysql", "postgresql", "sqlite"], key="conn_type")
            host = st.text_input("主机地址", key="conn_host")
            port = st.number_input("端口", value=3306, key="conn_port")
            database = st.text_input("数据库名", key="conn_db")
            username = st.text_input("用户名", key="conn_user")
            password = st.text_input("密码", type="password", key="conn_pass")
            col1, col2 = st.columns(2)
            if col1.button("测试连接"):
                r = requests.post(f"{API}/api/admin/connections/test", json={
                    "name": name, "db_type": db_type, "host": host, "port": port,
                    "database": database, "username": username, "password": password,
                }).json()
                if r["success"]:
                    st.success("✅ 连接成功")
                else:
                    st.error(f"❌ {r['error']}")
            if col2.button("保存连接", type="primary"):
                requests.post(f"{API}/api/admin/connections", json={
                    "name": name, "db_type": db_type, "host": host, "port": port,
                    "database": database, "username": username, "password": password,
                })
                st.success("已保存")
                st.rerun()

    with tab2:
        st.markdown("### 数据字典管理")
        st.info("上传企业的数据字典文档（表结构说明、字段含义、计算公式等），帮助 AI 更精准地理解你的数据库。")
        uploaded_file = st.file_uploader("上传文档", type=["pdf", "docx", "xlsx", "txt", "md", "csv"])
        if uploaded_file:
            import os, tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
                tmp.write(uploaded_file.read())
                result = requests.post(f"{API}/api/rag/upload?file_path={tmp.name}").json()
                os.unlink(tmp.name)
                if result.get("success"):
                    st.success(f"✅ 已索引 {result['chunks']} 个片段")
                else:
                    st.error(f"❌ {result['error']}")

        status = requests.get(f"{API}/api/rag/status").json()
        st.metric("已索引文档片段", status.get("document_count", 0))

    with tab3:
        st.markdown("### 用户管理")
        users = requests.get(f"{API}/api/admin/users").json()
        for u in users:
            cols = st.columns([2, 1, 1, 1])
            cols[0].write(f"**{u['username']}** ({u.get('display_name','')})")
            cols[1].write(u['role'])
            cols[2].write("✅" if u.get('is_active') else "❌")
            if cols[3].button("删除", key=f"deluser_{u['id']}"):
                requests.delete(f"{API}/api/admin/users/{u['id']}")
                st.rerun()

        with st.expander("+ 添加用户"):
            uname = st.text_input("用户名", key="new_user")
            upass = st.text_input("密码", type="password", key="new_pass")
            udisplay = st.text_input("显示名称", key="new_display")
            urole = st.selectbox("角色", ["user", "admin"], key="new_role")
            if st.button("创建用户"):
                r = requests.post(f"{API}/api/admin/users", json={
                    "username": uname, "password": upass, "display_name": udisplay, "role": urole,
                }).json()
                if r.get("success"):
                    st.success("已创建")
                    st.rerun()
                else:
                    st.error(r.get("error", "失败"))

    with tab4:
        st.markdown("### LDAP/AD 配置")
        st.info("对接企业 Active Directory，员工使用企业账号登录。")
        ldap_server = st.text_input("LDAP 服务器地址", "ldap://192.168.1.1:389")
        ldap_base = st.text_input("Base DN", "dc=company,dc=com")
        ldap_admin = st.text_input("管理员 DN", "cn=admin,dc=company,dc=com")
        ldap_pass = st.text_input("管理员密码", type="password")
        if st.button("测试 LDAP 连接"):
            st.warning("LDAP 测试需要 ldap3 库，请在 PRD 中查看完整对接方案")
        st.caption("MVP 阶段：LDAP 配置保存到 .env 文件，服务重启后生效。")

# ===== 路由 =====
if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "chat":
    chat_page()
elif st.session_state.page == "admin":
    admin_page()
