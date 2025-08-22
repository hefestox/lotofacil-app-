# main.py
import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
import bcrypt

# =========================================
# CONFIGURAÇÕES
# =========================================
st.set_page_config(page_title="Mão Amiga • PIX", page_icon="🤝", layout="wide")

APP_NAME = "Mão Amiga"
STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12

# =========================================
# BANCO DE DADOS
# =========================================
@st.cache_resource
def get_conn():
    conn = sqlite3.connect("app.db", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Usuários
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            stage INTEGER NOT NULL DEFAULT 1,
            received_stage_donations INTEGER NOT NULL DEFAULT 0,
            full_name TEXT,
            pix_key TEXT,
            referrer_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(referrer_id) REFERENCES users(id)
        );
    """)
    # Auditoria
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
    # Doações
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

# =========================================
# AUTENTICAÇÃO
# =========================================
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

def get_user_by_username(username: str):
    rows = db_query("""SELECT id, username, email, password_hash, role, stage,
                               received_stage_donations, full_name, pix_key, referrer_id
                        FROM users WHERE username = ?""", (username,))
    return rows[0] if rows else None

def get_user_by_id(uid: int):
    rows = db_query("""SELECT id, username, email, password_hash, role, stage,
                               received_stage_donations, full_name, pix_key, referrer_id
                        FROM users WHERE id = ?""", (uid,))
    return rows[0] if rows else None

def authenticate(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return False, "Usuário não encontrado."
    uid, uname, email, phash, role, stage, recv, full_name, pix_key, ref_id = user
    if check_password(password, phash):
        return True, {"id": uid, "username": uname, "email": email, "role": role,
                      "stage": stage, "received_stage_donations": recv,
                      "full_name": full_name, "pix_key": pix_key, "referrer_id": ref_id}
    return False, "Senha inválida."

def require_login():
    if not st.session_state.get("user"):
        st.warning("Faça login para continuar.")
        st.stop()

# =========================================
# USUÁRIOS E DOAÇÕES
# =========================================
def create_user(username: str, email: str, password: str, full_name: str, pix_key: str, referrer_username: str|None):
    now = datetime.utcnow().isoformat()
    ph = hash_password(password)

    ref_id = None
    if referrer_username:
        row = db_query("SELECT id FROM users WHERE username = ?", (referrer_username,))
        if row:
            ref_id = row[0][0]
    else:
        # Atribui automaticamente primeiro admin existente
        row = db_query("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")
        if row:
            ref_id = row[0][0]

    try:
        cur = db_execute(
            """INSERT INTO users (username, email, password_hash, role, stage,
                                  received_stage_donations, full_name, pix_key, referrer_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (username, email, ph, "user", 1, 0, full_name, pix_key, ref_id, now)
        )
        uid = cur.lastrowid
        log_action(uid, "CREATE_USER", {"username": username, "referrer_id": ref_id})
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError as e:
        return False, f"Erro: usuário ou e-mail já existe. ({e})"

def update_pix(uid: int, new_pix: str):
    db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, uid))
    log_action(uid, "UPDATE_PIX", {"pix": new_pix})
    return True, "Chave PIX atualizada."

def get_stage_amount(stage: int) -> float:
    return STAGE_AMOUNTS.get(stage, STAGE_AMOUNTS[1])

def get_donation_target(uid: int):
    row = db_query("""SELECT u2.id, u2.full_name, u2.pix_key
                       FROM users u1
                       JOIN users u2 ON u1.referrer_id = u2.id
                       WHERE u1.id = ?""", (uid,))
    return row[0] if row else None

def record_donation(from_uid: int):
    tgt = get_donation_target(from_uid)
    if not tgt:
        return False, "Você ainda não tem um indicador definido."
    to_uid, to_full, to_pix = tgt

    u = get_user_by_id(from_uid)
    stage = u[5]
    amount = get_stage_amount(stage)
    now = datetime.utcnow().isoformat()

    db_execute("""INSERT INTO donations(from_user_id, to_user_id, amount, stage, status, created_at)
                  VALUES (?,?,?,?, 'confirmed', ?)""",
               (from_uid, to_uid, amount, stage, now))
    log_action(from_uid, "DONATION_SENT", {"to": to_uid, "amount": amount, "stage": stage})

    recv_user = get_user_by_id(to_uid)
    recv_stage = recv_user[5]
    recv_count = recv_user[6] + 1

    if recv_count >= STAGE_TARGET_DONATIONS and recv_stage < STAGE_MAX:
        db_execute("""UPDATE users
                      SET received_stage_donations = 0,
                          stage = stage + 1
                      WHERE id = ?""", (to_uid,))
        log_action(to_uid, "STAGE_UP", {"from_stage": recv_stage, "to_stage": recv_stage + 1})
    else:
        db_execute("UPDATE users SET received_stage_donations = ? WHERE id = ?", (recv_count, to_uid))

    return True, f"Doação registrada e confirmada para {to_full} (R$ {amount:.2f})."

def listar_doacoes(uid: int):
    sent = db_query("""SELECT d.id, u.username AS para, d.amount, d.stage, d.status, d.created_at
                        FROM donations d
                        JOIN users u ON d.to_user_id = u.id
                        WHERE d.from_user_id = ? ORDER BY d.id DESC""", (uid,), as_df=True)
    received = db_query("""SELECT d.id, u.username AS de, d.amount, d.stage, d.status, d.created_at
                            FROM donations d
                            JOIN users u ON d.from_user_id = u.id
                            WHERE d.to_user_id = ? ORDER BY d.id DESC""", (uid,), as_df=True)
    return sent, received

# =========================================
# UI
# =========================================
def ui_login():
    if "user" not in st.session_state:
        st.session_state["user"] = None

    st.sidebar.title(f"🤝 {APP_NAME}")
    st.sidebar.subheader("🔐 Login")
    u = st.sidebar.text_input("Usuário")
    p = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        ok, res = authenticate(u, p)
        if ok:
            st.session_state["user"] = res
            st.success(f"Bem-vindo, {res['full_name'] or res['username']}!")
        else:
            st.error(res)

    st.sidebar.subheader("📌 Registrar")
    u2 = st.sidebar.text_input("Novo usuário", key="reg_u")
    p2 = st.sidebar.text_input("Senha", type="password", key="reg_p")
    n2 = st.sidebar.text_input("Nome completo", key="reg_n")
    pix2 = st.sidebar.text_input("Chave PIX", key="reg_pix")
    ref2 = st.sidebar.text_input("Indicador (opcional)", key="reg_ref")
    if st.sidebar.button("Registrar", key="reg_btn"):
        ok, msg = create_user(u2, None, p2, n2, pix2, ref2 or None)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

def page_dashboard():
    require_login()
    user = st.session_state["user"]
    st.title("🏠 Dashboard")
    st.write(f"Olá **{user['full_name']}**! Stage atual: **{user['stage']}**")
    st.write(f"Chave PIX cadastrada: **{user['pix_key']}**")
    st.write("Use a aba 'Doações / Rede' para registrar suas doações via PIX.")

def page_rede_doacoes():
    require_login()
    user = st.session_state["user"]
    st.title("🤝 Rede / Doações")
    st.write(f"Stage atual: **{user['stage']}**")

    target = get_donation_target(user["id"])
    if target:
        to_uid, to_full, to_pix = target
        st.write(f"Você deve doar para: **{to_full}** | PIX: **{to_pix}**")
    else:
        st.write("Ainda não há indicador definido para você.")

    new_pix = st.text_input("Atualizar chave PIX", value=user["pix_key"])
    if st.button("Atualizar PIX"):
        ok, msg = update_pix(user["id"], new_pix)
        if ok:
            st.success(msg)
            st.session_state["user"]["pix_key"] = new_pix

    if st.button("Registrar Doação"):
        ok, msg = record_donation(user["id"])
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    sent, received = listar_doacoes(user["id"])
    st.subheader("Doações enviadas")
    st.dataframe(sent)
    st.subheader("Doações recebidas")
    st.dataframe(received)

def page_admin():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "admin":
        st.warning("Área restrita a administradores")
        st.stop()

    st.title("⚙️ Painel Admin")
    df = db_query("SELECT id, username, full_name, email, stage, received_stage_donations, pix_key, referrer_id FROM users", as_df=True)
    st.dataframe(df)

# =========================================
# ROTEAMENTO
# =========================================
PAGES = {
    "Dashboard": page_dashboard,
    "Doações / Rede": page_rede_doacoes,
    "Admin": page_admin
}

ui_login()

if st.session_state.get("user"):
    page = st.sidebar.selectbox("Menu", list(PAGES.keys()))
    PAGES[page]()
