import streamlit as st
import pandas as pd
import numpy as np
import hashlib
import sqlite3
import plotly.express as px


# ========================
# BANCO DE DADOS LOCAL
# ========================
def criar_tabelas():
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL
                )""")
    conn.commit()
    conn.close()


def cadastrar_usuario(username, password):
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, password))
    conn.commit()
    conn.close()


def verificar_usuario(username, password):
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE username=? AND password=?", (username, password))
    data = c.fetchone()
    conn.close()
    return data


# ========================
# SENHAS
# ========================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ========================
# INTERFACE
# ========================
st.set_page_config(page_title="LotoFácil Revolution", layout="wide")
st.title("💰 LotoFácil Revolution")

# Sessão para armazenar previsões
if "previsoes" not in st.session_state:
    st.session_state["previsoes"] = None
if "historico" not in st.session_state:
    st.session_state["historico"] = None

menu = ["Login", "Cadastro", "Sistema"]
escolha = st.sidebar.selectbox("Menu", menu)

# ========================
# CADASTRO
# ========================
if escolha == "Cadastro":
    st.subheader("📌 Cadastro de Usuário")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Cadastrar"):
        if usuario and senha:
            criar_tabelas()
            try:
                cadastrar_usuario(usuario, hash_password(senha))
                st.success("✅ Usuário cadastrado com sucesso!")
            except:
                st.error("⚠️ Usuário já existe!")
        else:
            st.warning("Preencha todos os campos.")

# ========================
# LOGIN
# ========================
elif escolha == "Login":
    st.subheader("🔐 Login")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        criar_tabelas()
        user = verificar_usuario(usuario, hash_password(senha))
        if user:
            st.session_state["logado"] = True
            st.success("✅ Login realizado com sucesso!")
        else:
            st.error("Usuário ou senha incorretos.")

# ========================
# SISTEMA PRINCIPAL
# ========================
elif escolha == "Sistema":
    if "logado" not in st.session_state or not st.session_state["logado"]:
        st.warning("⚠️ Faça login para acessar o sistema.")
    else:
        abas = st.tabs(["📂 Histórico", "🎯 Conferir Jogos", "🤖 Previsão", "📊 Análise"])

        # ================= HISTÓRICO =================
        with abas[0]:
            st.subheader("📂 Upload do Histórico")
            arquivo = st.file_uploader("Envie o arquivo Excel/CSV", type=["xlsx", "csv"])
            if arquivo:
                try:
                    if arquivo.name.endswith(".csv"):
                        df = pd.read_csv(arquivo, header=None)
                    else:
                        df = pd.read_excel(arquivo, header=None)

                    # Ajuste para garantir 15 dezenas por jogo
                    df = df.dropna(axis=1, how="all")
                    df = df.iloc[:, :15]
                    df.columns = [f"D{c + 1}" for c in range(df.shape[1])]
                    st.session_state["historico"] = df

                    st.success(f"✅ {len(df)} concursos carregados com sucesso!")
                    st.dataframe(df.tail(10))
                except Exception as e:
                    st.error(f"Erro ao ler arquivo: {e}")

        # ================= CONFERIR JOGOS =================
        with abas[1]:
            st.subheader("🎯 Conferir Jogos")
            if st.session_state["historico"] is not None:
                numeros = st.text_area("Digite suas dezenas separadas por espaço:")
                if st.button("Conferir"):
                    try:
                        dezenas = sorted([int(x) for x in numeros.split()])
                        if len(dezenas) != 15:
                            st.error("Você precisa digitar exatamente 15 dezenas.")
                        else:
                            df = st.session_state["historico"]
                            resultados = []
                            for idx, row in df.iterrows():
                                acertos = len(set(dezenas) & set(row))
                                resultados.append(acertos)
                            st.write("✅ Conferência concluída!")
                            st.bar_chart(pd.Series(resultados).value_counts().sort_index())
                    except:
                        st.error("Erro ao processar dezenas.")
            else:
                st.info("Envie primeiro o histórico.")

        # ================= PREVISÃO =================
        with abas[2]:
            st.subheader("🤖 Gerar Previsão")
            if st.button("Gerar Previsão"):
                st.session_state["previsoes"] = sorted(np.random.choice(range(1, 26), 15, replace=False))

            if st.session_state["previsoes"]:
                st.success(f"Previsão Gerada: {st.session_state['previsoes']}")

        # ================= ANÁLISE =================
        with abas[3]:
            st.subheader("📊 Análise de Frequência")
            if st.session_state["historico"] is not None:
                df = st.session_state["historico"]
                freq = pd.Series(df.values.ravel()).value_counts().sort_index()
                fig = px.bar(freq, x=freq.index, y=freq.values, title="Frequência das Dezenas")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Envie primeiro o histórico.")
