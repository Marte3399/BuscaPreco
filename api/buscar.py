"""
Vercel Serverless Function - Busca de precos no Google Shopping e Amazon Brasil.
Usa SerpAPI que retorna JSON estruturado (sem depender de parsing HTML).
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


def _serpapi_request(params):
    """Faz requisicao para SerpAPI e retorna o JSON."""
    params["api_key"] = SERPAPI_KEY
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_preco(texto):
    """Converte texto de preco (ex: 'R$ 1.299,90') para float."""
    try:
        texto = texto.replace("R$", "").replace("$", "").strip()
        texto = texto.replace("\xa0", "").replace(" ", "")
        texto = texto.replace(".", "").replace(",", ".")
        valor = float(texto)
        return valor if valor > 0 else None
    except (ValueError, AttributeError):
        return None


# ── Google Shopping via SerpAPI ──────────────────────────────────────────────

def buscar_google_shopping(produto, num_resultados=20):
    """Busca precos no Google Shopping via SerpAPI (engine: google_shopping)."""
    resultados = []

    if not SERPAPI_KEY:
        return resultados, "SERPAPI_KEY nao configurada."

    try:
        data = _serpapi_request({
            "engine": "google_shopping",
            "q": produto,
            "hl": "pt",
            "gl": "br",
            "num": str(num_resultados),
        })
    except Exception as e:
        return resultados, f"Erro Google Shopping: {e}"

    if "error" in data:
        return resultados, f"SerpAPI: {data['error']}"

    for item in data.get("shopping_results", [])[:num_resultados]:
        try:
            nome = item.get("title", "")
            if not nome:
                continue

            preco_valor = item.get("extracted_price")
            if preco_valor is None or preco_valor <= 0:
                preco_valor = parse_preco(item.get("price", ""))
            if preco_valor is None:
                continue

            preco_texto = item.get("price", f"R$ {preco_valor:,.2f}")

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": item.get("source", ""),
                "link": item.get("link", item.get("product_link", "")),
                "fonte": "Google Shopping",
                "imagem": item.get("thumbnail", ""),
                "avaliacao": f"{item['rating']} ({item.get('reviews', 0)})" if item.get("rating") else "",
            })
        except Exception:
            continue

    return resultados, None


# ── Amazon via SerpAPI ───────────────────────────────────────────────────────

def buscar_amazon(produto, num_resultados=20):
    """Busca precos na Amazon Brasil via SerpAPI (engine: amazon)."""
    resultados = []

    if not SERPAPI_KEY:
        return resultados, "SERPAPI_KEY nao configurada."

    try:
        data = _serpapi_request({
            "engine": "amazon",
            "amazon_domain": "amazon.com.br",
            "q": produto,
        })
    except Exception as e:
        return resultados, f"Erro Amazon: {e}"

    if "error" in data:
        return resultados, f"SerpAPI: {data['error']}"

    for item in data.get("organic_results", [])[:num_resultados]:
        try:
            nome = item.get("title", "")
            if not nome:
                continue

            # SerpAPI retorna price info em diferentes campos
            price_info = item.get("price", {})

            if isinstance(price_info, dict):
                preco_valor = price_info.get("value") or price_info.get("raw")
                preco_texto = price_info.get("raw", "")
                if isinstance(preco_valor, str):
                    preco_valor = parse_preco(preco_valor)
                if not preco_texto and preco_valor:
                    preco_texto = f"R$ {preco_valor:,.2f}"
            elif isinstance(price_info, str):
                preco_texto = price_info
                preco_valor = parse_preco(price_info)
            else:
                # Tenta extracted_price ou price_raw
                preco_valor = item.get("extracted_price")
                preco_texto = item.get("price_raw", "")
                if not preco_valor:
                    continue

            if preco_valor is None or preco_valor <= 0:
                continue

            if not preco_texto:
                preco_texto = f"R$ {preco_valor:,.2f}"

            rating = item.get("rating", "")
            reviews = item.get("reviews", "")
            avaliacao = f"{rating} ({reviews})" if rating else ""

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": "Amazon",
                "link": item.get("link", ""),
                "fonte": "Amazon",
                "imagem": item.get("thumbnail", ""),
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

        if not SERPAPI_KEY:
            self._respond(200, {
                "produto": produto,
                "total": 0,
                "google_shopping": 0,
                "amazon": 0,
                "resultados": [],
                "avisos": [
                    "SERPAPI_KEY nao configurada. "
                    "Cadastre-se gratis em serpapi.com e adicione a chave "
                    "nas Environment Variables da Vercel (Settings > Environment Variables)."
                ],
            })
            return

        # Busca em paralelo para nao estourar timeout
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_google = executor.submit(buscar_google_shopping, produto)
            fut_amazon = executor.submit(buscar_amazon, produto)
            resultados_google, erro_google = fut_google.result()
            resultados_amazon, erro_amazon = fut_amazon.result()

        todos = resultados_google + resultados_amazon
        todos.sort(key=lambda x: x["preco"])

        avisos = []
        if erro_google:
            avisos.append(f"Google Shopping: {erro_google}")
        if erro_amazon:
            avisos.append(f"Amazon: {erro_amazon}")

        self._respond(200, {
            "produto": produto,
            "total": len(todos),
            "google_shopping": len(resultados_google),
            "amazon": len(resultados_amazon),
            "resultados": todos,
            "avisos": avisos,
        })

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
