"""
Vercel Serverless Function - Busca de precos no Google Shopping e Amazon Brasil.
Usa ScraperAPI como proxy para contornar bloqueio de IPs cloud.
"""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")


def _fetch(url):
    """Faz requisicao via ScraperAPI (proxy) ou direto como fallback."""
    if SCRAPER_API_KEY:
        proxy_url = (
            f"http://api.scraperapi.com"
            f"?api_key={SCRAPER_API_KEY}"
            f"&url={quote_plus(url)}"
            f"&country_code=br"
        )
        resp = requests.get(proxy_url, timeout=30)
    else:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)

    resp.raise_for_status()
    return resp.text


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


# ── Google Shopping ──────────────────────────────────────────────────────────

def buscar_google_shopping(produto, num_resultados=20):
    """Busca precos no Google Shopping."""
    url = f"https://www.google.com.br/search?q={quote_plus(produto)}&tbm=shop&hl=pt-BR&gl=br"
    resultados = []

    try:
        html = _fetch(url)
    except Exception as e:
        return resultados, f"Erro ao acessar Google Shopping: {e}"

    soup = BeautifulSoup(html, "html.parser")

    # Tenta varios seletores (Google muda frequentemente)
    items = (
        soup.select("div.sh-dgr__content")
        or soup.select("div.sh-dlr__list-result")
        or soup.select("div.xcR77")
        or soup.select("div.i0X6df")
        or soup.select("div.KZmu8e")
    )

    if not items:
        # Fallback generico: procura blocos com preco R$
        for div in soup.find_all("div"):
            text = div.get_text()
            if "R$" in text and len(text) < 500:
                children = div.find_all("div", recursive=False)
                if len(children) >= 2:
                    items.append(div)
            if len(items) >= num_resultados:
                break

    for item in items[:num_resultados]:
        try:
            # Nome do produto
            nome_el = (
                item.select_one("h3")
                or item.select_one("h4")
                or item.select_one("a[aria-label]")
                or item.select_one("a")
            )
            nome = nome_el.get_text(strip=True) if nome_el else None
            if not nome or len(nome) < 3:
                continue

            # Preco
            preco_el = (
                item.select_one("span.a8Pemb")
                or item.select_one("span.HRLxBb")
                or item.select_one("span.kHxwFf")
                or item.select_one("b")
            )
            if not preco_el:
                for span in item.find_all("span"):
                    txt = span.get_text(strip=True)
                    if "R$" in txt and len(txt) < 30:
                        preco_el = span
                        break

            if not preco_el:
                continue

            preco_texto = preco_el.get_text(strip=True)
            preco_valor = parse_preco(preco_texto)
            if preco_valor is None:
                continue

            # Loja
            loja_el = (
                item.select_one("div.aULzUe")
                or item.select_one("div.IuHnof")
                or item.select_one("div.E5ocAb")
            )
            loja = loja_el.get_text(strip=True) if loja_el else ""

            # Link
            link_el = item.select_one("a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else "https://www.google.com" + href

            # Imagem
            img_el = item.select_one("img")
            imagem = ""
            if img_el:
                imagem = img_el.get("src", "") or img_el.get("data-src", "")

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": loja,
                "link": link,
                "fonte": "Google Shopping",
                "imagem": imagem,
                "avaliacao": "",
            })
        except Exception:
            continue

    return resultados, None


# ── Amazon Brasil ────────────────────────────────────────────────────────────

def buscar_amazon(produto, num_resultados=20):
    """Busca precos na Amazon Brasil."""
    url = f"https://www.amazon.com.br/s?k={quote_plus(produto)}"
    resultados = []

    try:
        html = _fetch(url)
    except Exception as e:
        return resultados, f"Erro ao acessar Amazon: {e}"

    soup = BeautifulSoup(html, "html.parser")

    items = soup.select("div[data-component-type='s-search-result']")
    if not items:
        items = [
            el for el in soup.select("div[data-asin]")
            if el.get("data-asin", "").strip()
        ]

    for item in items[:num_resultados]:
        try:
            # Nome
            nome_el = (
                item.select_one("h2 a span")
                or item.select_one("h2 span")
                or item.select_one("span.a-text-normal")
            )
            nome = nome_el.get_text(strip=True) if nome_el else None
            if not nome:
                continue

            # Preco - metodo 1: partes separadas
            preco_valor = None
            preco_texto = ""

            preco_inteiro_el = item.select_one("span.a-price-whole")
            preco_frac_el = item.select_one("span.a-price-fraction")

            if preco_inteiro_el:
                preco_int = preco_inteiro_el.get_text(strip=True).rstrip(",.")
                preco_int = preco_int.replace(".", "").replace(",", "")
                preco_frac = preco_frac_el.get_text(strip=True) if preco_frac_el else "00"
                try:
                    preco_valor = float(f"{preco_int}.{preco_frac}")
                    preco_texto = f"R$ {preco_inteiro_el.get_text(strip=True)},{preco_frac}"
                except ValueError:
                    pass

            # Preco - metodo 2: span.a-offscreen
            if preco_valor is None:
                offscreen = item.select_one("span.a-price span.a-offscreen")
                if offscreen:
                    preco_texto = offscreen.get_text(strip=True)
                    preco_valor = parse_preco(preco_texto)

            if preco_valor is None or preco_valor <= 0:
                continue

            # Link
            link_el = item.select_one("h2 a[href]") or item.select_one("a.a-link-normal[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else "https://www.amazon.com.br" + href

            # Avaliacao
            rating_el = item.select_one("span.a-icon-alt")
            avaliacao = rating_el.get_text(strip=True) if rating_el else ""

            # Imagem
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
        if not SCRAPER_API_KEY:
            avisos.append(
                "SCRAPER_API_KEY nao configurada. Cadastre-se gratis em scraperapi.com "
                "e adicione a chave nas variaveis de ambiente da Vercel."
            )
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
