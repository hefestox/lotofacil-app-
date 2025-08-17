from typing import List
import pandas as pd
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam

# ===== CONFIGURAÇÕES =====
CAMINHO_EXCEL = r"C:\Users\LENOVO\Desktop\Lotofácil 08.xls.xlsx"
NUM_DEZENAS = 25
NUM_ENSEMBLE = 10
EPOCHS = 50
BATCH_SIZE = 16

# ===== FUNÇÃO PARA CARREGAR HISTÓRICO =====
def carregar_historico(caminho: str) -> List[List[int]]:
    df = pd.read_excel(caminho, header=None)
    resultados = []
    for row in df.values:
        dezenas = []
        for x in row:
            try:
                num = int(x)
                if 1 <= num <= NUM_DEZENAS:  # só números válidos
                    dezenas.append(num)
            except:
                continue
        if dezenas:
            resultados.append(dezenas)
    return resultados

# ===== FUNÇÃO PARA PREPARAR DADOS =====
def preparar_dados(resultados: List[List[int]]):
    X, y = [], []
    for concurso in resultados[:-1]:
        vetor = np.zeros(NUM_DEZENAS)
        for dez in concurso:
            if 1 <= dez <= NUM_DEZENAS:
                vetor[dez-1] = 1
        X.append(vetor)
    for dez in resultados[1:]:
        vetor = np.zeros(NUM_DEZENAS)
        for d in dez:
            if 1 <= d <= NUM_DEZENAS:
                vetor[d-1] = 1
        y.append(vetor)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)

# ===== FUNÇÃO PARA CRIAR MODELO =====
def criar_modelo(input_dim: int):
    model = Sequential()
    model.add(Dense(128, input_dim=input_dim, activation='relu'))
    model.add(Dense(256, activation='relu'))
    model.add(Dense(128, activation='relu'))
    model.add(Dense(input_dim, activation='sigmoid'))
    model.compile(loss='binary_crossentropy', optimizer=Adam(0.001))
    return model

# ===== FUNÇÃO PARA TREINAR ENSEMBLE =====
def treinar_ensemble(X, y, num_ensemble: int):
    modelos = []
    for i in range(num_ensemble):
        print(f"Treinando modelo {i+1}/{num_ensemble}")
        model = criar_modelo(X.shape[1])
        model.fit(X, y, epochs=EPOCHS, batch_size=BATCH_SIZE, verbose=0)
        modelos.append(model)
    return modelos

# ===== FUNÇÃO PARA PREDIÇÃO COM ENSEMBLE =====
def predizer_ensemble(modelos, X_ultimo):
    previsoes = []
    for model in modelos:
        p = model.predict(np.array([X_ultimo]), verbose=0)[0]
        previsoes.append(p)
    media = np.mean(previsoes, axis=0)
    # selecionar as 15 dezenas mais prováveis
    dezenas_sugeridas = np.argsort(media)[-15:] + 1
    return sorted(list(dezenas_sugeridas))

# ===== FUNÇÃO PRINCIPAL =====
def main():
    resultados = carregar_historico(CAMINHO_EXCEL)
    print(f"Concursos carregados: {len(resultados)}")

    X, y = preparar_dados(resultados)
    modelos = treinar_ensemble(X, y, NUM_ENSEMBLE)

    X_ultimo = X[-1]  # último concurso
    dezenas = predizer_ensemble(modelos, X_ultimo)

    print("\n===== SUGESTÃO AVANÇADA COM ENSEMBLE =====")
    print(dezenas)

if __name__ == "__main__":
    main()

