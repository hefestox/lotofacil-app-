# main.py
import os
import json
import sqlite3
from datetime import datetime

import bcrypt
import pandas as pd
import streamlit as st

from db import db_query, db_execute

# ===============================
# CONFIGURAÇÕES
# ===============================
st.set_page_config(page_title="Mão Amiga • PIX", page_icon="🤝", layout="wide")
APP_NAME = "Mão Amiga"
LOCAL_LOGO_REL = os.path.join("assets", "logo.png")

# Estágios e metas
STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3
STAGE_TARGET_DONATIONS = 12  # fecha ciclo e sobe de estágio após 12 doações recebidas

# ===============================
# BANCO (INICIALIZAÇÃO)
# ===============================
def init_db():
    # Tabela de usuários
    db_execute("""
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
    # Auditoria
    db_execute("""
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
    db_execute("""
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

def ensure_admin_seed():
    # Cria um admin padrão se não existir (username: admin / senha: admin123)
    row = db_query("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not row:
        now = datetime.utcnow().isoformat()
        ph = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        try:
            db_execute("""
                INSERT INTO users (username, email, password_hash, role, plan, full_name, pix_key,
                                   stage, received_stage_donations, referrer_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, ("admin", "admin@teste.com", ph, "admin", "Diamante", "Administrador",
                  None, 3, 0, None, now))
        except sqlite3.IntegrityError:
            pass

init_db()
ensure_admin_seed()

# ===============================
# HELPERS / AUTENTICAÇÃO
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

    # resolve referrer se foi informado
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
        msg = str(e).lower()
        if "username" in msg:
            return False, "Erro: usuário já existe."
        if "email" in msg:
            return False, "Erro: e-mail já cadastrado."
        return False, f"Erro de integridade: {e}"
    except Exception as e:
        return False, f"Erro inesperado ao criar usuário: {e}"

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
# LÓGICA DE CICLO / DOAÇÕES
# ===============================
def get_stage_amount(stage: int) -> float:
    return STAGE_AMOUNTS.get(stage, STAGE_AMOUNTS[1])

def get_donation_target(uid: int):
    """
    1) Se tiver referrer, o alvo é o referrer.
    2) Caso contrário, escolhe automaticamente o próximo usuário disponível NO MESMO ESTÁGIO do doador,
       com menos doações recebidas e mais antigo (fair queue).
    """
    # tenta referrer
    row = db_query("""
        SELECT u2.id, u2.username, u2.full_name, u2.pix_key
        FROM users u1
        JOIN users u2 ON u1.referrer_id = u2.id
        WHERE u1.id = ?
    """, (uid,))
    if row:
        return row[0]

    # fallback: fila por estágio
    me = get_user_by_id(uid)
    if not me:
        return None
    my_stage = me[8]

    fallback = db_query("""
        SELECT id, username, full_name, pix_key
        FROM users
        WHERE id != ? AND stage = ? AND received_stage_donations < ?
        ORDER BY received_stage_donations ASC, created_at ASC
        LIMIT 1
    """, (uid, my_stage, STAGE_TARGET_DONATIONS))
    return fallback[0] if fallback else None

def record_donation(from_uid: int):
    tgt = get_donation_target(from_uid)
    if not tgt:
        return False, "Nenhum alvo de doação disponível no seu ciclo ainda. Tente novamente mais tarde."
    to_uid, to_username, to_full, to_pix = tgt

    u = get_user_by_id(from_uid)
    stage = u[8]  # índice do stage
    amount = get_stage_amount(stage)
    now = datetime.utcnow().isoformat()

    # registra doação
    db_execute("""
        INSERT INTO donations(from_user_id, to_user_id, amount, stage, status, created_at)
        VALUES (?,?,?,?, 'confirmed', ?)
    """, (from_uid, to_uid, amount, stage, now))
    log_action(from_uid, "DONATION_SENT", {"to": to_uid, "amount": amount, "stage": stage})

    # atualiza contador do recebedor e possível subida de estágio
    recv_user = get_user_by_id(to_uid)
    recv_stage = recv_user[8]
    recv_count = recv_user[9] + 1  # received_stage_donations + 1

    if recv_count >= STAGE_TARGET_DONATIONS and recv_stage < STAGE_MAX:
        # fecha ciclo, sobe estágio e zera contador
        db_execute("UPDATE users SET received_stage_donations = 0, stage = stage + 1 WHERE id = ?", (to_uid,))
        log_action(to_uid, "STAGE_UP", {"from_stage": recv_stage, "to_stage": recv_stage + 1})
    else:
        db_execute("UPDATE users SET received_stage_donations = ? WHERE id = ?", (recv_count, to_uid))

    # refresh quick message
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
            st.rerun()
        st.sidebar.divider()
        st.sidebar.markdown("Menu principal abaixo.")
        return

    st.sidebar.subheader("🔐 Login")
    login_user = st.sidebar.text_input("Usuário")
    login_pass = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
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
        st.image(LOCAL_LOGO_REL, width=280)
    st.title("🤝 Mão Amiga • PIX")
    st.subheader("Semear Prosperidade e Compartilhar Abundância")
    st.write("Cada doação é uma semente. Contribua, receba e permita que a prosperidade transborde.")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estágio 1", "R$ 50")
    c2.metric("Estágio 2", "R$ 100")
    c3.metric("Estágio 3", "R$ 300")
    st.caption(f"Receba {STAGE_TARGET_DONATIONS} doações para subir de estágio.")

def page_register():
    st.header("📝 Registrar novo usuário")
    col1, col2 = st.columns([2,1])
    with col1:
        reg_user = st.text_input("Usuário (único)")
        reg_full = st.text_input("Nome completo")
        reg_email = st.text_input("Email (opcional)")
        reg_pix = st.text_input("Chave PIX (opcional)")
        reg_ref = st.text_input("Indicador (username) - opcional")
    with col2:
        reg_pass = st.text_input("Senha", type="password")
        if st.button("Registrar"):
            if not reg_user or not reg_pass or not reg_full:
                st.error("Preencha usuário, nome completo e senha.")
            else:
                ok, msg = create_user(reg_user, reg_email or None, reg_pass, reg_full, reg_pix or None, reg_ref or None)
                if ok:
                    st.success(msg)
                    st.info("Agora faça login pela barra lateral.")
                else:
                    st.error(msg)

def page_dashboard():
    require_login()
    user = st.session_state["user"]
    st.header(f"🏠 Dashboard — {user['full_name'] or user['username']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Stage atual", user["stage"])
    c2.metric("Recebidas (atual)", user["received_stage_donations"])
    c3.metric("PIX", user["pix_key"] or "—")
    st.markdown("---")

    # Mostra alvo atual (indicador ou automático)
    tgt = get_donation_target(user["id"])
    st.subheader("🎯 Seu alvo de doação")
    if tgt:
        to_id, to_username, to_full, to_pix = tgt
        st.write(f"**Nome:** {to_full}  \n**Usuário:** {to_username}  \n**PIX:** {to_pix or '—'}  \n**Valor a doar:** R$ {get_stage_amount(user['stage']):.2f}")
    else:
        st.info("Ainda não há alvo disponível no seu ciclo. Aguarde novos participantes.")

    if st.button("Registrar Doação Agora"):
        ok, msg = record_donation(user["id"])
        if ok:
            st.success(msg)
            # refresh local user info
            refreshed = get_user_by_id(user["id"])
            if refreshed:
                st.session_state["user"]["pix_key"] = refreshed[7]
                st.session_state["user"]["stage"] = refreshed[8]
                st.session_state["user"]["received_stage_donations"] = refreshed[9]
            st.rerun()
        else:
            st.error(msg)

    st.markdown("---")
    sent, received = listar_doacoes(user["id"])
    with st.expander("📤 Doações enviadas"):
        if not sent.empty:
            st.dataframe(sent.style.format({"amount": "R$ {:.2f}"}), use_container_width=True)
        else:
            st.write("Nenhuma doação enviada.")
    with st.expander("📥 Doações recebidas"):
        if not received.empty:
            st.dataframe(received.style.format({"amount": "R$ {:.2f}"}), use_container_width=True)
        else:
            st.write("Nenhuma doação recebida.")

def page_rede_doacoes():
    require_login()
    user = st.session_state["user"]
    st.header("🤝 Rede / Doações")
    st.write(f"**Stage:** {user['stage']}")

    tgt = get_donation_target(user["id"])
    if tgt:
        to_id, to_username, to_full, to_pix = tgt
        left, right = st.columns([3,2])
        with left:
            st.subheader("Beneficiário")
            st.markdown(f"**Nome:** {to_full}")
            st.markdown(f"**Usuário:** {to_username}")
            st.markdown(f"**PIX:** {to_pix or '—'}")
            st.markdown(f"**Valor a doar:** R$ {get_stage_amount(user['stage']):.2f}")
        with right:
            st.subheader("Ações")
            new_pix = st.text_input("Sua chave PIX (para receber)", value=user["pix_key"] or "")
            if st.button("Salvar minha PIX"):
                db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, user["id"]))
                st.session_state["user"]["pix_key"] = new_pix
                log_action(user["id"], "UPDATE_PIX", {"pix": new_pix})
                st.success("PIX atualizada.")
            if st.button("Registrar Doação"):
                ok, msg = record_donation(user["id"])
                if ok:
                    st.success(msg)
                    refreshed = get_user_by_id(user["id"])
                    if refreshed:
                        st.session_state["user"]["pix_key"] = refreshed[7]
                        st.session_state["user"]["stage"] = refreshed[8]
                        st.session_state["user"]["received_stage_donations"] = refreshed[9]
                    st.rerun()
                else:
                    st.error(msg)
    else:
        st.warning("Nenhum alvo disponível no seu ciclo no momento.")

    st.markdown("---")
    sent, received = listar_doacoes(user["id"])
    with st.expander("📤 Doações enviadas"):
        st.dataframe(sent if not sent.empty else pd.DataFrame(), use_container_width=True)
    with st.expander("📥 Doações recebidas"):
        st.dataframe(received if not received.empty else pd.DataFrame(), use_container_width=True)

def page_ciclos():
    st.header("🔁 Ciclos por estágio")
    st.caption(f"Cada ciclo fecha quando um usuário recebe {STAGE_TARGET_DONATIONS} doações; então ele sobe de estágio.")

    for stage in range(1, STAGE_MAX + 1):
        st.subheader(f"Estágio {stage}")
        df = db_query("""
            SELECT id, username, full_name, pix_key, received_stage_donations, created_at
            FROM users
            WHERE stage = ?
            ORDER BY received_stage_donations ASC, datetime(created_at) ASC
        """, (stage,), as_df=True)
        if df.empty:
            st.info("Nenhum usuário neste estágio.")
        else:
            st.dataframe(
                df.rename(columns={
                    "id": "ID", "username": "Usuário", "full_name": "Nome",
                    "pix_key": "PIX", "received_stage_donations": "Recebidas", "created_at": "Criado em"
                }),
                use_container_width=True
            )

def page_admin():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "admin":
        st.warning("Área restrita a administradores.")
        st.stop()

    st.header("⚙️ Painel Admin • Gerenciamento de Usuários")
    df = db_query("""
        SELECT id, username, full_name, email, plan, stage, received_stage_donations, pix_key, referrer_id, created_at
        FROM users ORDER BY id
    """, as_df=True)

    st.subheader("Usuários Cadastrados")
    if df.empty:
        st.info("Sem usuários cadastrados.")
        return

    for idx, row in df.iterrows():
        st.markdown(f"**{row['full_name'] or '—'} ({row['username']})**")
        st.write(f"- Email: {row['email'] or '—'}")
        st.write(f"- Stage: {row['stage']} | Doações recebidas: {row['received_stage_donations']} | Plano: {row['plan']}")
        st.write(f"- PIX: {row['pix_key'] or '—'} | Indicação (referrer_id): {row['referrer_id'] or '—'} | Criado em: {row['created_at']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Excluir {row['username']}", key=f"del_{row['id']}"):
                db_execute("DELETE FROM users WHERE id = ?", (row['id'],))
                log_action(user['id'], "DELETE_USER", {"deleted_user": row['username']})
                st.success(f"Usuário {row['username']} excluído.")
                st.rerun()
        with col2:
            new_pix = st.text_input(f"PIX do {row['username']}", value=row['pix_key'] or "", key=f"pix_{row['id']}")
            if st.button(f"Atualizar PIX {row['username']}", key=f"btn_pix_{row['id']}"):
                db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, row['id']))
                log_action(user['id'], "UPDATE_PIX_ADMIN", {"user": row['username'], "new_pix": new_pix})
                st.success(f"PIX de {row['username']} atualizada.")
                st.rerun()

# ===============================
# MENU / ROTEAMENTO
# ===============================
PAGES = {
    "Início": page_home,
    "Registrar": page_register,
    "Dashboard": page_dashboard,
    "Rede / Doações": page_rede_doacoes,
    "Ciclos": page_ciclos,
    "Admin": page_admin,
}

def main():
    ui_sidebar_login()
    choice = st.sidebar.selectbox("Menu", list(PAGES.keys()), index=0)
    PAGES[choice]()

if __name__ == "__main__":
    main()
