"""
Vercel Serverless Function - Busca de precos usando DuckDuckGo HTML.
Requisicao HTTP direta, sem bibliotecas externas problematicas.
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote_plus

import requests
from bs4 import BeautifulSoup


def extrair_precos(texto):
    """Extrai todos os precos em R$ de um texto."""
    padroes = re.findall(
        r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})',
        texto
    )
    precos = []
    for p in padroes:
        try:
            valor = float(p.replace(".", "").replace(",", "."))
            if 1 < valor < 100000:
                precos.append(valor)
        except ValueError:
            continue
    return precos


def identificar_loja(url):
    """Identifica a loja pelo dominio da URL."""
    domain = urlparse(url).netloc.lower()
    lojas = {
        "amazon": "Amazon",
        "mercadolivre": "Mercado Livre",
        "magazineluiza": "Magazine Luiza",
        "magalu": "Magazine Luiza",
        "americanas": "Americanas",
        "casasbahia": "Casas Bahia",
        "kabum": "KaBuM!",
        "pichau": "Pichau",
        "terabyte": "Terabyteshop",
        "shopee": "Shopee",
        "aliexpress": "AliExpress",
        "carrefour": "Carrefour",
        "submarino": "Submarino",
        "zoom.com": "Zoom",
        "buscape": "Buscape",
        "extra.com": "Extra",
        "pontofrio": "Ponto Frio",
        "pelando": "Pelando",
        "promobit": "Promobit",
        "girafa": "Girafa",
        "fastshop": "Fast Shop",
        "colombo": "Colombo",
        "walm": "Walmart",
    }
    for chave, nome in lojas.items():
        if chave in domain:
            return nome
    domain = domain.replace("www.", "")
    parts = domain.split(".")
    return parts[0].capitalize() if parts else ""


def buscar_duckduckgo(query, max_results=30):
    """Busca no DuckDuckGo HTML e retorna lista de resultados."""
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    resp = requests.post(
        url,
        data={"q": query, "kl": "br-pt"},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for item in soup.select(".result")[:max_results]:
        title_el = item.select_one(".result__title a") or item.select_one(".result__a")
        snippet_el = item.select_one(".result__snippet")
        url_el = item.select_one(".result__url")

        title = title_el.get_text(strip=True) if title_el else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        href = ""

        if title_el and title_el.get("href"):
            href = title_el["href"]
            # DuckDuckGo wraps URLs in redirects
            if "uddg=" in href:
                from urllib.parse import unquote
                match = re.search(r'uddg=([^&]+)', href)
                if match:
                    href = unquote(match.group(1))

        if not href and url_el:
            href = url_el.get_text(strip=True)
            if not href.startswith("http"):
                href = "https://" + href

        results.append({
            "title": title,
            "snippet": snippet,
            "url": href,
        })

    return results


def formatar_preco(valor):
    """Formata float para texto R$ brasileiro."""
    inteiro = int(valor)
    centavos = int(round((valor - inteiro) * 100))
    if inteiro >= 1000:
        inteiro_fmt = f"{inteiro:,}".replace(",", ".")
    else:
        inteiro_fmt = str(inteiro)
    return f"R$ {inteiro_fmt},{centavos:02d}"


def buscar_produtos(produto):
    """Busca produtos com precos usando DuckDuckGo HTML."""
    resultados = []
    vistos = set()
    erros = []

    queries = [
        f"{produto} preço",
        f"{produto} comprar online preço",
    ]

    for query in queries:
        try:
            items = buscar_duckduckgo(query)
        except Exception as e:
            erros.append(f"Busca '{query}': {e}")
            continue

        for item in items:
            try:
                titulo = item["title"]
                snippet = item["snippet"]
                url = item["url"]

                if not titulo or not url:
                    continue

                # Evita duplicatas
                dominio = urlparse(url).netloc
                chave_dup = dominio + urlparse(url).path
                if chave_dup in vistos:
                    continue
                vistos.add(chave_dup)

                # Extrai precos do titulo + snippet
                texto = f"{titulo} {snippet}"
                precos = extrair_precos(texto)

                if not precos:
                    continue

                preco_valor = min(precos)
                preco_texto = formatar_preco(preco_valor)
                loja = identificar_loja(url)

                # Limpa titulo
                nome = re.sub(r'\s*[-|–]\s*R\$.*', '', titulo).strip()
                nome = re.sub(r'\s*R\$\s*\d.*', '', nome).strip()
                nome = re.sub(r'\s*[-|–]\s*$', '', nome).strip()
                if len(nome) < 5:
                    nome = titulo

                resultados.append({
                    "nome": nome,
                    "preco": preco_valor,
                    "preco_texto": preco_texto,
                    "loja": loja,
                    "link": url,
                    "fonte": loja or "Web",
                    "imagem": "",
                    "avaliacao": "",
                })
            except Exception:
                continue

    return resultados, erros


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        produto = params.get("q", [""])[0].strip()

        if not produto:
            self._respond(400, {"erro": "Parametro 'q' e obrigatorio."})
            return

        try:
            resultados, erros = buscar_produtos(produto)
        except Exception as e:
            self._respond(200, {
                "produto": produto,
                "total": 0,
                "resultados": [],
                "avisos": [f"Erro geral: {e}"],
            })
            return

        # Ordena por preco crescente
        resultados.sort(key=lambda x: x["preco"])

        # Remove duplicatas (mesmo preco + mesma loja)
        filtrados = []
        visto = set()
        for r in resultados:
            chave = (r["preco"], r["loja"])
            if chave not in visto:
                visto.add(chave)
                filtrados.append(r)

        avisos = erros if erros else []

        self._respond(200, {
            "produto": produto,
            "total": len(filtrados),
            "resultados": filtrados,
            "avisos": avisos,
        })

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
