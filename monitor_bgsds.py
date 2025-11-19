import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from io import BytesIO
from PyPDF2 import PdfReader

URL = "https://www.sds.pe.gov.br/boletim-geral"
LAST_ID_FILE = "last_bgsds_id.txt"

# 🔎 Ajuste suas palavras-chave aqui
# Ele vai verificar cada uma e dizer se encontrou ou não
KEYWORDS = [
    "PORTARIA NORMATIVA",   # exemplo
    "DG/PCPE",              # exemplo
    # coloque aqui o que você quiser procurar
]

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

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()


def baixa_pdf_texto(pdf_url: str) -> str:
    """
    Baixa o PDF e retorna o texto extraído.
    Usa PyPDF2 para ler todas as páginas.
    """
    resp = requests.get(pdf_url, timeout=120)
    resp.raise_for_status()

    with BytesIO(resp.content) as f:
        reader = PdfReader(f)
        textos = []
        for page in reader.pages:
            try:
                textos.append(page.extract_text() or "")
            except Exception:
                # se der erro em uma página, continua nas outras
                continue

    texto_completo = "\n".join(textos)
    return texto_completo


def busca_palavras_no_pdf(pdf_url: str, palavras: list[str]) -> dict:
    """
    Baixa o PDF, extrai o texto e verifica se cada palavra-chave aparece.
    Retorna dict: {palavra: True/False}
    """
    print(f"Baixando PDF para busca de palavras-chave: {pdf_url}")
    texto = baixa_pdf_texto(pdf_url)
    texto_lower = texto.lower()

    resultado = {}
    for p in palavras:
        p_norm = p.lower()
        encontrado = p_norm in texto_lower
        resultado[p] = encontrado
        print(f"Palavra-chave '{p}': {'ENCONTRADA' if encontrado else 'NÃO encontrada'}")

    return resultado


def monta_resumo_palavras(resultado: dict) -> str:
    """
    Monta um texto resumido para colocar na mensagem do Telegram,
    mostrando se cada palavra-chave foi encontrada.
    """
    linhas = []
    for palavra, ok in resultado.items():
        status = "✅ encontrada" if ok else "❌ não encontrada"
        linhas.append(f"• <b>{palavra}</b>: {status}")
    return "\n".join(linhas)


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
        # 1) Busca palavras-chave no PDF
        resumo_palavras = ""
        try:
            resultado = busca_palavras_no_pdf(pdf_url, KEYWORDS)
            resumo_palavras = monta_resumo_palavras(resultado)
        except Exception as e:
            resumo_palavras = f"⚠️ Erro ao analisar o PDF para palavras-chave: {e}"

        # 2) Monta mensagem do Telegram
        msg = (
            f"✅ <b>Novo Boletim Geral publicado!</b>\n\n"
            f"<b>{titulo_novo}</b>\n\n"
            f"📄 <a href=\"{pdf_url}\">Abrir PDF</a>\n"
            f"{pdf_url}\n\n"
            f"<b>Busca de palavras-chave:</b>\n"
            f"{resumo_palavras}"
        )

        envia_telegram(msg)
        salva_ultimo(data_nova)

        print("Mensagem enviada e data registrada.")
    else:
        print("Nenhum boletim novo.")


if __name__ == "__main__":
    main()
