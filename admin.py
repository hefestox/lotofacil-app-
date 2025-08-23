# main.py
import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime
import bcrypt

# ===============================
# CONFIGURAÇÕES
# ===============================
st.set_page_config(page_title="Mão Amiga • PIX", page_icon="🤝", layout="wide")
APP_NAME = "Mão Amiga"
LOCAL_LOGO_REL = os.path.join("assets", "logo.png")

STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12  # tamanho do ciclo

# ===============================
# BANCO (SQLite)
# ===============================
@st.cache_resource
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
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            plan TEXT NOT NULL DEFAULT 'Bronze',
            full_name TEXT,
            pix_key TEXT,
            stage INTEGER NOT NULL DEFAULT 1,
            received_stage_donations INTEGER NOT NULL DEFAULT 0,
            referrer_id INTEGER,
            created_at TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
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
# AUTENTICAÇÃO / HELPERS
# ===============================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def log_action(user_id, action, payload=None):
    db_execute(
        "INSERT INTO audit(user_id, action, payload, created_at) VALUES (?,?,?,?)",
        (user_id, action, json.dumps(payload) if payload else None, datetime.utcnow().isoformat())
    )

def create_user(username: str, email: str, password: str, full_name: str, pix_key: str, referrer_username: str|None):
    now = datetime.utcnow().isoformat()
    ph = hash_password(password)
    ref_id = None
    if referrer_username:
        row = db_query("SELECT id FROM users WHERE username = ?", (referrer_username,))
        if row:
            ref_id = row[0][0]
    try:
        cur = db_execute(
            """INSERT INTO users (username, email, password_hash, role, plan, full_name, pix_key,
                                  stage, received_stage_donations, referrer_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (username, email, ph, "user", "Bronze", full_name, pix_key, 1, 0, ref_id, now)
        )
        uid = cur.lastrowid
        log_action(uid, "CREATE_USER", {"username": username, "referrer_id": ref_id})
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError as e:
        return False, f"Erro: usuário ou e-mail já existe. ({e})"

def get_user_by_username(username: str):
    rows = db_query("""
        SELECT id, username, email, password_hash, role, plan, full_name, pix_key, stage, received_stage_donations, referrer_id
        FROM users WHERE username = ?""", (username,))
    return rows[0] if rows else None

def get_user_by_id(uid: int):
    rows = db_query("""
        SELECT id, username, email, password_hash, role, plan, full_name, pix_key, stage, received_stage_donations, referrer_id
        FROM users WHERE id = ?""", (uid,))
    return rows[0] if rows else None

def authenticate(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return False, "Usuário não encontrado."
    uid, uname, email, phash, role, plan, full_name, pix_key, stage, recv, ref_id = user
    if check_password(password, phash):
        return True, {"id": uid, "username": uname, "email": email, "role": role, "plan": plan,
                      "full_name": full_name, "pix_key": pix_key,
                      "stage": stage, "received_stage_donations": recv, "referrer_id": ref_id}
    return False, "Senha inválida."

def require_login():
    if not st.session_state.get("user"):
        st.warning("Faça login para continuar.")
        st.stop()

def update_pix(uid: int, new_pix: str):
    db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, uid))
    log_action(uid, "UPDATE_PIX", {"pix": new_pix})
    return True, "Chave PIX atualizada."

def get_stage_amount(stage: int) -> float:
    return STAGE_AMOUNTS.get(stage, STAGE_AMOUNTS[1])

def get_donation_target(uid: int):
    row = db_query("""
        SELECT u2.id, u2.username, u2.full_name, u2.pix_key
        FROM users u1
        JOIN users u2 ON u1.referrer_id = u2.id
        WHERE u1.id = ?""", (uid,))
    return row[0] if row else None

def record_donation(from_uid: int):
    tgt = get_donation_target(from_uid)
    if not tgt:
        return False, "Você ainda não tem um indicador cadastrado."
    to_uid, to_username, to_full, to_pix = tgt
    u = get_user_by_id(from_uid)
    stage = u[8]  # stage index
    amount = get_stage_amount(stage)
    now = datetime.utcnow().isoformat()
    try:
        db_execute("""INSERT INTO donations(from_user_id, to_user_id, amount, stage, status, created_at)
                      VALUES (?,?,?,?, 'confirmed', ?)""",
                   (from_uid, to_uid, amount, stage, now))
    except Exception as e:
        return False, f"Erro ao registrar doação: {e}"
    log_action(from_uid, "DONATION_SENT", {"to": to_uid, "amount": amount, "stage": stage})
    recv_user = get_user_by_id(to_uid)
    recv_stage = recv_user[8]
    recv_count = recv_user[9] + 1
    if recv_count >= STAGE_TARGET_DONATIONS and recv_stage < STAGE_MAX:
        db_execute("UPDATE users SET received_stage_donations = 0, stage = stage + 1 WHERE id = ?", (to_uid,))
        log_action(to_uid, "STAGE_UP", {"from_stage": recv_stage, "to_stage": recv_stage + 1})
    else:
        db_execute("UPDATE users SET received_stage_donations = ? WHERE id = ?", (recv_count, to_uid))
    return True, f"Doação registrada e confirmada para {to_full} (R$ {amount:.2f})."

def listar_doacoes(uid: int):
    sent = db_query("""
        SELECT d.id, u.username AS para, d.amount, d.stage, d.status, d.created_at
        FROM donations d
        JOIN users u ON d.to_user_id = u.id
        WHERE d.from_user_id = ? ORDER BY d.id DESC
    """, (uid,), as_df=True)
    received = db_query("""
        SELECT d.id, u.username AS de, d.amount, d.stage, d.status, d.created_at
        FROM donations d
        JOIN users u ON d.from_user_id = u.id
        WHERE d.to_user_id = ? ORDER BY d.id DESC
    """, (uid,), as_df=True)
    return sent, received

# ===============================
# UI: Sidebar (login ou logado)
# ===============================
def ui_sidebar_login():
    if "user" not in st.session_state:
        st.session_state["user"] = None

    st.sidebar.title(f"🤝 {APP_NAME}")

    if st.session_state.get("user"):
        u = st.session_state["user"]
        st.sidebar.markdown(f"**{u['full_name'] or u['username']}**")
        st.sidebar.caption(f"Stage: {u['stage']}")
        if st.sidebar.button("Sair", key="logout_btn"):
            st.session_state["user"] = None
            st.rerun()
        st.sidebar.divider()
        st.sidebar.markdown("Menu principal abaixo.")
        return

    st.sidebar.subheader("🔐 Login")
    login_user = st.sidebar.text_input("Usuário", key="login_u")
    login_pass = st.sidebar.text_input("Senha", type="password", key="login_p")
    if st.sidebar.button("Entrar", key="login_btn"):
        ok, res = authenticate(login_user, login_pass)
        if ok:
            st.session_state["user"] = res
            st.success(f"Bem-vindo, {res['full_name'] or res['username']}!")
            st.rerun()
        else:
            st.error(res)

# ===============================
# PÁGINAS
# ===============================
def page_home():
    if os.path.exists(LOCAL_LOGO_REL):
        st.image(LOCAL_LOGO_REL, width=300)
    st.title("🤝 Mão Amiga • PIX")
    st.subheader("Semear Prosperidade e Compartilhar Abundância")
    st.write("Cada doação é uma semente. Contribua, receba e permita que a prosperidade transborde.")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estágio 1", "R$ 50")
    c2.metric("Estágio 2", "R$ 100")
    c3.metric("Estágio 3", "R$ 300")
    st.caption("Receba 12 doações para subir de estágio.")

# ======= Página Registro =======
def page_register():
    st.header("📝 Registrar novo usuário")
    st.write("Preencha os dados para entrar na rede.")
    col1, col2 = st.columns([2,1])
    with col1:
        reg_user = st.text_input("Usuário (único)", key="reg_user_page")
        reg_full = st.text_input("Nome completo", key="reg_full_page")
        reg_email = st.text_input("Email (opcional)", key="reg_email_page")
        reg_pix = st.text_input("Chave PIX (opcional)", key="reg_pix_page")
    with col2:
        reg_pass = st.text_input("Senha", type="password", key="reg_pass_page")
        reg_ref = st.text_input("Indicador (username) - opcional", key="reg_ref_page")
        st.write("")
        if st.button("Registrar", key="reg_submit_page"):
            if not reg_user or not reg_pass or not reg_full:
                st.error("Preencha usuário, nome completo e senha.")
            else:
                ok, msg = create_user(reg_user, reg_email or None, reg_pass, reg_full, reg_pix or None, reg_ref or None)
                if ok:
                    st.success(msg)
                    st.info("Agora faça login pela barra lateral.")
                else:
                    st.error(msg)

# ======= Página Dashboard =======
def page_dashboard():
    require_login()
    user = st.session_state["user"]
    st.header(f"🏠 Dashboard — {user['full_name'] or user['username']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Stage atual", user["stage"])
    c2.metric("Recebidas (atual)", user["received_stage_donations"])
    c3.metric("PIX", user["pix_key"] or "—")
    st.markdown("---")
    st.info("Acesse 'Rede / Ciclos' para ver os ciclos e registrar suas doações.")

# ======= Página Rede / Ciclos =======
def page_rede_ciclos():
    require_login()
    user = st.session_state["user"]
    st.header("🤝 Rede / Ciclos")
    st.write(f"Você está no **Stage {user['stage']}**")

    # Pega todos os usuários do stage atual
    df_stage = db_query("SELECT id, username, full_name, pix_key, received_stage_donations FROM users WHERE stage = ? ORDER BY id",
                        (user["stage"],), as_df=True)

    # Dividir em ciclos de 12 pessoas
    ciclos = [df_stage[i:i+STAGE_TARGET_DONATIONS] for i in range(0, len(df_stage), STAGE_TARGET_DONATIONS)]

    for i, ciclo in enumerate(ciclos):
        fechado = ciclo.shape[0] == STAGE_TARGET_DONATIONS
        st.subheader(f"Ciclo {i+1} {'(Fechado)' if fechado else '(Em andamento)'}")
        cols = st.columns(4)
        for idx, row in ciclo.iterrows():
            with cols[idx % 4]:
                st.markdown(f"**{row['full_name']} ({row['username']})**")
                st.markdown(f"PIX: {row['pix_key'] or '—'}")
                st.markdown(f"Doações recebidas: {row['received_stage_donations']}/{STAGE_TARGET_DONATIONS}")
                if row['id'] == user["id"]:
                    st.info("Você está aqui!")

    # Mostrar beneficiário do usuário
    tgt = get_donation_target(user["id"])
    if tgt:
        to_id, to_username, to_full, to_pix = tgt
        st.markdown("---")
        st.subheader("📌 Você vai doar para:")
        st.info(f"**Nome:** {to_full}\n\n"
                f"**Usuário:** {to_username}\n\n"
                f"**PIX:** {to_pix or '—'}\n\n"
                f"**Valor a doar:** R$ {get_stage_amount(user['stage']):.2f}")
        if st.button("Registrar Doação"):
            ok, msg = record_donation(user["id"])
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    else:
        st.warning("Você não possui indicador (referrer) definido.")

# ======= Página Admin =======
def page_admin():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "admin":
        st.warning("Área restrita a administradores.")
        st.stop()

    st.header("⚙️ Painel Admin • Gerenciamento de Usuários")
    st.markdown("Aqui você pode gerenciar usuários, atualizar PIX, planos e visualizar indicadores.")

    df = db_query("""
        SELECT id, username, full_name, email, plan, stage, received_stage_donations, pix_key, referrer_id, created_at
        FROM users ORDER BY id
    """, as_df=True)

    st.subheader("Usuários Cadastrados")
    for idx, row in df.iterrows():
        st.markdown(f"**{row['full_name']} ({row['username']})**")
        st.write(f"- Email: {row['email'] or '—'}")
        st.write(f"- Stage: {row['stage']} | Doações recebidas: {row['received_stage_donations']} | Plano: {row['plan']}")
        st.write(f"- PIX: {row['pix_key'] or '—'} | Indicação: {row['referrer_id'] or '—'} | Criado em: {row['created_at']}")
        col1, col2, col3 = st.columns([1,1,1])
        with col1:
            if st.button(f"Excluir {row['username']}", key=f"del_{row['id']}"):
                db_execute("DELETE FROM users WHERE id = ?", (row['id'],))
                log_action(user['id'], "DELETE_USER", {"deleted_user": row['username']})
                st.success(f"Usuário {row['username']} excluído com sucesso!")
                st.rerun()
        with col2:
            new_pix = st.text_input(f"PIX {row['username']}", value=row['pix_key'] or "", key=f"pix_{row['id']}")
            if st.button(f"Atualizar PIX {row['username']}", key=f"btn_pix_{row['id']}"):
                db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, row['id']))
                log_action(user['id'], "UPDATE_PIX", {"user": row['username'], "new_pix": new_pix})
                st.success(f"PIX de {row['username']} atualizado!")
                st.rerun()
        with col3:
            new_plan = st.text_input(f"Plano {row['username']}", value=row['plan'], key=f"plan_{row['id']}")
            if st.button(f"Atualizar Plano {row['username']}", key=f"btn_plan_{row['id']}"):
                db_execute("UPDATE users SET plan = ? WHERE id = ?", (new_plan, row['id']))
                log_action(user['id'], "UPDATE_PLAN", {"user": row['username'], "new_plan": new_plan})
                st.success(f"Plano de {row['username']} atualizado!")
                st.rerun()

# ===============================
# Roteamento
# ===============================
pages = {
    "Home": page_home,
    "Registro": page_register,
    "Dashboard": page_dashboard,
    "Rede / Ciclos": page_rede_ciclos,
    "Admin": page_admin
}

ui_sidebar_login()

page = st.sidebar.selectbox("Escolha a página", list(pages.keys()))
pages[page]()
