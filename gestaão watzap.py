import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# Premiação atual
premiacao = {
    15: 2000000.00,
    14: 1500.00,
    13: 35.00,
    12: 14.00,
    11: 7.00,
}

class LotofacilApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestão de Apostas Lotofácil")
        self.geometry("800x600")

        # Entrada de resultado
        frame_inputs = ttk.LabelFrame(self, text="Entradas")
        frame_inputs.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_inputs, text="Resultado oficial (15 dezenas separadas por vírgula):").pack(anchor=tk.W)
        self.entry_result = ttk.Entry(frame_inputs)
        self.entry_result.insert(0, "1,4,5,7,8,10,12,13,14,18,20,21,22,23,24")  # exemplo
        self.entry_result.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame_inputs, text="Jogos (cada linha = 1 jogo com 15 dezenas):").pack(anchor=tk.W)
        self.text_games = scrolledtext.ScrolledText(frame_inputs, height=10)
        self.text_games.pack(fill=tk.BOTH, padx=5, pady=5)

        ttk.Label(frame_inputs, text="Valor por aposta (ex: 4.50):").pack(anchor=tk.W)
        self.entry_value = ttk.Entry(frame_inputs)
        self.entry_value.insert(0, "4.50")
        self.entry_value.pack(fill=tk.X, padx=5, pady=5)

        # Botão calcular
        btn = ttk.Button(self, text="Calcular", command=self.calcular)
        btn.pack(pady=10)

        # Saída
        frame_output = ttk.LabelFrame(self, text="Resultado")
        frame_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.text_output = scrolledtext.ScrolledText(frame_output)
        self.text_output.pack(fill=tk.BOTH, expand=True)

    def calcular(self):
        try:
            resultado = [int(n) for n in self.entry_result.get().split(',')]
            valor_aposta = float(self.entry_value.get())
            linhas = self.text_games.get("1.0", tk.END).strip().splitlines()
            jogos = [[int(n) for n in linha.split(',')] for linha in linhas]
        except Exception as e:
            messagebox.showerror("Erro", f"Erro na entrada de dados: {e}")
            return

        total_lucro = 0
        self.text_output.delete("1.0", tk.END)

        for i, jogo in enumerate(jogos, 1):
            acertos = len(set(jogo) & set(resultado))
            premio = premiacao.get(acertos, 0)
            lucro = premio - valor_aposta
            total_lucro += lucro
            self.text_output.insert(
                tk.END,
                f"Jogo {i}: {acertos} pontos - Prêmio: R$ {premio:.2f} - Lucro/Prejuízo: R$ {lucro:.2f}\n"
            )

        self.text_output.insert(tk.END, f"\nLucro/Prejuízo total: R$ {total_lucro:.2f}\n")

if __name__ == "__main__":
    app = LotofacilApp()
    app.mainloop()
