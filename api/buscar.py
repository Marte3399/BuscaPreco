"""
Vercel Serverless Function - Busca de precos no Google Shopping e Amazon.
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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


def buscar_google_shopping(produto, num_resultados=15):
    """Busca precos no Google Shopping."""
    url = f"https://www.google.com/search?q={quote_plus(produto)}&tbm=shop&hl=pt-BR"
    resultados = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return resultados

    soup = BeautifulSoup(response.text, "html.parser")

    items = soup.select("div.sh-dgr__content")
    if not items:
        items = soup.select("div.sh-dlr__list-result")
    if not items:
        items = soup.select("div.xcR77")

    for item in items[:num_resultados]:
        try:
            nome_el = item.select_one("h3") or item.select_one("h4") or item.select_one("a")
            nome = nome_el.get_text(strip=True) if nome_el else "Produto sem nome"

            preco_el = item.select_one("span.a8Pemb") or item.select_one("span.HRLxBb")
            if not preco_el:
                for span in item.find_all("span"):
                    text = span.get_text(strip=True)
                    if "R$" in text:
                        preco_el = span
                        break

            if not preco_el:
                continue

            preco_texto = preco_el.get_text(strip=True)
            preco_valor = parse_preco(preco_texto)
            if preco_valor is None:
                continue

            loja_el = item.select_one("div.aULzUe") or item.select_one("div.IuHnof")
            loja = loja_el.get_text(strip=True) if loja_el else "Loja nao identificada"

            link_el = item.select_one("a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else "https://www.google.com" + href

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": loja,
                "link": link,
                "fonte": "Google Shopping",
            })
        except Exception:
            continue

    return resultados


def buscar_amazon(produto, num_resultados=15):
    """Busca precos na Amazon Brasil."""
    url = f"https://www.amazon.com.br/s?k={quote_plus(produto)}"
    resultados = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return resultados

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("div[data-component-type='s-search-result']")

    for item in items[:num_resultados]:
        try:
            nome_el = item.select_one("h2 a span") or item.select_one("h2 span")
            nome = nome_el.get_text(strip=True) if nome_el else "Produto sem nome"

            preco_inteiro_el = item.select_one("span.a-price-whole")
            preco_frac_el = item.select_one("span.a-price-fraction")
            if not preco_inteiro_el:
                continue

            preco_inteiro = preco_inteiro_el.get_text(strip=True).replace(".", "").replace(",", "")
            preco_frac = preco_frac_el.get_text(strip=True) if preco_frac_el else "00"

            try:
                preco_valor = float(f"{preco_inteiro}.{preco_frac}")
            except ValueError:
                continue

            preco_texto = f"R$ {preco_inteiro_el.get_text(strip=True)},{preco_frac}"

            link_el = item.select_one("h2 a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                link = href if href.startswith("http") else "https://www.amazon.com.br" + href

            rating_el = item.select_one("span.a-icon-alt")
            avaliacao = rating_el.get_text(strip=True) if rating_el else ""

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": "Amazon",
                "link": link,
                "fonte": "Amazon",
                "avaliacao": avaliacao,
            })
        except Exception:
            continue

    return resultados


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        produto = params.get("q", [""])[0].strip()

        if not produto:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"erro": "Parametro 'q' e obrigatorio"}).encode())
            return

        resultados_google = buscar_google_shopping(produto)
        resultados_amazon = buscar_amazon(produto)

        todos = resultados_google + resultados_amazon
        todos.sort(key=lambda x: x["preco"])

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        resposta = {
            "produto": produto,
            "total": len(todos),
            "google_shopping": len(resultados_google),
            "amazon": len(resultados_amazon),
            "resultados": todos,
        }
        self.wfile.write(json.dumps(resposta, ensure_ascii=False).encode())
