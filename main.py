import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import hashlib
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense


# ========================
# Funções de login
# ========================
@st.cache_data
def carregar_usuarios():
    try:
        with open("usuarios.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("Arquivo de usuários não encontrado! Crie 'usuarios.json' na pasta do projeto.")
        return {}
    except json.JSONDecodeError:
        st.error("Arquivo de usuários está vazio ou com erro de formatação JSON.")
        return {}


def verificar_login(usuario, senha, usuarios):
    if usuario in usuarios:
        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        if senha_hash == usuarios[usuario]["password"]:
            return True
    return False


# ========================
# Funções auxiliares
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


# ========================
# Configuração da página
# ========================
st.set_page_config(
    page_title="Previsão Lotofácil",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

# ========================
# Inicializar estado de login
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
            st.sidebar.success(f"Bem-vindo, {usuario}!")
        else:
            st.sidebar.error("Usuário ou senha incorretos.")

# ========================
# Página principal (rede neural)
# ========================
if st.session_state["logado"]:
    st.markdown("<h1 style='text-align: center; color:#ff4b4b;'>🎯 Previsão Lotofácil</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align: center; font-size:18px;'>Carregue seu histórico e veja as dezenas mais prováveis de sair!</p>",
        unsafe_allow_html=True)

    arquivo = st.file_uploader("Escolha o arquivo Excel com histórico", type=["xls", "xlsx"])

    if arquivo is not None:
        @st.cache_data
        def carregar_historico(arquivo):
            df = pd.read_excel(arquivo)
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df.fillna(0).astype(int)


        df = carregar_historico(arquivo)
        historico_dezenas = df.values.tolist()
        historico_binario = converter_para_binario(historico_dezenas)

        st.success("✅ Arquivo carregado e convertido com sucesso!")

        if st.button("Gerar Previsão Inteligente"):
            modelo = treinar_rede_neural(historico_binario)
            ultimo = historico_binario[-1]
            jogo_previsto, probabilidade = prever_jogo(modelo, ultimo)

            st.subheader("🎯 Jogo Previsto  :")
            dez_colors = px.colors.qualitative.Pastel
            st.markdown(
                "".join([
                            f"<span style='display:inline-block; margin:3px; padding:5px; background-color:{dez_colors[i % len(dez_colors)]}; border-radius:5px;'>{num}</span>"
                            for i, num in enumerate(jogo_previsto)]),
                unsafe_allow_html=True
            )

            # Gráfico de probabilidade
            fig = px.bar(
                x=list(range(1, 26)),
                y=probabilidade,
                labels={"x": "Dezenas", "y": "Probabilidade"},
                title="Probabilidade de cada dezena",
                color=probabilidade,
                color_continuous_scale="plasma"
            )
            fig.update_layout(xaxis=dict(dtick=1))
            st.plotly_chart(fig, use_container_width=True)

    # Botão de logout
    if st.sidebar.button("Logout"):
        st.session_state["logado"] = False
        st.experimental_rerun = None
