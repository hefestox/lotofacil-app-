import pandas as pd
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from itertools import combinations
import random
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


# ==========================
# FUNÇÕES PRINCIPAIS
# ==========================

def converter_para_binario(lista_de_resultados):
    binario = []
    for resultado in lista_de_resultados:
        vetor = [0] * 25
        for dezena in resultado:
            if 1 <= dezena <= 25:
                vetor[dezena - 1] = 1
        binario.append(vetor)
    return np.array(binario)


def calcular_atraso(historico):
    atraso = [0] * 25
    total = len(historico)
    for dezena in range(25):
        atraso_dezena = 0
        for i in range(total - 1, -1, -1):
            if historico[i][dezena] == 1:
                break
            atraso_dezena += 1
        atraso[dezena] = atraso_dezena
    return atraso


def detectar_ciclo_fechado(historico):
    ultimo = historico[-1]
    ciclo_fechado = []
    for i, val in enumerate(ultimo):
        if val == 1:
            ciclo_fechado.append(i)
    return ciclo_fechado


def processar_excel(caminho):
    try:
        # Lê o Excel sem considerar cabeçalho
        df = pd.read_excel(caminho, header=None)

        historico_dezenas = []
        for concurso in df.values.tolist():
            dezenas = []
            for dezena in concurso:
                try:
                    dezenas.append(int(dezena))
                except:
                    continue  # ignora valores não numéricos
            if dezenas:
                historico_dezenas.append(dezenas)
        return historico_dezenas
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível ler o arquivo:\n{e}")
        return None


def gerar_jogos():
    caminho = filedialog.askopenfilename(title="Selecione o arquivo Excel",
                                         filetypes=(("Arquivos Excel", "*.xls*"), ("Todos os arquivos", "*.*")))
    if not caminho:
        return

    historico_dezenas = processar_excel(caminho)
    if historico_dezenas is None:
        return

    historico_binario = converter_para_binario(historico_dezenas)
    atrasos = calcular_atraso(historico_binario)
    ciclo_fechado_indices = detectar_ciclo_fechado(historico_binario)

    # Treinar rede neural
    X = historico_binario[:-1]
    y = historico_binario[1:]

    model = Sequential()
    model.add(Dense(64, activation='relu', input_dim=25))
    model.add(Dense(25, activation='sigmoid'))
    model.compile(optimizer='adam', loss='binary_crossentropy')
    model.fit(X, y, epochs=200, verbose=0)

    ultimo_concurso = historico_binario[-1].reshape(1, -1)
    predicao = model.predict(ultimo_concurso)[0]

    # Calcular score e excluir 5 dezenas
    max_atraso = max(atrasos) if max(atrasos) > 0 else 1
    scores = []
    for i in range(25):
        score = predicao[i] - (atrasos[i] / max_atraso) * 0.5
        if i in ciclo_fechado_indices:
            score -= 0.3
        scores.append((i + 1, score))

    scores_ordenados = sorted(scores, key=lambda x: x[1])
    dezenas_excluir = [dezena for dezena, score in scores_ordenados[:5]]
    dezenas_restantes = [d for d in range(1, 26) if d not in dezenas_excluir]

    # Gerar combinações
    combinacoes = list(combinations(dezenas_restantes, 15))
    random.shuffle(combinacoes)
    jogos_sugeridos = combinacoes[:10]

    # Mostrar resultados
    output_text.delete(1.0, tk.END)
    output_text.insert(tk.END, f"Dezenas a excluir (5): {sorted(dezenas_excluir)}\n\n")
    output_text.insert(tk.END, "Jogos sugeridos:\n")
    for i, jogo in enumerate(jogos_sugeridos, 1):
        output_text.insert(tk.END, f"Jogo {i}: {sorted(jogo)}\n")


# ==========================
# INTERFACE GRÁFICA
# ==========================
root = tk.Tk()
root.title("Gerador de Jogos Lotofácil")
root.geometry("500x600")

btn_excel = tk.Button(root, text="Selecionar Excel e Gerar Jogos", command=gerar_jogos)
btn_excel.pack(pady=10)

output_text = scrolledtext.ScrolledText(root, width=60, height=30)
output_text.pack(padx=10, pady=10)

root.mainloop()
