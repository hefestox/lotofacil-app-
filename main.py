import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sklearn.neural_network import MLPClassifier

# ========================
# Funções auxiliares
# ========================
def converter_para_binario(historico):
    historico_binario = []
    for concurso in historico:
        binario = [1 if i in concurso else 0 for i in range(1, 26)]
        historico_binario.append(binario)
    return np.array(historico_binario)

def treinar_rede_neural(X):
    # Previsão de cada dezena separadamente
    modelos = []
    for i in range(X.shape[1]):
        y = X[:, i]  # cada coluna é a presença da dezena
        modelo = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42)
        modelo.fit(X, y)
        modelos.append(modelo)
    return modelos

def gerar_jogo(modelos):
    jogo = []
    for i, modelo in enumerate(modelos):
        prob = modelo.predict_proba(np.zeros((1, 25)))[:, 1][0]
        if prob > 0.5:
            jogo.append(i + 1)
    # Ajustar para exatamente 15 dezenas
    if len(jogo) > 15:
        jogo = sorted(jogo, key=lambda x: np.random.random())[:15]
    elif len(jogo) < 15:
        faltando = list(set(range(1, 26)) - set(jogo))
        np.random.shuffle(faltando)
        jogo += faltando[:15 - len(jogo)]
    return sorted(jogo)

# ========================
# Interface Streamlit
# ========================
st.set_page_config(
    page_title="Lotofácil - Rede Neural",
    layout="wide",
    page_icon="🤖",
    initial_sidebar_state="expanded"
)

st.markdown("<h1 style='text-align: center; color:#ff4b4b;'>🤖 Previsão Lotofácil - Rede Neural</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size:18px;'>Carregue seu histórico e veja os jogos sugeridos pela rede neural!</p>", unsafe_allow_html=True)

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

    qtd_jogos = st.number_input("Quantos jogos gerar?", min_value=1, max_value=10, value=1, step=1)

    if st.button("Gerar jogos com rede neural"):
        with st.spinner("Treinando rede neural e gerando jogos..."):
            modelos = treinar_rede_neural(historico_binario)
            jogos = [gerar_jogo(modelos) for _ in range(qtd_jogos)]

        st.subheader("Jogos sugeridos pela rede neural:")
        dez_colors = px.colors.qualitative.Pastel
        for idx, jogo in enumerate(jogos):
            cores = [dez_colors[i % len(dez_colors)] for i in range(15)]
            st.markdown(
                "".join([f"<span style='display:inline-block; margin:3px; padding:5px; background-color:{cores[i]}; border-radius:5px;'>{num}</span>" for i, num in enumerate(jogo)]),
                unsafe_allow_html=True
            )

        # Gráfico de probabilidade média por dezena
        media = np.mean(historico_binario, axis=0)
        fig = px.bar(
            x=list(range(1, 26)),
            y=media,
            labels={"x": "Dezenas", "y": "Probabilidade Histórica"},
            title="Probabilidade histórica de cada dezena",
            color=media,
            color_continuous_scale="plasma"
        )
        fig.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig, use_container_width=True)
