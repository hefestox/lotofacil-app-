# admin_streamlit_advanced.py
import streamlit as st
import pandas as pd
import sqlite3

# ===============================
# CONFIGURAÇÕES
# ===============================
st.set_page_config(page_title="Admin • Mão Amiga", page_icon="🛠️", layout="wide")

DB_FILE = "app.db"

# ===============================
# FUNÇÕES DB
# ===============================
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

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

# ===============================
# FUNÇÕES ADMIN
# ===============================
def list_users(filter_text=""):
    df = db_query(
        "SELECT id, username, full_name, email, role, plan, pix_key FROM users",
        as_df=True
    )
    if filter_text:
        df = df[df.apply(lambda row: row.astype(str).str.contains(filter_text, case=False).any(), axis=1)]
    return df

def delete_user(user_id):
    db_execute("DELETE FROM users WHERE id = ?", (user_id,))
    st.success(f"Usuário {user_id} excluído com sucesso!")

def update_pix(user_id, new_pix):
    db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, user_id))
    st.success(f"PIX do usuário {user_id} atualizado para: {new_pix}")

def update_plan(user_id, new_plan):
    db_execute("UPDATE users SET plan = ? WHERE id = ?", (new_plan, user_id))
    st.success(f"Plano do usuário {user_id} atualizado para: {new_plan}")

# ===============================
# INTERFACE
# ===============================
st.title("🛠️ Painel Admin • Mão Amiga")

tabs = st.tabs(["Usuários", "Excluir Usuário", "Atualizar PIX", "Atualizar Plano"])

# ===============================
# ABA 1: Usuários
# ===============================
with tabs[0]:
    st.subheader("📋 Lista de Usuários")
    filter_text = st.text_input("Filtrar por nome, email ou plano")
    users_df = list_users(filter_text)
    st.dataframe(users_df, use_container_width=True)

# ===============================
# ABA 2: Excluir Usuário
# ===============================
with tabs[1]:
    st.subheader("❌ Excluir Usuário")
    del_id = st.number_input("ID do usuário", min_value=1, step=1)
    if st.button("Excluir Usuário"):
        if st.confirm(f"Tem certeza que deseja excluir o usuário {del_id}?"):
            delete_user(del_id)
            st.experimental_rerun()

# ===============================
# ABA 3: Atualizar PIX
# ===============================
with tabs[2]:
    st.subheader("💳 Atualizar PIX")
    pix_id = st.number_input("ID do usuário", min_value=1, step=1, key="pix_id")
    new_pix = st.text_input("Nova chave PIX")
    if st.button("Atualizar PIX"):
        if st.confirm(f"Confirmar atualização do PIX do usuário {pix_id}?"):
            update_pix(pix_id, new_pix)
            st.experimental_rerun()

# ===============================
# ABA 4: Atualizar Plano
# ===============================
with tabs[3]:
    st.subheader("🔄 Atualizar Plano")
    plan_id = st.number_input("ID do usuário", min_value=1, step=1, key="plan_id")
    new_plan = st.selectbox("Novo plano", ["Bronze", "Prata", "Ouro", "Diamante"])
    if st.button("Atualizar Plano"):
        if st.confirm(f"Confirmar atualização do plano do usuário {plan_id}?"):
            update_plan(plan_id, new_plan)
            st.experimental_rerun()
