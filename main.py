consiguir coloca codigo para rodar perfeitamente. porem que me ajuda coloca para treinar em off : e executar apenas  como vc sugeriu encima : import streamlit as st
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

def treinar_modelo(historico_binario):
    if len(historico_binario) < 2:
        st.warning("Histórico muito curto para treinar a rede neural.")
        return None
    X = historico_binario[:-1]
    Y = historico_binario[1:]
    model = Sequential([
        Dense(64, activation='relu', input_dim=25),
        Dense(128, activation='relu'),
        Dense(25, activation='sigmoid')
    ])
    model.compile(optimizer='adam', loss='binary_crossentropy')
    model.fit(X, Y, epochs=50, batch_size=8, verbose=0)
    return model

def gerar_jogos_nn(model, historico_binario, qtd_jogos=1):
    ult_linha = historico_binario[-1].reshape(1, 25)
    predicao = model.predict(ult_linha, verbose=0)[0]
    dezenas_ordenadas = np.argsort(predicao)[-15:] + 1
    jogos = []
    while len(jogos) < qtd_jogos:
        np.random.shuffle(dezenas_ordenadas)
        jogo = tuple(sorted(dezenas_ordenadas[:15]))
        if jogo not in jogos:
            jogos.append(jogo)
    return jogos, predicao

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
    st.markdown("<h1 style='text-align: center; color:#ff4b4b;'>🎯 Previsão Lotofácil</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size:18px;'>Carregue seu histórico e veja as dezenas mais prováveis de sair!</p>", unsafe_allow_html=True)

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
            st.subheader("Quantidade de jogos")
            qtd_jogos = st.number_input("Quantos jogos gerar?", min_value=1, max_value=10, value=1, step=1)

        with col2:
            if st.button("Gerar Previsões NN"):
                model = treinar_modelo(historico_binario)
                if model:
                    jogos, media = gerar_jogos_nn(model, historico_binario, qtd_jogos)
                    st.subheader("Jogos sugeridos pela Rede Neural:")
                    dez_colors = px.colors.qualitative.Pastel
                    for idx, jogo in enumerate(jogos):
                        cores = [dez_colors[i % len(dez_colors)] for i in range(15)]
                        st.markdown(
                            "".join([f"<span style='display:inline-block; margin:3px; padding:5px; background-color:{cores[i]}; border-radius:5px;'>{num}</span>" for i, num in enumerate(jogo)]),
                            unsafe_allow_html=True
                        )

                    # Gráfico de probabilidade
                    fig = px.bar(
                        x=list(range(1, 26)),
                        y=media,
                        labels={"x": "Dezenas", "y": "Probabilidade"},
                        title="Probabilidade de cada dezena (NN)",
                        color=media,
                        color_continuous_scale="plasma"
                    )
                    fig.update_layout(xaxis=dict(dtick=1))
                    st.plotly_chart(fig, use_container_width=True)

        st.subheader("Histórico de concursos")
        st.dataframe(df, use_container_width=True)
