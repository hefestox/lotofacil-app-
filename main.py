import os
import json
import random
import sqlite3
from datetime import datetime

import bcrypt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from tensorflow.keras.layers import Dense
from tensorflow.keras.models import Sequential

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
# UTILIDADES DE NEGÓCIO
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

def salvar_jogo(user_id, n_dezenas, numbers, strategy, concurso=None):
    db_execute(
        "INSERT INTO games(user_id, n_dezenas, numbers_json, strategy, created_at, concurso) VALUES (?,?,?,?,?,?)",
        (user_id, n_dezenas, json.dumps(numbers), strategy, datetime.utcnow().isoformat(), concurso)
    )
    log_action(user_id, "SAVE_GAME", {"n": n_dezenas, "numbers": numbers, "strategy": strategy, "concurso": concurso})

def listar_jogos(user_id, limit=200, as_df=True):
    rows = db_query(
        "SELECT id, n_dezenas, numbers_json, strategy, created_at, concurso FROM games WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit), as_df=as_df
    )
    if as_df and not isinstance(rows, pd.DataFrame):
        rows = pd.DataFrame(rows, columns=["id","n_dezenas","numbers_json","strategy","created_at","concurso"])
    if isinstance(rows, pd.DataFrame) and not rows.empty:
        rows["dezenas"] = rows["numbers_json"].apply(lambda s: ", ".join(map(str, json.loads(s))))
        rows = rows[["id","n_dezenas","dezenas","strategy","concurso","created_at"]]
    return rows

def debitar_creditos(user_id, qnt_dezenas=15):
    mult = {15:1, 16:2, 17:3}
    custo = mult.get(qnt_dezenas, 1)
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
# FUNÇÕES DE MACHINE LEARNING & HISTÓRICO
# =========================================
def converter_para_binario(historico):
    """
    Recebe uma lista de concursos, cada concurso é lista de dezenas (ex.: [1,4,7,...]).
    Retorna matriz (n_concursos x 25) com 0/1.
    """
    historico_binario = []
    for concurso in historico:
        binario = [1 if i in concurso else 0 for i in range(1, 26)]
        historico_binario.append(binario)
    return np.array(historico_binario, dtype=np.float32)

@st.cache_data
def carregar_historico_arquivo(file):
    """
    Aceita:
      - Excel (.xls/.xlsx) com cada linha = 15 dezenas sorteadas (1..25)
      - CSV com 15 dezenas por linha OU 25 colunas binárias (0/1)
    Retorna matriz binária (n x 25).
    """
    name = file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(file)
    elif name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        raise ValueError("Formato de arquivo não suportado. Use .xlsx, .xls ou .csv")

    # Limpa strings, converte para numérico
    df = df.applymap(lambda x: pd.to_numeric(x, errors="coerce"))
    # Se tem 25 colunas de 0/1, normaliza
    if df.shape[1] >= 25 and set(df.columns[:25]) == set(df.columns[:25]):
        # Pega as primeiras 25 colunas e força 0/1
        m = df.iloc[:, :25].fillna(0).clip(lower=0, upper=1).astype(int).values
        return m.astype(np.float32)

    # Caso contrário, assume que cada linha tem 15 dezenas sorteadas
    df = df.fillna(0).astype(int)
    historico_dezenas = df.values.tolist()
    # filtra zeros e mantém 1..25
    historico_dezenas = [[int(n) for n in linha if 1 <= int(n) <= 25] for linha in historico_dezenas]
    return converter_para_binario(historico_dezenas)

def treinar_rede_neural(historico_binario, epochs=80):
    X = historico_binario[:-1]
    y = historico_binario[1:]
    if len(X) < 2:
        raise ValueError("Histórico insuficiente para treinar (mínimo 2 linhas).")
    model = Sequential()
    model.add(Dense(50, activation='relu', input_dim=25))
    model.add(Dense(25, activation='sigmoid'))
    model.compile(optimizer='adam', loss='binary_crossentropy')
    model.fit(X, y, epochs=epochs, verbose=0)
    return model

def prever_jogo(model, ultimo_concurso, n_dezenas=15):
    pred = model.predict(np.array([ultimo_concurso]))[0]
    dezenas_prob = [(i + 1, float(pred[i])) for i in range(25)]
    dezenas_prob.sort(key=lambda x: x[1], reverse=True)
    jogo = [dez[0] for dez in dezenas_prob[:n_dezenas]]
    return sorted(jogo), np.array([p for _, p in dezenas_prob], dtype=np.float32)

# =========================================
# ESTRATÉGIAS DE GERAÇÃO
# =========================================
def gerar_jogo(n_dezenas=15, strategy="aleatório", historico_binario=None):
    if strategy == "balanceado":
        pares = [n for n in range(1, 26) if n % 2 == 0]
        impares = [n for n in range(1, 26) if n % 2 != 0]
        alvo_pares = n_dezenas // 2
        alvo_impares = n_dezenas - alvo_pares
        escolha = random.sample(pares, alvo_pares) + random.sample(impares, alvo_impares)
        return sorted(validar_dezenas(escolha))
    elif strategy == "predicao" and historico_binario is not None and len(historico_binario) > 2:
        model = treinar_rede_neural(np.array(historico_binario, dtype=np.float32), epochs=50)
        ultimo = np.array(historico_binario, dtype=np.float32)[-1]
        jogo, _ = prever_jogo(model, ultimo, n_dezenas=n_dezenas)
        return jogo
    else:
        return sorted(random.sample(range(1, 26), n_dezenas))

# =========================================
# CONFERÊNCIA DE RESULTADOS
# =========================================
def conferir_resultados(resultado, jogos, valor_aposta):
    resultados = []
    total_lucro = 0.0
    for i, jogo in enumerate(jogos, 1):
        acertos = len(set(jogo) & set(resultado))
        premio = PREMIACAO.get(acertos, 0.0)
        lucro = premio - float(valor_aposta)
        total_lucro += lucro
        resultados.append({
            "Jogo": i,
            "Dezenas": ", ".join(map(str, sorted(jogo))),
            "Acertos": acertos,
            "Prêmio (R$)": round(premio, 2),
            "Lucro/Prejuízo (R$)": round(lucro, 2)
        })
    return resultados, round(total_lucro, 2)

# =========================================
# UI LOGIN / REGISTRO
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
    total_jogos = 0 if isinstance(jogos_df, pd.DataFrame) and jogos_df.empty else (len(jogos_df) if isinstance(jogos_df, pd.DataFrame) else 0)
    col1, col2, col3 = st.columns(3)
    col1.metric("Jogos salvos", total_jogos)
    col2.metric("Plano atual", st.session_state["user"]["plan"])
    col3.metric("Créditos", st.session_state["user"]["credits"])
    st.caption("⚠️ Este aplicativo é educativo. Loterias são jogos de azar; não há garantia de ganhos. Jogue com responsabilidade.")

def page_previsao_inteligente():
    """
    Nova página (vinda do primeiro app) com upload de histórico, treino da rede, exibição
    do jogo previsto com “chips” coloridos e gráfico de probabilidades. Permite salvar o jogo.
    """
    require_login()
    st.subheader("🎯 Previsão Inteligente (Rede Neural)")
    uid = st.session_state["user"]["id"]
    plano = st.session_state["user"]["plan"]
    max_dezenas = PLANOS[plano]["max_dezenas"]

    colA, colB = st.columns([2, 1])
    with colA:
        file = st.file_uploader("Carregue histórico (.xlsx/.xls/.csv)", type=["xlsx", "xls", "csv"], key="hist_previsao")
        n_dezenas = 15 if max_dezenas == 15 else st.slider("Quantidade de dezenas do palpite", 15, max_dezenas, 15, 1)
        epochs = st.slider("Épocas de treino", 20, 200, 80, 10)
    with colB:
        concurso = st.text_input("Concurso (opcional)", "")

    if file is not None:
        try:
            hist = carregar_historico_arquivo(file)
            st.success(f"✅ Histórico carregado: {hist.shape[0]} concursos.")

            if st.button("Gerar Previsão"):
                model = treinar_rede_neural(hist, epochs=epochs)
                ultimo = hist[-1]
                jogo_prev, probs = prever_jogo(model, ultimo, n_dezenas=n_dezenas)

                # Persistir na sessão para não sumir
                st.session_state["pred_jogo"] = jogo_prev
                st.session_state["pred_probs"] = probs

            if "pred_jogo" in st.session_state and "pred_probs" in st.session_state:
                st.markdown("### 🎯 Jogo Previsto:")
                dez_colors = px.colors.qualitative.Pastel
                st.markdown(
                    "".join([
                        f"<span style='display:inline-block; margin:3px; padding:6px 8px; background-color:{dez_colors[i % len(dez_colors)]}; border-radius:8px; font-weight:600;'>{num}</span>"
                        for i, num in enumerate(st.session_state["pred_jogo"])
                    ]),
                    unsafe_allow_html=True
                )

                fig = px.bar(
                    x=list(range(1, 26)),
                    y=st.session_state["pred_probs"],
                    labels={"x": "Dezenas", "y": "Probabilidade"},
                    title="Probabilidade de cada dezena (rede neural)",
                    color=st.session_state["pred_probs"],
                    color_continuous_scale="plasma"
                )
                fig.update_layout(xaxis=dict(dtick=1))
                st.plotly_chart(fig, use_container_width=True)

                col1, col2 = st.columns([1, 2])
                with col1:
                    if st.button("💾 Salvar este palpite"):
                        ok, msg = debitar_creditos(uid, len(st.session_state["pred_jogo"]))
                        if ok:
                            salvar_jogo(uid, len(st.session_state["pred_jogo"]), st.session_state["pred_jogo"], "predicao", concurso if concurso.strip() else None)
                            st.success(f"Palpite salvo! {msg}")
                            # Atualiza créditos no estado
                            row = get_user_by_username(st.session_state["user"]["username"])
                            if row:
                                _, _, _, _, _, _, credits = row
                                st.session_state["user"]["credits"] = credits
                        else:
                            st.error(msg)
                with col2:
                    st.info("Dica: você pode conferir este palpite depois em **Meus Jogos** ou na página **Conferir Resultado**.")
        except Exception as e:
            st.error(f"Erro ao processar histórico: {e}")
    else:
        st.info("📄 Envie um arquivo de histórico para treinar e gerar o palpite.")

def page_gerar_jogos():
    require_login()
    st.subheader("🎲 Gerar Jogos (Estratégias)")
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
        uploaded_file = st.file_uploader("Carregar histórico (.csv/.xlsx/.xls) para rede neural", type=["csv","xlsx","xls"])
        if uploaded_file is not None:
            try:
                hb = carregar_historico_arquivo(uploaded_file)
                historico_binario = hb.tolist()
                st.success(f"Histórico carregado ({hb.shape[0]} concursos).")
            except Exception as e:
                st.error(f"Erro ao carregar histórico: {e}")

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
            st.error(f"Erro ao gerar jogo: {e}")

def page_meus_jogos():
    require_login()
    st.subheader("📚 Meus Jogos")
    uid = st.session_state["user"]["id"]
    df = listar_jogos(uid, limit=500, as_df=True)
    if isinstance(df, pd.DataFrame) and df.empty:
        st.info("Nenhum jogo salvo ainda.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8"), "meus_jogos.csv", "text/csv")

def page_conferir_resultado():
    """
    Nova página integrada (do primeiro app):
    - Digitar resultado oficial
    - Conferir jogos colados/manual OU selecionar dos jogos salvos
    - Exibe tabela com acertos, prêmio e lucro total
    """
    require_login()
    st.subheader("📊 Conferir Resultado")

    col1, col2 = st.columns([2, 1])
    with col1:
        resultado_input = st.text_input(
            "Resultado oficial (15 dezenas separadas por vírgula):",
            "1,4,5,7,8,10,12,13,14,18,20,21,22,23,24",
            key="resultado_oficial"
        )
    with col2:
        valor_aposta = st.number_input("Valor por aposta (R$):", min_value=0.0, value=4.50, step=0.50, key="valor_aposta")

    st.markdown("#### Escolha como deseja conferir")
    modo = st.radio("Modo", ["Colar jogos manualmente", "Usar jogos salvos"])

    jogos = []
    if modo == "Colar jogos manualmente":
        jogos_input = st.text_area(
            "Jogos (cada linha = 1 jogo com 15 dezenas separadas por vírgula):",
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15\n"
            "2,4,5,7,8,10,12,13,14,16,18,20,21,23,25",
            key="jogos_texto"
        )
        if st.button("Conferir (manual)"):
            try:
                resultado = [int(n) for n in resultado_input.split(",")]
                linhas = [l.strip() for l in jogos_input.strip().splitlines() if l.strip()]
                jogos = [[int(n) for n in linha.split(",")] for linha in linhas]
                res, total = conferir_resultados(resultado, jogos, valor_aposta)
                st.success("✅ Resultados conferidos!")
                st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
                st.markdown(f"**Lucro/Prejuízo total: R$ {total:.2f}**")
                st.download_button("⬇️ Baixar conferência (CSV)", pd.DataFrame(res).to_csv(index=False).encode("utf-8"), "conferencia.csv", "text/csv")
            except Exception as e:
                st.error(f"Erro ao processar os dados: {e}")
    else:
        # Usar jogos salvos
        uid = st.session_state["user"]["id"]
        df = listar_jogos(uid, limit=500, as_df=True)
        if isinstance(df, pd.DataFrame) and df.empty:
            st.info("Você não possui jogos salvos.")
            return
        # Filtros
        with st.expander("Filtrar jogos"):
            concurso_filtro = st.text_input("Concurso (deixe em branco para todos)")
            estrategia = st.multiselect("Estratégia", options=["aleatório","balanceado","predicao"], default=["aleatório","balanceado","predicao"])
            df_filtrado = df.copy()
            if concurso_filtro.strip():
                df_filtrado = df_filtrado[df_filtrado["concurso"].fillna("").str.contains(concurso_filtro.strip(), case=False)]
            if estrategia:
                df_filtrado = df_filtrado[df_filtrado["strategy"].isin(estrategia)]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

        ids_sel = st.multiselect("Selecione os IDs dos jogos para conferir", df_filtrado["id"].tolist())
        if st.button("Conferir (jogos salvos)"):
            try:
                resultado = [int(n) for n in resultado_input.split(",")]
                linhas = df_filtrado[df_filtrado["id"].isin(ids_sel)]["dezenas"].tolist()
                jogos = [[int(n) for n in linha.split(",")] for linha in linhas]
                res, total = conferir_resultados(resultado, jogos, valor_aposta)
                st.success("✅ Resultados conferidos!")
                st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
                st.markdown(f"**Lucro/Prejuízo total: R$ {total:.2f}**")
                st.download_button("⬇️ Baixar conferência (CSV)", pd.DataFrame(res).to_csv(index=False).encode("utf-8"), "conferencia.csv", "text/csv")
            except Exception as e:
                st.error(f"Erro ao processar os dados: {e}")

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
        st.dataframe(df, use_container_width=True, hide_index=True)
        with st.expander("Gerenciar usuários"):
            uid = st.number_input("ID do usuário", min_value=1, step=1)
            c1, c2, c3 = st.columns(3)
            if c1.button("Adicionar 10 créditos"):
                db_execute("UPDATE users SET credits = credits + 10 WHERE id = ?", (uid,))
                st.success("Créditos adicionados!")
            if c2.button("Remover usuário"):
                db_execute("DELETE FROM users WHERE id = ?", (uid,))
                st.success("Usuário removido!")
            new_plan = c3.selectbox("Alterar plano", list(PLANOS.keys()))
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
        "Previsão Inteligente": page_previsao_inteligente,  # <- adicionada
        "Gerar Jogos": page_gerar_jogos,
        "Conferir Resultado": page_conferir_resultado,      # <- adicionada
        "Meus Jogos": page_meus_jogos,
        "Admin": page_admin
    }
elif st.session_state.get("user"):
    PAGES = {
        "Dashboard": page_dashboard,
        "Previsão Inteligente": page_previsao_inteligente,  # <- adicionada
        "Gerar Jogos": page_gerar_jogos,
        "Conferir Resultado": page_conferir_resultado,      # <- adicionada
        "Meus Jogos": page_meus_jogos
    }
else:
    PAGES = {}

if PAGES:
    st.sidebar.subheader("Menu")
    current_page = st.sidebar.radio("Ir para", list(PAGES.keys()))
    # Botão de logout
    if st.sidebar.button("Logout"):
        st.session_state["user"] = None
        st.experimental_rerun()
    PAGES[current_page]()
