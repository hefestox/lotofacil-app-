import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import hashlib
import os
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam


# ========================
# Funções de login
# ========================
def carregar_usuarios():
    try:
        with open("usuarios.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("Arquivo de usuários não encontrado! Crie 'usuarios.json'.")
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
# Funções auxiliares do app
# ========================
def converter_para_binario(historico):
    historico_binario = []
    for concurso in historico:
        binario = [1 if i in concurso else 0 for i in range(1, 26)]
        historico_binario.append(binario)
    return np.array(historico_binario)


def treinar_modelo(historico_binario):
    X = historico_binario[:-1]
    y = historico_binario[1:]

    model = Sequential()
    model.add(Dense(128, input_dim=25, activation='relu'))
    model.add(Dense(64, activation='relu'))
    model.add(Dense(25, activation='sigmoid'))
    model.compile(loss='binary_crossentropy', optimizer=Adam(learning_rate=0.001))
    model.fit(X, y, epochs=100, verbose=0)
    model.save("modelo_lotofacil.h5")
    return model


def carregar_ou_treinar(historico_binario):
    if os.path.exists("modelo_lotofacil.h5"):
        model = load_model("modelo_lotofacil.h5")
    else:
        model = treinar_modelo(historico_binario)
    return model


def gerar_previsao_nn(model, ultimo_concurso, excluir_dezenas=[], n_jogos=1):
    jogos = []
    base = np.array(ultimo_concurso).reshape(1, -1)
    for _ in range(n_jogos):
        previsao = model.predict(base)[0]
        for dez in excluir_dezenas:
            if 1 <= dez <= 25:
                previsao[dez - 1] = 0
        dezenas_sugeridas = np.argsort(previsao)[-15:] + 1
        jogos.append(sorted(list(dezenas_sugeridas)))
    return jogos, previsao


# ========================
# Interface Streamlit
# ========================
st.set_page_config(
    page_title="Previsão Lotofácil",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

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
# Página principal
# ========================
if st.session_state["logado"]:
    st.markdown("<h1 style='text-align:center; color:#ff4b4b;'>🎯 Previsão Lotofácil</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center; font-size:18px;'>Carregue seu histórico e veja as dezenas mais prováveis de sair!</p>",
        unsafe_allow_html=True)

    arquivo = st.file_uploader("Escolha o arquivo Excel com histórico", type=["xls", "xlsx"])

    if arquivo is not None:
        df = pd.read_excel(arquivo)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.fillna(0).astype(int)
        historico_dezenas = df.values.tolist()
        historico_binario = converter_para_binario(historico_dezenas)

        st.success("✅ Arquivo carregado e convertido com sucesso!")

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Escolha dezenas para excluir")
            excluir_dezenas = st.multiselect("Selecione dezenas (opcional)", options=list(range(1, 26)))
            n_jogos = st.number_input("Quantos jogos deseja gerar?", min_value=1, max_value=20, value=1, step=1)
        with col2:
            if st.button("Gerar Previsão"):
                model = carregar_ou_treinar(historico_binario)
                jogos, previsao_final = gerar_previsao_nn(model, historico_binario[-1], excluir_dezenas, n_jogos)

                st.subheader("Jogos sugeridos:")
                dez_colors = px.colors.qualitative.Pastel
                for idx, jogo in enumerate(jogos):
                    st.markdown(
                        f"**Jogo {idx + 1}:** " + " ".join([f"<span style='color:#ff4b4b;'>{d}</span>" for d in jogo]),
                        unsafe_allow_html=True)

                st.subheader("Probabilidade final (rede neural):")
                fig = px.bar(x=list(range(1, 26)), y=previsao_final, labels={"x": "Dezenas", "y": "Probabilidade"},
                             color=previsao_final, color_continuous_scale="plasma")
                fig.update_layout(xaxis=dict(dtick=1))
                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Histórico de concursos")
        st.dataframe(df, use_container_width=True)
