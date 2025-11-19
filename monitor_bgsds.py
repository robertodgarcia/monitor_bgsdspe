import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://www.sds.pe.gov.br/boletim-geral"
LAST_ID_FILE = "last_bgsds_id.txt"

MESES = {
    "JAN": "01",
    "FEV": "02",
    "MAR": "03",
    "ABR": "04",
    "MAI": "05",
    "JUN": "06",
    "JUL": "07",
    "AGO": "08",
    "SET": "09",
    "OUT": "10",
    "NOV": "11",
    "DEZ": "12",
}


def parse_data(texto):
    """
    Extrai a data real do boletim no formato datetime.
    Exemplo: '249 BGSDS DE 31DEZ2019' → datetime(2019, 12, 31)
    """
    m = re.search(r"DE\s*(\d{1,2})([A-Z]{3})(\d{4})", texto)
    if not m:
        return None

    dia = int(m.group(1))
    mes_abrev = m.group(2)
    ano = int(m.group(3))

    mes = MESES.get(mes_abrev)
    if not mes:
        return None

    return datetime(ano, int(mes), dia)


def lista_boletins():
    """
    Retorna lista de boletins no formato:
    [(data_real, titulo, pdf_url), ...]
    """
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    boletins = []

    for a in soup.find_all("a"):
        texto = a.get_text(strip=True)
        if "BGSDS" not in texto:
            continue

        data = parse_data(texto)
        if not data:
            continue

        href = a.get("href")
        if not href:
            continue

        pdf_url = requests.compat.urljoin(URL, href)
        boletins.append((data, texto, pdf_url))

    # Ordenar pela data real (mais recente primeiro)
    boletins.sort(key=lambda x: x[0], reverse=True)
    return boletins


def carrega_ultimo():
    if not os.path.exists(LAST_ID_FILE):
        return None
    try:
        with open(LAST_ID_FILE, "r") as f:
            s = f.read().strip()
        return datetime.fromisoformat(s)
    except Exception:
        return None


def salva_ultimo(data):
    with open(LAST_ID_FILE, "w") as f:
        f.write(data.isoformat())


def envia_telegram(mensagem):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise ValueError("Tokens do Telegram não configurados.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    requests.post(url, json=payload, timeout=60)


def main():
    boletins = lista_boletins()
    if not boletins:
        print("Nenhum boletim encontrado.")
        return

    data_nova, titulo_novo, pdf_url = boletins[0]
    data_ultima = carrega_ultimo()

    print(f"Mais recente encontrado: {data_nova} → {titulo_novo}")
    print(f"Último registrado: {data_ultima}")

    # Se for o primeiro uso ou se há boletim mais novo
    if data_ultima is None or data_nova > data_ultima:

        msg = (
            f"✅ <b>Novo Boletim Geral publicado!</b>\n\n"
            f"<b>{titulo_novo}</b>\n\n"
            f"📄 <a href=\"{pdf_url}\">Abrir PDF</a>\n"
            f"{pdf_url}"
        )

        envia_telegram(msg)
        salva_ultimo(data_nova)

        print("Mensagem enviada e data registrada.")
    else:
        print("Nenhum boletim novo.")


if __name__ == "__main__":
    main()
