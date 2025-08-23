# main.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import bcrypt
import os
from typing import Optional, List, Dict

# ============================
# Config
# ============================
st.set_page_config(page_title="Mão Amiga • Rede", page_icon="🤝", layout="wide")
APP_NAME = "Mão Amiga"
DB_FILE = "app.db"

MAX_INDICADOS_POR_CICLO = 12
STAGE_AMOUNTS = {1: 50.0, 2: 100.0, 3: 300.0}
STAGE_MAX = 3

# ============================
# DB helpers
# ============================
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        full_name TEXT,
        pix_key TEXT,
        indicador_id INTEGER,          -- quem indicou esse usuário (o "indicador")
        total_indicados INTEGER DEFAULT 0, -- quantos indicados diretos ele tem
        stage INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (indicador_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)
    # simple audit and donations tables (kept minimal)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        payload TEXT,
        created_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS donations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        amount REAL,
        stage INTEGER,
        status TEXT,
        created_at TEXT
    );
    """)
    conn.commit()

def db_execute(query: str, params: tuple = ()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    return cur

def db_query(query: str, params: tuple = (), as_df: bool = False):
    conn = get_conn()
    if as_df:
        return pd.read_sql_query(query, conn, params=params)
    cur = conn.cursor()
    cur.execute(query, params)
    return cur.fetchall()

init_db()

# ============================
# Auth & user functions
# ============================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def get_user_by_username(username: str):
    rows = db_query("SELECT * FROM users WHERE username = ?", (username,))
    return rows[0] if rows else None

def get_user_by_id(uid: int):
    rows = db_query("SELECT * FROM users WHERE id = ?", (uid,))
    return rows[0] if rows else None

def create_user(username: str, email: Optional[str], password: str,
                full_name: Optional[str], pix_key: Optional[str], indicador_id: Optional[int]) -> tuple[bool, str, Optional[int]]:
    """
    Cria usuário. Se indicador_id for fornecido, verifica se indicador tem espaço (<12).
    Retorna (ok, mensagem, novo_id)
    """
    now = datetime.utcnow().isoformat()
    ph = hash_password(password)

    # verifica indicador
    if indicador_id is not None:
        row = get_user_by_id(indicador_id)
        if not row:
            return False, f"Indicador (id={indicador_id}) não encontrado.", None
        total = row[8]  # total_indicados column index (see schema)
        if total >= MAX_INDICADOS_POR_CICLO:
            return False, f"Indicador já possui {MAX_INDICADOS_POR_CICLO} indicados (ciclo completo).", None

    try:
        cur = db_execute(
            """INSERT INTO users (username, email, password_hash, role, full_name, pix_key, indicador_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (username, email, ph, "user", full_name, pix_key, indicador_id, now)
        )
        new_id = cur.lastrowid
        # atualizar contador do indicador
        if indicador_id is not None:
            cur2 = db_execute("UPDATE users SET total_indicados = total_indicados + 1 WHERE id = ?", (indicador_id,))
            # checar se completou 12 e subir de estágio (somente se menor que STAGE_MAX)
            updated = get_user_by_id(indicador_id)
            total_now = updated[8]
            current_stage = updated[9]
            if total_now >= MAX_INDICADOS_POR_CICLO and current_stage < STAGE_MAX:
                db_execute("UPDATE users SET stage = stage + 1, total_indicados = 0 WHERE id = ?", (indicador_id,))
        # log
        db_execute("INSERT INTO audit (user_id, action, payload, created_at) VALUES (?,?,?,?)",
                   (new_id, "create_user", f"indicador={indicador_id}", now))
        return True, "Usuário criado com sucesso.", new_id
    except sqlite3.IntegrityError as e:
        return False, f"Erro: username ou e-mail já existe. ({e})", None

def authenticate(username: str, password: str) -> tuple[bool, str, Optional[Dict]]:
    row = get_user_by_username(username)
    if not row:
        return False, "Usuário não encontrado.", None
    uid, uname, email, phash, role, full_name, pix_key, indicador_id, total_indicados, stage, created_at = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10]
    if check_password(password, phash):
        user = {
            "id": uid,
            "username": uname,
            "email": email,
            "role": role,
            "full_name": full_name,
            "pix_key": pix_key,
            "indicador_id": indicador_id,
            "total_indicados": total_indicados,
            "stage": stage,
            "created_at": created_at
        }
        return True, "Autenticado", user
    return False, "Senha inválida.", None

def delete_user_safe(uid: int) -> tuple[bool, str]:
    """Deleta doações/audit antes de deletar usuário para não quebrar FK."""
    try:
        db_execute("DELETE FROM donations WHERE from_user_id = ? OR to_user_id = ?", (uid, uid))
        db_execute("DELETE FROM audit WHERE user_id = ?", (uid,))
        db_execute("DELETE FROM users WHERE id = ?", (uid,))
        return True, "Usuário excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir usuário: {e}"

def list_indicados(uid: int) -> List[tuple]:
    return db_query("SELECT id, username, full_name, created_at FROM users WHERE indicador_id = ? ORDER BY id", (uid,))

# ============================
# Visualização da rede (árvore)
# ============================
def build_tree(root_id: int, depth: int = 3) -> Dict:
    """Constrói dicionário de árvore até profundidade `depth` (inclusive)."""
    node = get_user_by_id(root_id)
    if not node:
        return {}
    uid = node[0]
    res = {"id": uid, "username": node[1], "full_name": node[5], "children": []}
    if depth <= 0:
        return res
    children = db_query("SELECT id FROM users WHERE indicador_id = ?", (uid,))
    for (cid,) in children:
        res["children"].append(build_tree(cid, depth - 1))
    return res

def render_tree(tree: Dict, level: int = 0):
    if not tree:
        return
    indent = " " * (4 * level)
    st.write(f"{indent}- **{tree['username']}** — {tree.get('full_name') or ''} (id: {tree['id']})")
    for child in tree.get("children", []):
        render_tree(child, level + 1)

# ============================
# UI helpers
# ============================
if "user" not in st.session_state:
    st.session_state["user"] = None

def login_form():
    st.sidebar.subheader("🔐 Login")
    user = st.sidebar.text_input("Usuário", key="login_user")
    pw = st.sidebar.text_input("Senha", type="password", key="login_pass")
    if st.sidebar.button("Entrar"):
        ok, msg, data = authenticate(user, pw)
        if ok:
            st.session_state["user"] = data
            st.sidebar.success(f"Olá, {data['full_name'] or data['username']} (id: {data['id']})")
        else:
            st.sidebar.error(msg)

def logout_action():
    st.session_state["user"] = None
    st.experimental_set_query_params()  # limpa params se quiser

def sidebar_user_block():
    u = st.session_state["user"]
    st.sidebar.markdown(f"**{u['full_name'] or u['username']}**")
    st.sidebar.caption(f"ID: {u['id']} • Stage: {u['stage']}")
    st.sidebar.write(f"Seu código de indicação (ID): **{u['id']}**")
    if st.sidebar.button("Sair"):
        logout_action()

# ============================
# Páginas
# ============================
def page_home():
    st.title(f"🤝 {APP_NAME}")
    st.markdown("Bem-vindo ao painel da rede. Cada usuário é um indicador — ao indicar 12 pessoas você sobe de estágio.")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estágio 1 (valor)", f"R$ {STAGE_AMOUNTS[1]:.2f}")
    c2.metric("Estágio 2 (valor)", f"R$ {STAGE_AMOUNTS[2]:.2f}")
    c3.metric("Estágio 3 (valor)", f"R$ {STAGE_AMOUNTS[3]:.2f}")
    st.markdown("### How it works (resumo)")
    st.write(
        f"- Cada usuário que você cadastrar diretamente conta como 1 indicado.\n"
        f"- Ao completar **{MAX_INDICADOS_POR_CICLO}** indicados diretos, você sobe de estágio (se ainda houver estágio disponível).\n"
        f"- Você pode cadastrar indicados dentro do seu painel (opção 'Registrar' enquanto logado) ou compartilhar seu código (id)."
    )

def page_register():
    st.header("📝 Registrar novo usuário")
    # Captura o ref (id ou username) da query string
    query_ref = st.query_params.get("ref", [None])[0]
    inferred_indicator_id = None
    if query_ref:
        # tenta interpretar como id (int) primeiro, senão como username
        try:
            cand_id = int(query_ref)
            row = get_user_by_id(cand_id)
            if row:
                inferred_indicator_id = cand_id
        except Exception:
            row = get_user_by_username(query_ref)
            if row:
                inferred_indicator_id = row[0]
    col1, col2 = st.columns([2,1])
    with col1:
        r_username = st.text_input("Usuário (único)", key="r_username")
        r_full = st.text_input("Nome completo", key="r_full")
        r_email = st.text_input("E-mail (opcional)", key="r_email")
        r_pix = st.text_input("Chave PIX (opcional)", key="r_pix")
    with col2:
        r_pass = st.text_input("Senha", type="password", key="r_pass")
        # Se o usuário está logado, oferecemos cadastrar como seu indicado direto
        r_as_my_indicado = False
        if st.session_state["user"]:
            r_as_my_indicado = st.checkbox("Cadastrar como meu indicado (vou usar meu ID como indicador)", value=True)
        # Mostrar inferred ref
        if inferred_indicator_id:
            st.info(f"Este cadastro foi iniciado com indicação (ref={query_ref}). Indicador sugerido: id {inferred_indicator_id}")
        else:
            if "ref" in st.query_params:
                st.warning("O parâmetro ref foi informado, mas não foi possível localizar o indicador indicado.")
        if st.button("Registrar usuário"):
            indicador_id_to_use = None
            if r_as_my_indicado and st.session_state["user"]:
                indicador_id_to_use = st.session_state["user"]["id"]
            elif inferred_indicator_id:
                indicador_id_to_use = inferred_indicator_id
            # create user
            ok, msg, new_id = create_user(r_username.strip(), r_email.strip() or None, r_pass, r_full.strip() or None, r_pix.strip() or None, indicador_id_to_use)
            if ok:
                st.success(msg + (f" Novo id: {new_id}" if new_id else ""))
                st.info("Faça login na barra lateral para acessar seu painel.")
            else:
                st.error(msg)

def page_dashboard():
    require_login = st.session_state["user"] is not None
    if not require_login:
        st.warning("Faça login para ver o dashboard.")
        return
    u = st.session_state["user"]
    st.header(f"🏠 Dashboard — {u['full_name'] or u['username']}")
    col1, col2 = st.columns([2,1])
    with col1:
        st.markdown("**Seu Código de Indicação**")
        st.code(str(u["id"]))
        st.markdown("**Seus indicados diretos**")
        indicados = list_indicados(u["id"])
        if not indicados:
            st.info("Você ainda não indicou ninguém.")
        else:
            df = pd.DataFrame(indicados, columns=["ID", "Usuário", "Nome", "Criado em"])
            st.dataframe(df, use_container_width=True)
    with col2:
        st.metric("Estágio atual", u["stage"])
        st.metric("Indicados diretos (este ciclo)", u["total_indicados"])
        st.markdown("---")
        st.write("A cada 12 indicados diretos você sobe de estágio automaticamente (se houver próximo estágio).")

    st.markdown("---")
    st.subheader("Cadastrar indicado direto (crie um usuário vinculado ao seu id)")
    with st.form("form_indicar"):
        n_user = st.text_input("Usuário (único)")
        n_name = st.text_input("Nome completo")
        n_email = st.text_input("E-mail (opcional)")
        n_pass = st.text_input("Senha", type="password")
        n_pix = st.text_input("PIX (opcional)")
        submitted = st.form_submit_button("Cadastrar indicado")
        if submitted:
            indicador_id = u["id"]
            ok, msg, new_id = create_user(n_user.strip(), n_email.strip() or None, n_pass, n_name.strip() or None, n_pix.strip() or None, indicador_id)
            if ok:
                st.success(msg + f" (id:{new_id})")
                # atualizar sessão do usuário (fetch fresh)
                fresh = get_user_by_id(u["id"])
                if fresh:
                    st.session_state["user"]["total_indicados"] = fresh[8]
                    st.session_state["user"]["stage"] = fresh[9]
            else:
                st.error(msg)

def page_rede():
    st.header("🌳 Rede de Indicações (visão árvore)")
    # escolha usuário raiz (por id ou por username)
    root_choice = st.text_input("Mostrar árvore a partir do ID do usuário (deixe vazio para seu ID se logado)")
    root_id = None
    if root_choice.strip():
        try:
            root_id = int(root_choice.strip())
        except:
            u = get_user_by_username(root_choice.strip())
            if u:
                root_id = u[0]
    else:
        if st.session_state["user"]:
            root_id = st.session_state["user"]["id"]
    if not root_id:
        st.info("Informe um ID ou faça login para ver sua rede.")
        return
    depth = st.slider("Profundidade da árvore", 1, 6, 3)
    tree = build_tree(root_id, depth)
    if not tree:
        st.error("Usuário raiz não encontrado.")
        return
    render_tree(tree, 0)

def page_admin():
    if not st.session_state["user"]:
        st.warning("Faça login com conta admin.")
        return
    if st.session_state["user"]["role"] != "admin":
        st.error("Área restrita a administradores.")
        return
    st.header("🛠️ Painel Admin")
    users = db_query("SELECT id, username, full_name, email, role, total_indicados, stage, indicador_id, created_at FROM users ORDER BY id", ())
    df = pd.DataFrame(users, columns=["ID", "Usuário", "Nome", "Email", "Role", "TotalIndicados", "Stage", "IndicadorID", "Criado"])
    st.dataframe(df, use_container_width=True)

    st.subheader("Excluir usuário (seguro)")
    del_id = st.number_input("ID para excluir", min_value=1, step=1)
    if st.button("Excluir usuário"):
        ok, msg = delete_user_safe(del_id)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# ============================
# Router / run
# ============================
# Sidebar: login or user block
if st.session_state["user"] is None:
    login_form()
else:
    sidebar_user_block()

# Menu
pages = {
    "Início": page_home,
    "Registrar": page_register,
    "Dashboard": page_dashboard,
    "Rede": page_rede,
}
# Add Admin page if logged as admin
if st.session_state["user"] and st.session_state["user"]["role"] == "admin":
    pages["Admin"] = page_admin

choice = st.sidebar.selectbox("Menu", list(pages.keys()))
pages[choice]()
