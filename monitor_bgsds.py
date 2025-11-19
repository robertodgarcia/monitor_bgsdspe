import os
import re
import requests
from bs4 import BeautifulSoup

URL = "https://www.sds.pe.gov.br/boletim-geral"
LAST_ID_FILE = "last_bgsds_id.txt"


def lista_boletins():
    """
    Retorna uma lista de boletins encontrados na página, no formato:
    [(numero, titulo, pdf_url), ...]
    """
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    boletins = []

    for a in soup.find_all("a"):
        texto = a.get_text(strip=True)
        if "BGSDS" not in texto:
            continue

        # procura algo como "215 BGSDS"
        m = re.search(r"(\d+)\s*BGSDS", texto)
        if not m:
            continue

        numero = int(m.group(1))
        href = a.get("href")
        if not href:
            continue

        pdf_url = requests.compat.urljoin(URL, href)
        boletins.append((numero, texto, pdf_url))

    # ordena do mais recente (maior número) para o mais antigo
    boletins.sort(key=lambda x: x[0], reverse=True)
    return boletins


def carrega_ultimo_id():
    """
    Lê o último ID salvo no arquivo last_bgsds_id.txt.
    Se não existir, retorna None.
    """
    if not os.path.exists(LAST_ID_FILE):
        return None

    try:
        with open(LAST_ID_FILE, "r", encoding="utf-8") as f:
            conteudo = f.read().strip()
        return int(conteudo) if conteudo else None
    except Exception:
        return None


def salva_ultimo_id(numero: int):
    """
    Salva o último ID no arquivo last_bgsds_id.txt.
    """
    with open(LAST_ID_FILE, "w", encoding="utf-8") as f:
        f.write(str(numero))


def envia_telegram(mensagem: str):
    """
    Envia mensagem para o Telegram usando Bot API.
    Necessita das variáveis de ambiente:
      - TELEGRAM_BOT_TOKEN
      - TELEGRAM_CHAT_ID
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    boletins = lista_boletins()
    if not boletins:
        print("Nenhum boletim encontrado na página.")
        return

    numero_novo, titulo_novo, pdf_url_novo = boletins[0]
    ultimo_id = carrega_ultimo_id()

    print(f"Boletim mais recente na página: {numero_novo} - {titulo_novo}")
    print(f"Último ID registrado: {ultimo_id}")

    # Se nunca registrou nada, você pode escolher:
    # - Enviar mensagem mesmo assim
    # - Ou só gravar o ID sem notificar
    # Aqui vou: ENVIAR uma vez na primeira execução.
    if ultimo_id is None or numero_novo > ultimo_id:
        msg = (
            f"✅ <b>Novo Boletim Geral publicado!</b>\n\n"
            f"<b>{titulo_novo}</b>\n"
            f"{pdf_url_novo}"
        )
        print("Novo boletim detectado, enviando mensagem ao Telegram...")
        envia_telegram(msg)
        print("Mensagem enviada com sucesso.")
        salva_ultimo_id(numero_novo)
    else:
        print("Nenhum boletim novo desde o último registro.")
        # ainda assim garantimos que o arquivo está atualizado
        salva_ultimo_id(numero_novo)


if __name__ == "__main__":
    main()
