import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ========================
# Funções auxiliares
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

st.set_page_config(page_title="Previsão Lotofácil", layout="wide", page_icon="🎯")

# Título estilizado
st.markdown("<h1 style='text-align: center; color: darkblue;'>🎯 Previsão Lotofácil</h1>", unsafe_allow_html=True)
st.write("Carregue seu histórico e veja as dezenas mais prováveis de sair!")

# Upload do arquivo Excel
arquivo = st.file_uploader("Escolha o arquivo Excel com histórico", type=["xls", "xlsx"])

if arquivo is not None:
    # Lê o Excel
    df = pd.read_excel(arquivo)

    # Remove coluna não numérica se existir
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.fillna(0).astype(int)

    # Transformar em lista de listas
    historico_dezenas = df.values.tolist()
    historico_binario = converter_para_binario(historico_dezenas)

    st.success("✅ Arquivo carregado e convertido com sucesso!")

    # Layout com colunas
    col1, col2 = st.columns([1,1])

    with col1:
        st.header("Escolha dezenas para excluir")
        excluir_dezenas = st.multiselect(
            "Selecione dezenas (opcional)",
            options=list(range(1, 26))
        )

    with col2:
        if st.button("Gerar Previsão"):
            dezenas, media = gerar_previsao(historico_binario, excluir_dezenas)
            st.subheader("Dezenas sugeridas:")
            st.write(dezenas)

            # Gráfico de probabilidade
            fig = px.bar(
                x=list(range(1,26)),
                y=media,
                labels={"x":"Dezenas", "y":"Probabilidade"},
                title="Probabilidade de cada dezena"
            )
            fig.update_layout(xaxis=dict(dtick=1))
            st.plotly_chart(fig)

    # Exibir histórico original
    st.header("Histórico de concursos")
    st.dataframe(df)
else:
    st.info("📄 Por favor, faça upload do arquivo Excel com o histórico.")
