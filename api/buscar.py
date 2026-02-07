"""
Vercel Serverless Function - Busca de precos via SerpAPI (Google Shopping)
e scraping direto da Amazon Brasil.
"""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def parse_preco(texto):
    """Converte texto de preco (ex: 'R$ 1.299,90') para float."""
    try:
        texto = texto.replace("R$", "").strip()
        texto = texto.replace("\xa0", "").replace(" ", "")
        texto = texto.replace(".", "").replace(",", ".")
        valor = float(texto)
        return valor if valor > 0 else None
    except (ValueError, AttributeError):
        return None


# ── Google Shopping via SerpAPI ──────────────────────────────────────────────

def buscar_google_shopping(produto, num_resultados=20):
    """Busca precos no Google Shopping usando SerpAPI."""
    if not SERPAPI_KEY:
        return [], "SERPAPI_KEY nao configurada. Adicione nas variaveis de ambiente da Vercel."

    params = {
        "engine": "google_shopping",
        "q": produto,
        "hl": "pt",
        "gl": "br",
        "api_key": SERPAPI_KEY,
    }

    resultados = []

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return resultados, f"Erro ao buscar Google Shopping: {e}"

    if "error" in data:
        return resultados, f"SerpAPI erro: {data['error']}"

    shopping_results = data.get("shopping_results", [])

    for item in shopping_results[:num_resultados]:
        try:
            nome = item.get("title", "Produto sem nome")

            # SerpAPI retorna extracted_price como float
            preco_valor = item.get("extracted_price")
            if preco_valor is None or preco_valor <= 0:
                # Tenta parsear do texto
                preco_texto = item.get("price", "")
                preco_valor = parse_preco(preco_texto)
                if preco_valor is None:
                    continue

            preco_texto = item.get("price", f"R$ {preco_valor:,.2f}")

            loja = item.get("source", "Loja nao identificada")
            link = item.get("link", item.get("product_link", ""))
            thumbnail = item.get("thumbnail", "")
            avaliacao = ""
            if item.get("rating"):
                avaliacao = f"{item['rating']} ({item.get('reviews', 0)} avaliacoes)"

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": loja,
                "link": link,
                "fonte": "Google Shopping",
                "imagem": thumbnail,
                "avaliacao": avaliacao,
            })
        except Exception:
            continue

    return resultados, None


# ── Amazon Brasil via scraping ───────────────────────────────────────────────

def buscar_amazon(produto, num_resultados=20):
    """Busca precos na Amazon Brasil via scraping."""
    url = f"https://www.amazon.com.br/s?k={quote_plus(produto)}"
    resultados = []

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # Primeiro acessa a home para pegar cookies
        session.get("https://www.amazon.com.br", timeout=8)
        response = session.get(url, timeout=12)
        response.raise_for_status()
    except requests.RequestException as e:
        return resultados, f"Erro ao buscar Amazon: {e}"

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("div[data-component-type='s-search-result']")

    if not items:
        # Fallback: tenta outros seletores
        items = soup.select("div[data-asin]")
        items = [i for i in items if i.get("data-asin", "").strip()]

    for item in items[:num_resultados]:
        try:
            nome_el = (
                item.select_one("h2 a span")
                or item.select_one("h2 span")
                or item.select_one("span.a-text-normal")
            )
            nome = nome_el.get_text(strip=True) if nome_el else None
            if not nome:
                continue

            # Preco: tenta multiplos seletores
            preco_inteiro_el = item.select_one("span.a-price-whole")
            preco_frac_el = item.select_one("span.a-price-fraction")

            preco_valor = None
            preco_texto = ""

            if preco_inteiro_el:
                preco_inteiro = preco_inteiro_el.get_text(strip=True).rstrip(",").rstrip(".")
                preco_inteiro = preco_inteiro.replace(".", "").replace(",", "")
                preco_frac = preco_frac_el.get_text(strip=True) if preco_frac_el else "00"
                try:
                    preco_valor = float(f"{preco_inteiro}.{preco_frac}")
                    preco_texto = f"R$ {preco_inteiro_el.get_text(strip=True)},{preco_frac}"
                except ValueError:
                    pass

            if preco_valor is None:
                # Fallback: tenta span.a-offscreen
                offscreen = item.select_one("span.a-price span.a-offscreen")
                if offscreen:
                    preco_texto = offscreen.get_text(strip=True)
                    preco_valor = parse_preco(preco_texto)

            if preco_valor is None or preco_valor <= 0:
                continue

            link_el = item.select_one("h2 a[href]") or item.select_one("a.a-link-normal[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else "https://www.amazon.com.br" + href

            rating_el = item.select_one("span.a-icon-alt")
            avaliacao = rating_el.get_text(strip=True) if rating_el else ""

            img_el = item.select_one("img.s-image")
            imagem = img_el.get("src", "") if img_el else ""

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": "Amazon",
                "link": link,
                "fonte": "Amazon",
                "imagem": imagem,
                "avaliacao": avaliacao,
            })
        except Exception:
            continue

    return resultados, None


# ── Handler Vercel ───────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        produto = params.get("q", [""])[0].strip()

        if not produto:
            self._respond(400, {"erro": "Parametro 'q' e obrigatorio."})
            return

        resultados_google, erro_google = buscar_google_shopping(produto)
        resultados_amazon, erro_amazon = buscar_amazon(produto)

        todos = resultados_google + resultados_amazon
        todos.sort(key=lambda x: x["preco"])

        avisos = []
        if erro_google:
            avisos.append(f"Google Shopping: {erro_google}")
        if erro_amazon:
            avisos.append(f"Amazon: {erro_amazon}")

        resposta = {
            "produto": produto,
            "total": len(todos),
            "google_shopping": len(resultados_google),
            "amazon": len(resultados_amazon),
            "resultados": todos,
            "avisos": avisos,
        }

        self._respond(200, resposta)

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
