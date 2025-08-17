from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import pandas as pd
import time


def main():
    # Ajuste o caminho do ChromeDriver conforme necessário
    driver_path = "C:/Users/LENOVO/Downloads/chromedriver.exe"  # altere para o caminho correto

    # Cria o objeto Service com o caminho do driver
    service = Service(driver_path)

    # Inicializa o WebDriver com o Service
    driver = webdriver.Chrome(service=service)

    url = "https://asloterias.com.br/todos-resultados-lotofacil"
    driver.get(url)

    # Aguarda alguns segundos para que a página seja carregada completamente
    time.sleep(10)

    # Obtém o código HTML da página renderizada
    html = driver.page_source
    driver.quit()

    # Cria um objeto BeautifulSoup para analisar o HTML
    soup = BeautifulSoup(html, "html.parser")

    # Tenta encontrar uma tabela HTML na página
    table = soup.find("table")

    if table:
        try:
            # Se encontrar uma tabela, extrai os dados com pandas
            df = pd.read_html(str(table))[0]
            df.to_excel("lotofacil_resultados.xlsx", index=False)
            print("Arquivo Excel criado com sucesso usando a tabela encontrada!")
        except Exception as e:
            print("Erro ao processar a tabela:", e)
    else:
        print("Nenhuma tabela HTML encontrada. Tentando extrair os resultados manualmente...")

        # Tenta extrair os dados manualmente (ajuste os seletores conforme a estrutura atual da página)
        results = []
        draw_containers = soup.find_all("div", class_="resultado-lotofacil")

        if draw_containers:
            for draw in draw_containers:
                contest = draw.find("span", class_="concurso").get_text(strip=True) if draw.find("span",
                                                                                                 class_="concurso") else ""
                date = draw.find("span", class_="data").get_text(strip=True) if draw.find("span", class_="data") else ""
                numbers_elements = draw.find_all("span", class_="dezena")
                numbers = [el.get_text(strip=True) for el in numbers_elements]

                results.append({
                    "Concurso": contest,
                    "Data": date,
                    "Dezenas": ", ".join(numbers)
                })

            if results:
                df = pd.DataFrame(results)
                df.to_excel("lotofacil_resultados.xlsx", index=False)
                print("Arquivo Excel criado com sucesso usando extração manual!")
            else:
                print("Não foi possível extrair os resultados manualmente.")
        else:
            print("Não foram encontrados contêineres de resultados na página.")


if __name__ == "__main__":
    main()
