import pandas as pd
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense

# ===============================
# 1) LER RESULTADOS DO EXCEL
# ===============================
caminho_arquivo = r"C:\Users\LENOVO\Desktop\Lotofácil 08.xls.xlsx"

df = pd.read_excel(caminho_arquivo, sheet_name=0, header=None, dtype=str)

resultados = []
for _, linha in df.iterrows():
    numeros = []
    for item in linha:
        if pd.notna(item):
            try:
                numeros.append(int(float(item)))
            except:
                pass
    if numeros:
        resultados.append(numeros)

# ===============================
# 2) FUNÇÃO PARA SEPARAR EM CICLOS (opcional)
# ===============================
def separar_em_ciclos(resultados, tamanho_ciclo):
    ciclos = []
    for i in range(0, len(resultados), tamanho_ciclo):
        ciclos.append(resultados[i:i+tamanho_ciclo])
    return ciclos

tamanho_ciclo = 3
ciclos = separar_em_ciclos(resultados, tamanho_ciclo)

# ===============================
# 3) CONVERTER RESULTADOS PARA MATRIZ BINÁRIA
# ===============================
def resultados_para_binario(resultados):
    binarios = []
    for linha in resultados:
        vetor = [1 if i+1 in linha else 0 for i in range(25)]
        binarios.append(vetor)
    return np.array(binarios)

X = resultados_para_binario(resultados)
y = X.copy()  # autoencoder: tenta reproduzir o padrão

# ===============================
# 4) CRIAR E TREINAR REDE NEURAL
# ===============================
modelo = Sequential()
modelo.add(Dense(50, input_dim=25, activation='relu'))
modelo.add(Dense(25, activation='sigmoid'))  # saída: 25 posições (0 ou 1)

modelo.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

modelo.fit(X, y, epochs=200, batch_size=5, verbose=1)

# ===============================
# 5) TESTAR PREVISÃO
# ===============================
exemplo = X[-1].reshape(1,25)  # último concurso como exemplo
previsao = modelo.predict(exemplo)
previsao = [i+1 for i, v in enumerate(previsao[0]) if v > 0.5]  # considera >0.5 como saída

print("Último concurso:", resultados[-1])
print("Previsão da rede:", previsao)
