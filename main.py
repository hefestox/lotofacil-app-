import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import hashlib

# ========================
# Funções de login
# ========================
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
# Funções auxiliares do app
# ========================
def converter_para_binario(historico):
    historico_binario = []
    for concurso in historico:
        binario = [1 if i in concurso else 0 for i in range(1, 26)]
        historico_binario.append(binario)
    return np.array(historico_binario)

def gerar_previsao(historico_binario, excluir_dezenas=[]):
    media = np.mean(historico_binario, axis=0)
    for dez in excluir_dezenas:
        if 1 <= dez <= 25:
            media[dez - 1] = 0
    dezenas_sugeridas = np.argsort(media)[-15:] + 1
    return sorted(list(dezenas_sugeridas)), media

# ========================
# Interface Streamlit
# ========================
st.set_page_config(
    page_title="Previsão Lotofácil",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded"
)

# Inicializar estado de login
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
    st.markdown(
        "<h1 style='text-align: center; color:#ff4b4b;'>🎯 Previsão Lotofácil</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='text-align: center; font-size:18px;'>Carregue seu histórico e veja as dezenas mais prováveis de sair!</p>",
        unsafe_allow_html=True
    )

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
            excluir_dezenas = st.multiselect(
                "Selecione dezenas (opcional)",
                options=list(range(1, 26))
            )
        with col2:
            if st.button("Gerar Previsão"):
                dezenas, media = gerar_previsao(historico_binario, excluir_dezenas)
                st.subheader("Dezenas sugeridas:")

                # Dezenas em cards coloridos
                dez_colors = px.colors.qualitative.Pastel
                for idx, dez in enumerate(dezenas):
                    color = dez_colors[idx % len(dez_colors)]
                    st.markdown(f"<div style='display:inline-block; margin:5px; padding:10px; background-color:{color}; border-radius:10px; font-size:20px;'>{dez}</div>", unsafe_allow_html=True)

                # Gráfico de probabilidade colorido
                fig = px.bar(
                    x=list(range(1, 26)),
                    y=media,
                    labels={"x": "Dezenas", "y": "Probabilidade"},
                    title="Probabilidade de cada dezena",
                    color=media,
                    color_continuous_scale="plasma"
                )
                fig.update_layout(xaxis=dict(dtick=1))
                st.plotly_chart(fig, use_container_width=True)

        st.subheader("Histórico de concursos")
        st.dataframe(df, use_container_width=True)

