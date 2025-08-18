import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import hashlib
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
import os

# ========================
# Premiação oficial
# ========================
premiacao = {
    15: 2000000.00,
    14: 1500.00,
    13: 35.00,
    12: 14.00,
    11: 7.00,
}


# ========================
# Funções de login
# ========================
def carregar_usuarios():
    if not os.path.exists("usuarios.json"):
        # Cria admin padrão
        usuarios = {"admin": {"password": hashlib.sha256("admin".encode()).hexdigest()}}
        with open("usuarios.json", "w") as f:
            json.dump(usuarios, f, indent=4)
        return usuarios
    try:
        with open("usuarios.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error("Arquivo de usuários está vazio ou com erro de formatação JSON.")
        return {}


def verificar_login(usuario, senha, usuarios):
    if usuario in usuarios:
        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        return senha_hash == usuarios[usuario]["password"]
    return False


# ========================
# Funções Lotofácil
# ========================
def converter_para_binario(historico):
    historico_binario = []
    for concurso in historico:
        binario = [1 if i in concurso else 0 for i in range(1, 26)]
        historico_binario.append(binario)
    return np.array(historico_binario)


def treinar_rede_neural(historico_binario):
    X = historico_binario[:-1]
    y = historico_binario[1:]
    model = Sequential()
    model.add(Dense(50, activation='relu', input_dim=25))
    model.add(Dense(25, activation='sigmoid'))
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    model.fit(X, y, epochs=100, verbose=0)
    return model


def prever_jogo(model, ultimo_concurso):
    pred = model.predict(np.array([ultimo_concurso]))[0]
    dezenas_prob = [(i + 1, pred[i]) for i in range(25)]
    dezenas_prob.sort(key=lambda x: x[1], reverse=True)
    jogo = [dez[0] for dez in dezenas_prob[:15]]
    return sorted(jogo), pred


def conferir_resultados(resultado, jogos, valor_aposta):
    resultados = []
    total_lucro = 0
    for i, jogo in enumerate(jogos, 1):
        acertos = len(set(jogo) & set(resultado))
        premio = premiacao.get(acertos, 0)
        lucro = premio - valor_aposta
        total_lucro += lucro
        resultados.append({
            "Jogo": i,
            "Acertos": acertos,
            "Prêmio (R$)": premio,
            "Lucro/Prejuízo (R$)": lucro
        })
    return resultados, total_lucro


# ========================
# Função para carregar histórico Excel
# ========================
@st.cache_data
def carregar_historico(arquivo):
    df = pd.read_excel(arquivo)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0).astype(int)


# ========================
# Configuração Streamlit
# ========================
st.set_page_config(
    page_title="Lotofácil App",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

# ========================
# Estado de login
# ========================
if "logado" not in st.session_state:
    st.session_state["logado"] = False

usuarios = carregar_usuarios()

# ========================
# Login
# ========================
if not st.session_state["logado"]:
    st.sidebar.title("🔐 Login")
    usuario = st.sidebar.text_input("Usuário")
    senha = st.sidebar.text_input("Senha", type="password")
    entrar = st.sidebar.button("Entrar")

    if entrar:
        if verificar_login(usuario, senha, usuarios):
            st.session_state["logado"] = True
            st.session_state["usuario"] = usuario
            st.sidebar.success(f"Bem-vindo, {usuario}!")
        else:
            st.sidebar.error("Usuário ou senha incorretos.")

# ========================
# Aplicativo principal
# ========================
if st.session_state["logado"]:
    st.sidebar.subheader("📌 Menu")

    if st.sidebar.button("Logout"):
        st.session_state["logado"] = False
        st.experimental_rerun()

    # Admin pode gerenciar usuários
    if st.session_state["usuario"] == "admin":
        st.sidebar.subheader("👤 Gerenciar usuários")
        novo_usuario = st.sidebar.text_input("Novo usuário")
        nova_senha = st.sidebar.text_input("Senha do novo usuário", type="password")
        if st.sidebar.button("Adicionar usuário"):
            if novo_usuario and nova_senha:
                usuarios[novo_usuario] = {"password": hashlib.sha256(nova_senha.encode()).hexdigest()}
                with open("usuarios.json", "w") as f:
                    json.dump(usuarios, f, indent=4)
                st.sidebar.success(f"Usuário '{novo_usuario}' adicionado com sucesso!")
            else:
                st.sidebar.warning("Preencha usuário e senha para adicionar.")

    # ========================
    # Abas integradas
    # ========================
    st.markdown("<h1 style='text-align: center; color:#ff4b4b;'>🎯 Lotofácil App</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🎯 Previsão Inteligente", "📊 Conferir Resultados"])

    # -------------------------------
    # Aba 1: Previsão Inteligente
    # -------------------------------
    with tab1:
        st.markdown(
            "<p style='text-align: center;'>Carregue seu histórico e veja as dezenas mais prováveis de sair!</p>",
            unsafe_allow_html=True)
        arquivo = st.file_uploader("Escolha o arquivo Excel com histórico", type=["xls", "xlsx"], key="uploader")

        if arquivo is not None:
            df = carregar_historico(arquivo)
            historico_dezenas = df.values.tolist()
            historico_binario = converter_para_binario(historico_dezenas)
            st.success("✅ Arquivo carregado e convertido com sucesso!")

            if st.button("Gerar Previsão Inteligente", key="previsao"):
                modelo = treinar_rede_neural(historico_binario)
                ultimo = historico_binario[-1]
                jogo_previsto, probabilidade = prever_jogo(modelo, ultimo)

                # Salva no session_state
                st.session_state["jogo_previsto"] = jogo_previsto
                st.session_state["probabilidade"] = probabilidade

            # Exibe previsão mesmo sem clicar novamente
            if "jogo_previsto" in st.session_state:
                st.subheader("🎯 Jogo Previsto:")
                dez_colors = px.colors.qualitative.Pastel
                st.markdown(
                    "".join([
                        f"<span style='display:inline-block; margin:3px; padding:5px; background-color:{dez_colors[i % len(dez_colors)]}; border-radius:5px;'>{num}</span>"
                        for i, num in enumerate(st.session_state["jogo_previsto"])]),
                    unsafe_allow_html=True
                )

                fig = px.bar(
                    x=list(range(1, 26)),
                    y=st.session_state["probabilidade"],
                    labels={"x": "Dezenas", "y": "Probabilidade"},
                    title="Probabilidade de cada dezena",
                    color=st.session_state["probabilidade"],
                    color_continuous_scale="plasma"
                )
                fig.update_layout(xaxis=dict(dtick=1))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("⏳ Carregue o arquivo Excel para gerar a previsão.")

    # -------------------------------
    # Aba 2: Conferir Resultados
    # -------------------------------
    with tab2:
        st.markdown("<p style='text-align: center;'>Confira seus jogos com base no resultado oficial!</p>",
                    unsafe_allow_html=True)

        resultado_input = st.text_input(
            "Resultado oficial (15 dezenas separadas por vírgula):",
            "1,4,5,7,8,10,12,13,14,18,20,21,22,23,24",
            key="resultado"
        )

        jogos_input = st.text_area(
            "Jogos (cada linha = 1 jogo com 15 dezenas separadas por vírgula):",
            "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15\n"
            "2,4,5,7,8,10,12,13,14,16,18,20,21,23,25",
            key="jogos"
        )

        valor_aposta = st.number_input("Valor por aposta (R$):", min_value=0.0, value=4.50, step=0.50, key="valor")

        if st.button("Conferir Resultados", key="conferir"):
            try:
                resultado = [int(n) for n in resultado_input.split(",")]
                linhas = jogos_input.strip().splitlines()
                jogos = [[int(n) for n in linha.split(",")] for linha in linhas]

                resultados, total_lucro = conferir_resultados(resultado, jogos, valor_aposta)

                st.success("✅ Resultados conferidos com sucesso!")
                st.table(resultados)
                st.markdown(f"**Lucro/Prejuízo total: R$ {total_lucro:.2f}**")
            except Exception as e:
                st.error(f"Erro ao processar os dados: {e}")

