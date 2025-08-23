# main.py
import streamlit as st
import sqlite3
import bcrypt
from datetime import datetime
import pandas as pd

# ===============================
# CONFIGURAÇÕES
# ===============================
st.set_page_config(page_title="Mão Amiga • PIX", page_icon="🤝", layout="wide")
APP_NAME = "Mão Amiga"

STAGE_AMOUNTS = {1: 50, 2: 100, 3: 300}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12

# ===============================
# BANCO (SQLite)
# ===============================
def get_conn():
    conn = sqlite3.connect("app.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            full_name TEXT,
            pix_key TEXT,
            stage INTEGER NOT NULL DEFAULT 1,
            received_stage_donations INTEGER NOT NULL DEFAULT 0,
            indicador_id INTEGER,
            created_at TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            stage INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()

def db_execute(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    return cur

def db_query(query, params=(), as_df=False):
    conn = get_conn()
    if as_df:
        return pd.read_sql_query(query, conn, params=params)
    cur = conn.cursor()
    cur.execute(query, params)
    return cur.fetchall()

init_db()

# ===============================
# FUNÇÕES DE AUTENTICAÇÃO
# ===============================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_user(username, password, full_name):
    now = datetime.utcnow().isoformat()
    hashed_pw = hash_password(password)
    try:
        cur = db_execute("""
            INSERT INTO users (username, password_hash, full_name, indicador_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (username, hashed_pw, full_name, None, now))
        uid = cur.lastrowid
        # todo novo usuário vira indicador do seu criador? indicador_id será definido depois
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError:
        return False, "Usuário já existe."

def authenticate(username, password):
    row = db_query("SELECT id, username, password_hash, role, stage, received_stage_donations, indicador_id FROM users WHERE username = ?", (username,))
    if not row:
        return False, "Usuário não encontrado."
    uid, uname, phash, role, stage, recv, ind_id = row[0]
    if check_password(password, phash):
        return True, {"id": uid, "username": uname, "role": role, "stage": stage, "received_stage_donations": recv, "indicador_id": ind_id}
    return False, "Senha inválida."

# ===============================
# DOAÇÕES / INDICAÇÃO
# ===============================
def record_donation(from_uid):
    # pega indicador do usuário
    tgt = db_query("SELECT id FROM users WHERE id = (SELECT indicador_id FROM users WHERE id = ?)", (from_uid,))
    if not tgt:
        return False, "Você ainda não possui indicador definido."
    to_uid = tgt[0][0]
    u = db_query("SELECT stage, received_stage_donations FROM users WHERE id = ?", (to_uid,))[0]
    stage, recv = u
    amount = STAGE_AMOUNTS.get(stage, 50)
    now = datetime.utcnow().isoformat()
    db_execute("INSERT INTO donations(from_user_id, to_user_id, amount, stage, status, created_at) VALUES (?, ?, ?, ?, 'confirmed', ?)",
               (from_uid, to_uid, amount, stage, now))
    recv += 1
    if recv >= STAGE_TARGET_DONATIONS and stage < STAGE_MAX:
        db_execute("UPDATE users SET received_stage_donations = 0, stage = stage + 1 WHERE id = ?", (to_uid,))
    else:
        db_execute("UPDATE users SET received_stage_donations = ? WHERE id = ?", (recv, to_uid))
    return True, f"Doação registrada para usuário {to_uid}."

def list_indicados(uid):
    return db_query("SELECT id, username, full_name, stage FROM users WHERE indicador_id = ? ORDER BY id", (uid,), as_df=True)

# ===============================
# UI
# ===============================
def require_login():
    if "user" not in st.session_state or st.session_state["user"] is None:
        st.warning("Faça login para continuar.")
        st.stop()

def ui_sidebar_login():
    if "user" not in st.session_state:
        st.session_state["user"] = None

    st.sidebar.title(APP_NAME)
    if st.session_state["user"]:
        u = st.session_state["user"]
        st.sidebar.markdown(f"**{u['username']}**")
        if st.sidebar.button("Sair"):
            st.session_state["user"] = None
            st.experimental_rerun()  # se der problema, substituir por st.session_state['rerun'] = True
        st.sidebar.divider()
        st.sidebar.markdown("Menu principal")
        return

    st.sidebar.subheader("Login")
    login_user = st.sidebar.text_input("Usuário", key="login_u")
    login_pass = st.sidebar.text_input("Senha", type="password", key="login_p")
    if st.sidebar.button("Entrar"):
        ok, res = authenticate(login_user, login_pass)
        if ok:
            st.session_state["user"] = res
            st.experimental_rerun()
        else:
            st.error(res)

def page_home():
    st.title("Mão Amiga • PIX")
    st.write("Semear prosperidade e compartilhar abundância")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estágio 1", "R$ 50")
    c2.metric("Estágio 2", "R$ 100")
    c3.metric("Estágio 3", "R$ 300")
    st.caption("Receba 12 doações para subir de estágio.")

def page_register():
    st.header("Registrar Usuário")
    reg_user = st.text_input("Usuário", key="reg_user")
    reg_full = st.text_input("Nome completo", key="reg_full")
    reg_pass = st.text_input("Senha", type="password", key="reg_pass")
    if st.button("Registrar"):
        ok, msg = create_user(reg_user, reg_pass, reg_full)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

def page_dashboard():
    require_login()
    u = st.session_state["user"]
    st.header(f"Dashboard — {u['username']}")
    st.write(f"Stage atual: {u['stage']}")
    st.write(f"Doações recebidas: {u['received_stage_donations']}")
    if st.button("Registrar Doação"):
        ok, msg = record_donation(u["id"])
        if ok:
            st.success(msg)
        else:
            st.error(msg)
    st.markdown("---")
    indicados = list_indicados(u["id"])
    st.subheader("Seus Indicados")
    st.dataframe(indicados)

def page_admin():
    require_login()
    u = st.session_state["user"]
    if u["role"] != "admin":
        st.warning("Área restrita a administradores")
        st.stop()
    st.header("Painel Admin")
    df = db_query("SELECT id, username, full_name, stage FROM users", as_df=True)
    st.dataframe(df)
    del_user_id = st.number_input("ID do usuário para excluir", min_value=1, step=1)
    if st.button("Excluir Usuário"):
        db_execute("DELETE FROM users WHERE id = ?", (del_user_id,))
        st.success("Usuário excluído.")

# ===============================
# ROTEAMENTO
# ===============================
PAGES = {
    "Início": page_home,
    "Registrar": page_register,
    "Dashboard": page_dashboard,
    "Admin": page_admin
}

ui_sidebar_login()
choice = st.sidebar.selectbox("Menu", list(PAGES.keys()), index=0)
PAGES[choice]()
