import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import bcrypt
import random
from datetime import datetime
import plotly.express as px
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense

# =========================================
# CONFIGURAÇÕES
# =========================================
st.set_page_config(page_title="Lotofácil • Painel do Cliente", page_icon="🎯", layout="wide")

PLANOS = {
    "Bronze": {"max_dezenas": 15, "mensalidade": 0},
    "Prata":  {"max_dezenas": 16, "mensalidade": 0},
    "Ouro":   {"max_dezenas": 17, "mensalidade": 0},
}

PREMIACAO = {15: 2_000_000.00, 14: 1500.00, 13: 35.00, 12: 14.00, 11: 7.00}

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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        plan TEXT NOT NULL DEFAULT 'Bronze',
        credits INTEGER NOT NULL DEFAULT 10,
        created_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS games(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        n_dezenas INTEGER NOT NULL,
        numbers_json TEXT NOT NULL,
        strategy TEXT NOT NULL,
        created_at TEXT NOT NULL,
        concurso TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
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

def create_user(username: str, email: str, password: str, role="user", plan="Bronze"):
    now = datetime.utcnow().isoformat()
    ph = hash_password(password)
    try:
        db_execute(
            "INSERT INTO users (username, email, password_hash, role, plan, credits, created_at) VALUES (?,?,?,?,?, ?, ?)",
            (username, email, ph, role, plan, 10, now)
        )
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError:
        return False, "Erro: usuário ou e-mail já existe."

def get_user_by_username(username: str):
    rows = db_query("SELECT id, username, email, password_hash, role, plan, credits FROM users WHERE username = ?", (username,))
    return rows[0] if rows else None

def authenticate(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return False, "Usuário não encontrado."
    uid, uname, email, phash, role, plan, credits = user
    if check_password(password, phash):
        return True, {"id": uid, "username": uname, "email": email, "role": role, "plan": plan, "credits": credits}
    return False, "Senha inválida."

def require_login():
    if not st.session_state.get("user"):
        st.warning("Faça login para continuar.")
        st.stop()

# =========================================
# UTILIDADES
# =========================================
def log_action(user_id, action, payload=None):
    db_execute(
        "INSERT INTO audit(user_id, action, payload, created_at) VALUES (?,?,?,?)",
        (user_id, action, json.dumps(payload) if payload else None, datetime.utcnow().isoformat())
    )

def validar_dezenas(nums):
    if len(nums) == 0:
        raise ValueError("Informe ao menos um número.")
    if any((n < 1 or n > 25) for n in nums):
        raise ValueError("As dezenas devem estar entre 1 e 25.")
    if len(set(nums)) != len(nums):
        raise ValueError("As dezenas não podem repetir.")
    return sorted(nums)

def gerar_jogo(n_dezenas=15, strategy="balanceado", historico_binario=None):
    if strategy == "balanceado":
        pares = [n for n in range(1, 26) if n % 2 == 0]
        impares = [n for n in range(1, 26) if n % 2 != 0]
        alvo_pares = n_dezenas // 2
        alvo_impares = n_dezenas - alvo_pares
        escolha = random.sample(pares, alvo_pares) + random.sample(impares, alvo_impares)
        return sorted(validar_dezenas(escolha))
    elif strategy == "predicao" and historico_binario is not None:
        X = historico_binario[:-1]
        y = historico_binario[1:]
        model = Sequential()
        model.add(Dense(50, activation='relu', input_dim=25))
        model.add(Dense(25, activation='sigmoid'))
        model.compile(optimizer='adam', loss='binary_crossentropy')
        model.fit(X, y, epochs=50, verbose=0)
        ultimo = historico_binario[-1]
        pred = model.predict(np.array([ultimo]))[0]
        dezenas_prob = [(i + 1, pred[i]) for i in range(25)]
        dezenas_prob.sort(key=lambda x: x[1], reverse=True)
        return sorted([dez[0] for dez in dezenas_prob[:n_dezenas]])
    else:
        return sorted(random.sample(range(1,26), n_dezenas))

def salvar_jogo(user_id, n_dezenas, numbers, strategy, concurso=None):
    db_execute(
        "INSERT INTO games(user_id, n_dezenas, numbers_json, strategy, created_at, concurso) VALUES (?,?,?,?,?,?)",
        (user_id, n_dezenas, json.dumps(numbers), strategy, datetime.utcnow().isoformat(), concurso)
    )
    log_action(user_id, "SAVE_GAME", {"n": n_dezenas, "numbers": numbers, "strategy": strategy, "concurso": concurso})

def listar_jogos(user_id, limit=200):
    rows = db_query(
        "SELECT id, n_dezenas, numbers_json, strategy, created_at, concurso FROM games WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit), as_df=True
    )
    if rows.empty:
        return rows
    rows["dezenas"] = rows["numbers_json"].apply(lambda s: ", ".join(map(str, json.loads(s))))
    return rows[["id","n_dezenas","dezenas","strategy","concurso","created_at"]]

def debitar_creditos(user_id, qnt=1):
    mult = {15:1, 16:2, 17:3}
    custo = mult.get(qnt, 1)
    user = db_query("SELECT credits FROM users WHERE id = ?", (user_id,))
    if not user:
        return False, "Usuário não encontrado."
    saldo = user[0][0]
    if saldo < custo:
        return False, "Créditos insuficientes."
    db_execute("UPDATE users SET credits = credits - ? WHERE id = ?", (custo, user_id))
    return True, f"Debitado {custo} crédito(s)."

def set_plan(uid, plan):
    if plan not in PLANOS:
        return False, "Plano inválido."
    db_execute("UPDATE users SET plan = ? WHERE id = ?", (plan, uid))
    log_action(uid, "SET_PLAN", {"plan": plan})
    return True, "Plano atualizado."

# =========================================
# UI LOGIN
# =========================================
def ui_login():
    if "user" not in st.session_state:
        st.session_state["user"] = None

    st.sidebar.title("🎯 Lotofácil")
    st.sidebar.subheader("🔐 Login")
    u = st.sidebar.text_input("Usuário")
    p = st.sidebar.text_input("Senha", type="password")
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Entrar", use_container_width=True):
        ok, data = authenticate(u, p)
        if ok:
            st.session_state["user"] = data
            st.experimental_set_query_params(logged_in="true")
        else:
            st.sidebar.error(data)

    with st.sidebar.expander("Criar conta"):
        nu = st.text_input("Novo usuário", key="nu")
        em = st.text_input("E-mail", key="em")
        pw1 = st.text_input("Senha", type="password", key="pw1")
        pw2 = st.text_input("Confirmar senha", type="password", key="pw2")
        if st.button("Registrar"):
            if not nu or not pw1 or not em:
                st.warning("Preencha usuário, e-mail e senha.")
            elif pw1 != pw2:
                st.error("As senhas não conferem.")
            else:
                ok, msg = create_user(nu, em, pw1)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

# =========================================
# PÁGINAS
# =========================================
def page_dashboard():
    require_login()
    st.subheader("📊 Dashboard")
    uid = st.session_state["user"]["id"]
    jogos_df = listar_jogos(uid, limit=100)
    total_jogos = 0 if jogos_df.empty else len(jogos_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("Jogos salvos", total_jogos)
    col2.metric("Plano atual", st.session_state["user"]["plan"])
    col3.metric("Créditos", st.session_state["user"]["credits"])
    st.caption("⚠️ Este aplicativo é educativo. Loterias são jogos de azar; não há garantia de ganhos. Jogue com responsabilidade.")

def page_gerar_jogos():
    require_login()
    st.subheader("🎲 Gerar Jogos")
    uid = st.session_state["user"]["id"]
    plano = st.session_state["user"]["plan"]
    max_dezenas = PLANOS[plano]["max_dezenas"]

    if max_dezenas == 15:
        n_dezenas = 15
        st.info("Seu plano permite até 15 dezenas.")
    else:
        n_dezenas = st.slider("Quantidade de dezenas", 15, max_dezenas, 15, 1)

    strategy = st.selectbox("Estratégia", ["aleatório", "balanceado", "predicao"])
    historico_binario = None
    if strategy == "predicao":
        uploaded_file = st.file_uploader("Carregar histórico (.csv) para rede neural", type="csv")
        if uploaded_file is not None:
            df_hist = pd.read_csv(uploaded_file)
            historico_binario = df_hist.applymap(lambda x: 1 if x > 0 else 0).values.tolist()

    concurso = st.text_input("Concurso (opcional)")

    if st.button("Gerar Jogo"):
        try:
            jogo = gerar_jogo(n_dezenas, strategy, historico_binario)
            ok, msg = debitar_creditos(uid, n_dezenas)
            if ok:
                salvar_jogo(uid, n_dezenas, jogo, strategy, concurso if concurso.strip() else None)
                st.success(f"Jogo salvo! Dezenas: {', '.join(map(str, jogo))}\n{msg}")
                row = get_user_by_username(st.session_state["user"]["username"])
                if row:
                    _, _, _, _, _, _, credits = row
                    st.session_state["user"]["credits"] = credits
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"Erro ao gerar jogo: {str(e)}")

def page_meus_jogos():
    require_login()
    st.subheader("📚 Meus Jogos")
    uid = st.session_state["user"]["id"]
    df = listar_jogos(uid, limit=500)
    if df.empty:
        st.info("Nenhum jogo salvo ainda.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8"), "meus_jogos.csv", "text/csv")

    # Conferir concurso
    st.subheader("🔍 Conferir Concurso")
    concurso_input = st.text_input("Digite o número do concurso para conferir")
    if st.button("Conferir"):
        if not concurso_input.strip():
            st.warning("Informe o número do concurso.")
        else:
            df_check = df[df['concurso'] == concurso_input.strip()]
            if df_check.empty:
                st.info("Nenhum jogo registrado para este concurso.")
            else:
                st.dataframe(df_check, use_container_width=True, hide_index=True)
                st.success(f"{len(df_check)} jogo(s) encontrado(s) para o concurso {concurso_input.strip()}.")

def page_admin():
    require_login()
    if st.session_state["user"]["role"] != "admin":
        st.error("Acesso negado.")
        return
    st.subheader("🛠️ Painel Admin")
    st.markdown("### Usuários")
    users = db_query("SELECT id, username, email, role, plan, credits FROM users")
    if users:
        df = pd.DataFrame(users, columns=["ID", "Usuário", "Email", "Role", "Plano", "Créditos"])
        st.dataframe(df)
        with st.expander("Gerenciar usuários"):
            uid = st.number_input("ID do usuário", min_value=1, step=1)
            if st.button("Adicionar 10 créditos"):
                db_execute("UPDATE users SET credits = credits + 10 WHERE id = ?", (uid,))
                st.success("Créditos adicionados!")
            if st.button("Remover usuário"):
                db_execute("DELETE FROM users WHERE id = ?", (uid,))
                st.success("Usuário removido!")
            new_plan = st.selectbox("Alterar plano", list(PLANOS.keys()))
            if st.button("Atualizar plano"):
                set_plan(uid, new_plan)
                st.success("Plano atualizado!")

# =========================================
# MAIN
# =========================================
ui_login()

if st.session_state.get("user") and st.session_state["user"]["role"] == "admin":
    PAGES = {
        "Dashboard": page_dashboard,
        "Gerar Jogos": page_gerar_jogos,
        "Meus Jogos": page_meus_jogos,
        "Admin": page_admin
    }
else:
    PAGES = {
        "Dashboard": page_dashboard,
        "Gerar Jogos": page_gerar_jogos,
        "Meus Jogos": page_meus_jogos
    }

st.sidebar.subheader("Menu")
current_page = st.sidebar.radio("Ir para", list(PAGES.keys()))
PAGES[current_page]()
