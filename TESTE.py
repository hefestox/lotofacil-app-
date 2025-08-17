import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from itertools import combinations
import random
import pandas as pd

# ==========================
# 1) CARREGAR HISTÓRICO DO EXCEL (ignora colunas não numéricas)
# ==========================
CAMINHO_EXCEL = r"C:\Users\LENOVO\Desktop\Lotofácil 08.xls.xlsx"

def carregar_historico_do_excel(caminho):
    df = pd.read_excel(caminho)  # Lê o Excel com cabeçalho
    historico = []
    for _, linha in df.iterrows():
        # Pega apenas valores que sejam números inteiros válidos
        linha_inteiros = []
        for valor in linha:
            if pd.notna(valor):
                try:
                    linha_inteiros.append(int(valor))
                except ValueError:
                    pass  # Ignora células que não sejam números
        if linha_inteiros:  # Só adiciona se houver dezenas válidas
            historico.append(linha_inteiros)
    return historico

historico_dezenas = carregar_historico_do_excel(CAMINHO_EXCEL)

# ==========================
# 2) CONVERTER PARA BINÁRIO
# ==========================
def converter_para_binario(lista_de_resultados):
    binario = []
    for resultado in lista_de_resultados:
        vetor = [0]*25
        for dezena in resultado:
            if 1 <= dezena <= 25:
                vetor[dezena - 1] = 1
        binario.append(vetor)
    return np.array(binario)

historico_binario = converter_para_binario(historico_dezenas)

# ==========================
# 3) TREINAR REDE NEURAL
# ==========================
X = historico_binario[:-1]
y = historico_binario[1:]

model = Sequential()
model.add(Dense(64, activation='relu', input_dim=25))
model.add(Dense(25, activation='sigmoid'))

model.compile(optimizer='adam', loss='binary_crossentropy')
model.fit(X, y, epochs=200, verbose=0)

# ==========================
# 4) FAZER PREVISÃO
# ==========================
ultimo_concurso = historico_binario[-1].reshape(1, -1)
predicao = model.predict(ultimo_concurso)[0]

indices_ordenados = np.argsort(predicao)
dezenas_excluir = indices_ordenados[:4] + 1

print(f"4 dezenas recomendadas para excluir pela rede neural: {sorted(dezenas_excluir)}")

dezenas_restantes = [d for d in range(1, 26) if d not in dezenas_excluir]

combinacoes = list(combinations(dezenas_restantes, 15))
random.shuffle(combinacoes)
jogos_sugeridos = combinacoes[:3]

print("\n3 combinações sugeridas de 15 dezenas:")
for i, jogo in enumerate(jogos_sugeridos, 1):
    print(f"Jogo {i}: {sorted(jogo)}")
