import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from io import BytesIO
from PyPDF2 import PdfReader

# Configurações
URL = "https://www.sds.pe.gov.br/boletim-geral"
LAST_ID_FILE = "last_bgsds_id.txt"

# 🔎 Ajuste suas palavras-chave aqui
KEYWORDS = [
    "dominguez",
    "agostinho",
    # adicione outras palavras aqui
]

MESES = {
    "JAN": "01", "FEV": "02", "MAR": "03", "ABR": "04", "MAI": "05", "JUN": "06",
    "JUL": "07", "AGO": "08", "SET": "09", "OUT": "10", "NOV": "11", "DEZ": "12",
}

def parse_data(texto):
    """Extrai a data real do boletim no formato datetime."""
    m = re.search(r"DE\s*(\d{1,2})([A-Z]{3})(\d{4})", texto.upper()) # Converte para upper antes de buscar
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
    """Retorna lista de boletins ordenada por data."""
    try:
        resp = requests.get(URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erro ao acessar o site: {e}")
        return []

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
        print("ERRO: Tokens do Telegram não configurados.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        print("Mensagem enviada para o Telegram com sucesso.")
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

def baixa_pdf_texto(pdf_url: str) -> str:
    resp = requests.get(pdf_url, timeout=120)
    resp.raise_for_status()
    with BytesIO(resp.content) as f:
        reader = PdfReader(f)
        textos = []
        for page in reader.pages:
            try:
                textos.append(page.extract_text() or "")
            except Exception:
                continue
    return "\n".join(textos)

def busca_palavras_no_pdf(pdf_url: str, palavras: list[str]) -> dict:
    print(f"Baixando PDF para busca: {pdf_url}")
    texto = baixa_pdf_texto(pdf_url)
    texto_lower = texto.lower()
    resultado = {}
    for p in palavras:
        p_norm = p.lower()
        resultado[p] = p_norm in texto_lower
    return resultado

def monta_resumo_palavras(resultado: dict) -> str:
    linhas = []
    for palavra, ok in resultado.items():
        status = "✅ encontrada" if ok else "❌ não encontrada"
        linhas.append(f"• <b>{palavra}</b>: {status}")
    return "\n".join(linhas)

def main():
    boletins = lista_boletins()
    
    # Cabeçalho padrão da mensagem
    mensagem_final = "<b>Relatório do Boletim Geral da SDS/PE</b>\n"
    
    # Se a lista falhar, envia a mensagem de erro.
    if not boletins:
        mensagem_final += "⚠️ Não foi possível ler a lista de boletins no site."
        envia_telegram(mensagem_final) # Envia apenas em caso de erro na leitura do site
        return

    data_nova, titulo_novo, pdf_url = boletins[0]
    data_ultima = carrega_ultimo()

    print(f"Mais recente no site: {titulo_novo} ({data_nova})")
    print(f"Último salvo localmente: {data_ultima}")

    # Verifica se há atualização
    if data_ultima is None or data_nova > data_ultima:
        # --- Lógica de NOVA ATUALIZAÇÃO ---
        
        # 1) Busca palavras-chave no PDF
        resumo_palavras = ""
        try:
            resultado = busca_palavras_no_pdf(pdf_url, KEYWORDS)
            resumo_palavras = monta_resumo_palavras(resultado)
        except Exception as e:
            resumo_palavras = f"⚠️ Erro ao analisar o PDF: {e}"

        # 2) Monta o corpo da mensagem de sucesso
        corpo_msg = (
            f"✅ <b>Atualização encontrada!</b>\n\n"
            f"<b>{titulo_novo}</b>\n"
            f"📄 <a href=\"{pdf_url}\">Abrir PDF</a>\n\n"
            f"<b>Busca de palavras-chave:</b>\n"
            f"{resumo_palavras}"
        )
        
        # 3) Atualiza o arquivo local com a data nova
        salva_ultimo(data_nova)
        
        # 4) Envia a mensagem (SÓ AQUI, DENTRO DO IF)
        mensagem_final += corpo_msg
        envia_telegram(mensagem_final)
    else:
        # --- Lógica de SEM ATUALIZAÇÃO ---
        # Não faz nada e o script termina sem enviar mensagem para o Telegram.
        print("Boletim já processado. Nenhuma atualização para notificar.")
        pass # Apenas passa

if __name__ == "__main__":
    main()
