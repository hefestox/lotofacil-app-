from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import pandas as pd

# ==========================
# CONFIGURAÇÃO DO ARQUIVO
# ==========================
CAMINHO_EXCEL = r"C:\Users\LENOVO\Desktop\Lotofácil 08.xls.xlsx"
UNIVERSO = set(range(1, 26))  # Dezenas 1 a 25

# ==========================
# CLASSE CICLO
# ==========================
@dataclass
class Ciclo:
    inicio_idx: int
    fim_idx: int
    tamanho: int
    faltantes: List[int]

# ==========================
# LEITURA DO EXCEL
# ==========================
def ler_resultados_do_excel(caminho: str) -> List[List[int]]:
    df = pd.read_excel(caminho, header=None)
    resultados = []
    for row in df.values.tolist():
        dezenas = []
        for cell in row:
            try:
                d = int(cell)
                if 1 <= d <= 25:
                    dezenas.append(d)
            except:
                pass  # ignora células não numéricas
        if dezenas:
            resultados.append(dezenas)
    return resultados

# ==========================
# CÁLCULO DE CICLOS
# ==========================
def computar_ciclos(resultados: List[List[int]]) -> Tuple[List[Ciclo], Optional[int], set]:
    ciclos: List[Ciclo] = []
    if not resultados:
        return ciclos, None, set(UNIVERSO)

    faltando = set(UNIVERSO)
    ciclo_inicio = 0

    for i, draw in enumerate(resultados):
        faltando -= set(draw)
        if not faltando:
            vistos = set()
            for j in range(ciclo_inicio, i):
                vistos |= set(resultados[j])
            faltantes_prev = sorted(list(UNIVERSO - vistos))
            ciclos.append(Ciclo(
                inicio_idx=ciclo_inicio,
                fim_idx=i,
                tamanho=i - ciclo_inicio + 1,
                faltantes=faltantes_prev,
            ))
            ciclo_inicio = i + 1
            faltando = set(UNIVERSO)

    if ciclo_inicio < len(resultados):
        vistos = set()
        for j in range(ciclo_inicio, len(resultados)):
            vistos |= set(resultados[j])
        faltantes_atual = UNIVERSO - vistos
        return ciclos, ciclo_inicio, faltantes_atual
    else:
        return ciclos, None, set(UNIVERSO)

# ==========================
# ESTATÍSTICAS
# ==========================
def atraso_por_dezena(resultados: List[List[int]]) -> Dict[int, int]:
    atraso = {d: 0 for d in UNIVERSO}
    if not resultados:
        return atraso
    last_idx = {d: -1 for d in UNIVERSO}
    for i, draw in enumerate(resultados):
        for d in draw:
            last_idx[d] = i
    n = len(resultados)
    for d in UNIVERSO:
        atraso[d] = n - 1 - last_idx[d] if last_idx[d] != -1 else n
    return atraso

def frequencias_janela(resultados: List[List[int]], janela: Optional[int] = None) -> Dict[int, int]:
    freq = {d: 0 for d in UNIVERSO}
    if not resultados:
        return freq
    recorte = resultados[-janela:] if janela else resultados
    for draw in recorte:
        for d in draw:
            freq[d] += 1
    return freq

# ==========================
# TABELA DE DEZENAS
# ==========================
def tabela_dezenas(resultados: List[List[int]], ciclo_inicio_atual: Optional[int]) -> pd.DataFrame:
    atraso = atraso_por_dezena(resultados)
    freq_total = frequencias_janela(resultados)
    freq_10 = frequencias_janela(resultados, 10)
    freq_20 = frequencias_janela(resultados, 20)
    freq_50 = frequencias_janela(resultados, 50)

    cols = [
        "dezena", "atraso", "freq_total", "freq_50", "freq_20", "freq_10",
        "saiu_no_ultimo", "participa_ciclo_atual"
    ]
    rows = []
    ultimo = set(resultados[-1]) if resultados else set()

    participou = {d: False for d in UNIVERSO}
    if ciclo_inicio_atual is not None:
        vistos = set()
        for j in range(ciclo_inicio_atual, len(resultados)):
            vistos |= set(resultados[j])
        for d in UNIVERSO:
            participou[d] = d in vistos

    for d in sorted(list(UNIVERSO)):
        rows.append([
            d,
            atraso[d],
            freq_total[d],
            freq_50[d],
            freq_20[d],
            freq_10[d],
            1 if d in ultimo else 0,
            1 if participou[d] else 0,
        ])

    df = pd.DataFrame(rows, columns=cols)
    df.sort_values(["participa_ciclo_atual", "atraso", "freq_total"], ascending=[True, False, True], inplace=True)
    return df

# ==========================
# SUGESTÃO DE DEZENAS
# ==========================
def sugerir_dezenas(resultados: List[List[int]], faltantes_atual: set,
                     peso_atraso: float = 1.0, peso_freq: float = 0.5, qtd: int = 15) -> List[int]:
    atraso = atraso_por_dezena(resultados)
    freq = frequencias_janela(resultados)
    base = sorted(list(faltantes_atual), key=lambda d: atraso[d], reverse=True)
    restantes = [d for d in range(1, 26) if d not in base]
    restantes.sort(key=lambda d: (atraso[d] * peso_atraso - freq[d] * peso_freq), reverse=True)
    sugestao = base + restantes
    return sorted(sugestao[:qtd])

# ==========================
# FUNÇÃO PRINCIPAL
# ==========================
def main():
    resultados = ler_resultados_do_excel(CAMINHO_EXCEL)
    ciclos, ciclo_inicio_atual, faltantes_atual = computar_ciclos(resultados)

    print("\n===== RESUMO DE CICLOS COMPLETOS =====")
    if ciclos:
        df_ciclos = pd.DataFrame([{
            "ciclo#": i + 1,
            "inicio_idx": c.inicio_idx,
            "fim_idx": c.fim_idx,
            "tamanho": c.tamanho,
            "faltantes_antes_do_fechamento": c.faltantes,
        } for i, c in enumerate(ciclos)])
        print(df_ciclos.to_string(index=False))
    else:
        print("Nenhum ciclo completo ainda.")

    print("\n===== CICLO ATUAL =====")
    if ciclo_inicio_atual is not None:
        print(f"Início do ciclo atual (índice): {ciclo_inicio_atual}")
        print(f"Concursos no ciclo atual: {len(resultados) - ciclo_inicio_atual}")
        print(f"Dezenas faltantes para fechar: {sorted(list(faltantes_atual)) if faltantes_atual else []}")
    else:
        print("Não há ciclo em aberto.")

    print("\n===== TABELA POR DEZENA =====")
    df_dezenas = tabela_dezenas(resultados, ciclo_inicio_atual)
    print(df_dezenas.to_string(index=False))

    print("\n===== SUGESTÃO DE DEZENAS =====")
    sugestao = sugerir_dezenas(resultados, faltantes_atual if ciclo_inicio_atual is not None else set())
    print(sugestao)

if __name__ == "__main__":
    main()
