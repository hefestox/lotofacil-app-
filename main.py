import streamlit as st
from datetime import datetime
import bcrypt
from db import db_query, db_execute
import os
import json

# ===============================
# CONFIGURAÇÕES
# ===============================
st.set_page_config(page_title="Mão Amiga • PIX", page_icon="🤝", layout="wide")
APP_NAME = "Mão Amiga"
LOCAL_LOGO_REL = os.path.join("assets", "logo.png")

STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12

# ===============================
# BANCO (INICIALIZAÇÃO)
# ===============================
def init_db():
    db_execute("""CREATE TABLE IF NOT EXISTS users(
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
    );""")

    db_execute("""CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );""")

    db_execute("""CREATE TABLE IF NOT EXISTS donations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER NOT NULL,
        to_user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        stage INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
    );""")

init_db()

# ===============================
# FUNÇÕES DE AUTENTICAÇÃO
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
        (user_id, action, None if payload is None else json.dumps(payload), datetime.utcnow().isoformat())
    )

def create_user(username, email, password, full_name, pix_key, referrer_username=None):
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
    except Exception as e:
        return False, f"Erro: usuário ou e-mail já existe. ({e})"

def get_user_by_username(username):
    rows = db_query("""SELECT id, username, email, password_hash, role, plan, full_name, pix_key,
                       stage, received_stage_donations, referrer_id FROM users WHERE username = ?""", (username,))
    return rows[0] if rows else None

def get_user_by_id(uid):
    rows = db_query("""SELECT id, username, email, password_hash, role, plan, full_name, pix_key,
                       stage, received_stage_donations, referrer_id FROM users WHERE id = ?""", (uid,))
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

# ===============================
# FUNÇÕES DE DOAÇÃO
# ===============================
def get_stage_amount(stage: int) -> float:
    return STAGE_AMOUNTS.get(stage, STAGE_AMOUNTS[1])

def get_donation_target(uid: int):
    row = db_query("""SELECT u2.id, u2.username, u2.full_name, u2.pix_key
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
    stage = u[8]
    amount = get_stage_amount(stage)
    now = datetime.utcnow().isoformat()
    db_execute("""INSERT INTO donations(from_user_id, to_user_id, amount, stage, status, created_at)
                  VALUES (?,?,?,?, 'confirmed', ?)""",
               (from_uid, to_uid, amount, stage, now))
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
    sent = db_query("""SELECT d.id, u.username AS para, d.amount, d.stage, d.status, d.created_at
                       FROM donations d
                       JOIN users u ON d.to_user_id = u.id
                       WHERE d.from_user_id = ? ORDER BY d.id DESC""", (uid,), as_df=True)
    received = db_query("""SELECT d.id, u.username AS de, d.amount, d.stage, d.status, d.created_at
                           FROM donations d
                           JOIN users u ON d.from_user_id = u.id
                           WHERE d.to_user_id = ? ORDER BY d.id DESC""", (uid,), as_df=True)
    return sent, received

# ===============================
# UI: Sidebar login
# ===============================
def ui_sidebar_login():
    if "user" not in st.session_state:
        st.session_state["user"] = None

    st.sidebar.title(f"🤝 {APP_NAME}")

    if st.session_state.get("user"):
        u = st.session_state["user"]
        st.sidebar.markdown(f"**{u['full_name'] or u['username']}**")
        st.sidebar.caption(f"Stage: {u['stage']}")
        if st.sidebar.button("Sair"):
            st.session_state["user"] = None
            st.experimental_rerun()
        st.sidebar.divider()
        return

    st.sidebar.subheader("🔐 Login")
    login_user = st.sidebar.text_input("Usuário")
    login_pass = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        ok, res = authenticate(login_user, login_pass)
        if ok:
            st.session_state["user"] = res
            st.success(f"Bem-vindo, {res['full_name'] or res['username']}!")
            st.experimental_rerun()
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

def page_register():
    st.header("📝 Registrar novo usuário")
    reg_user = st.text_input("Usuário")
    reg_full = st.text_input("Nome completo")
    reg_email = st.text_input("Email (opcional)")
    reg_pass = st.text_input("Senha", type="password")
    reg_pix = st.text_input("Chave PIX (opcional)")
    reg_ref = st.text_input("Indicador (username) - opcional")
    if st.button("Registrar"):
        if not reg_user or not reg_pass or not reg_full:
            st.error("Preencha usuário, nome completo e senha.")
        else:
            ok, msg = create_user(reg_user, reg_email or None, reg_pass, reg_full, reg_pix or None, reg_ref or None)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

def page_dashboard():
    require_login()
    user = st.session_state["user"]
    st.header("📊 Dashboard")
    st.markdown(f"Bem-vindo, **{user['full_name'] or user['username']}**")
    st.write(f"Stage atual: {user['stage']}")
    st.write(f"Doações recebidas neste estágio: {user['received_stage_donations']}")
    st.markdown("---")
    if st.button("Registrar doação"):
        ok, msg = record_donation(user["id"])
        if ok:
            st.success(msg)
        else:
            st.error(msg)
        st.experimental_rerun()
    sent, received = listar_doacoes(user["id"])
    st.subheader("Doações enviadas")
    st.dataframe(sent)
    st.subheader("Doações recebidas")
    st.dataframe(received)

def page_admin():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "admin":
        st.warning("Área restrita a administradores.")
        st.stop()

    st.header("⚙️ Painel Admin • Gerenciamento de Usuários")
    st.markdown("Aqui você pode gerenciar usuários, atualizar PIX, planos e visualizar indicadores.")

    df = db_query("""SELECT id, username, full_name, email, plan, stage, received_stage_donations, pix_key, referrer_id, created_at
                     FROM users ORDER BY id""", as_df=True)

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
                st.experimental_rerun()
        with col2:
            new_pix = st.text_input(f"PIX {row['username']}", value=row['pix_key'] or "", key=f"pix_{row['id']}")
            if st.button(f"Atualizar PIX {row['username']}", key=f"btn_pix_{row['id']}"):
                db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, row['id']))
                log_action(user['id'], "UPDATE_PIX", {"user": row['username'], "new_pix": new_pix})
                st.success(f"PIX de {row['username']} atualizado!")
                st.experimental_rerun()

# ===============================
# MENU
# ===============================
PAGES = {
    "Início": page_home,
    "Registrar": page_register,
    "Dashboard": page_dashboard,
    "Admin": page_admin
}

def main():
    ui_sidebar_login()
    choice = st.sidebar.selectbox("Navegação", list(PAGES.keys()))
    PAGES[choice]()

if __name__ == "__main__":
    main()
