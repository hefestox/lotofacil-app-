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

# Paleta de cores
COLOR_PRIMARY = "#4CAF50"
COLOR_SECONDARY = "#FFC107"
COLOR_BG = "#F0F2F6"
COLOR_CARD = "#FFFFFF"

STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12


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


def create_user(username: str, email: str, password: str, full_name: str, pix_key: str, referrer_username: str | None):
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
        return True, uid, "Usuário criado com sucesso."
    except sqlite3.IntegrityError as e:
        return False, None, f"Erro: usuário ou e-mail já existe. ({e})"


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
    rec = db_query("""
        SELECT d.id, u.username AS de, d.amount, d.stage, d.status, d.created_at
        FROM donations d
        JOIN users u ON d.from_user_id = u.id
        WHERE d.to_user_id = ? ORDER BY d.id DESC
    """, (uid,), as_df=True)
    return sent, rec


# ===============================
# INTERFACE
# ===============================
def main():
    if LOCAL_LOGO_REL and os.path.exists(LOCAL_LOGO_REL):
        st.image(LOCAL_LOGO_REL, width=200)

    menu = ["Login", "Registrar"]
    choice = st.sidebar.selectbox("Menu", menu)

    # =====================
    # LOGIN
    # =====================
    if choice == "Login":
        st.subheader("Login")
        username = st.text_input("Usuário", key="login_user")
        password = st.text_input("Senha", type="password", key="login_pass")
        if st.button("Entrar"):
            ok, data = authenticate(username, password)
            if ok:
                st.session_state.user = data
                st.success(f"Bem-vindo(a) {data['full_name'] or data['username']}!")
                st.experimental_rerun()
            else:
                st.error(data)

    # =====================
    # REGISTRO
    # =====================
    if choice == "Registrar":
        st.subheader("Criar conta")
        full_name = st.text_input("Nome completo")
        username = st.text_input("Usuário")
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        pix = st.text_input("Chave PIX")
        referrer = st.text_input("Indicação (opcional)")
        if st.button("Registrar"):
            ok, uid, msg = create_user(username, email, password, full_name, pix, referrer)
            if ok:
                st.success(msg)
                # Auto-login após registro
                user_data = get_user_by_id(uid)
                st.session_state.user = {
                    "id": user_data[0], "username": user_data[1], "email": user_data[2],
                    "role": user_data[4], "plan": user_data[5], "full_name": user_data[6],
                    "pix_key": user_data[7], "stage": user_data[8], "received_stage_donations": user_data[9],
                    "referrer_id": user_data[10]
                }
                st.experimental_rerun()
            else:
                st.error(msg)

    # =====================
    # ÁREA LOGADA
    # =====================
    if st.session_state.get("user"):
        user = st.session_state.user
        st.sidebar.success(f"Olá, {user['full_name'] or user['username']}!")
        st.title(f"Bem-vindo(a) ao {APP_NAME}")

        st.markdown(f"**Plano atual:** {user['plan']}")
        st.markdown(
            f"**Etapa atual:** {user['stage']} • Doações recebidas nesta etapa: {user['received_stage_donations']}/{STAGE_TARGET_DONATIONS}")

        st.subheader("Registrar doação")
        if st.button("Enviar doação"):
            ok, msg = record_donation(user['id'])
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        st.subheader("Minhas doações")
        sent, rec = listar_doacoes(user['id'])
        st.markdown("**Enviadas:**")
        st.dataframe(sent)
        st.markdown("**Recebidas:**")
        st.dataframe(rec)

        st.subheader("Atualizar PIX")
        new_pix = st.text_input("Nova chave PIX", value=user.get("pix_key") or "")
        if st.button("Atualizar PIX"):
            ok, msg = update_pix(user['id'], new_pix)
            if ok:
                st.success(msg)
                st.session_state.user['pix_key'] = new_pix
            else:
                st.error(msg)

        if st.button("Sair"):
            st.session_state.pop("user")
            st.experimental_rerun()


if __name__ == "__main__":
    main()
