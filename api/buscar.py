"""
Vercel Serverless Function - Busca de precos usando DuckDuckGo HTML.
Sem API key, sem bloqueio de IP, 100% gratis.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote_plus, unquote

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


def extrair_precos(texto):
    """Extrai todos os precos em R$ de um texto."""
    precos = []

    # Padrao 1: R$ 1.299,90 / R$99,90
    for m in re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})', texto):
        try:
            v = float(m.replace(".", "").replace(",", "."))
            if 1 < v < 200000:
                precos.append(v)
        except ValueError:
            pass

    # Padrao 2: "por 1.299,90" / "por 99,90" / "a partir de 99,90"
    if not precos:
        for m in re.findall(r'(?:por|partir de|desde|price|preco)\s*:?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})', texto, re.IGNORECASE):
            try:
                v = float(m.replace(".", "").replace(",", "."))
                if 1 < v < 200000:
                    precos.append(v)
            except ValueError:
                pass

    # Padrao 3: numeros com virgula que parecem precos (ex: "1.299,90" sozinho)
    if not precos:
        for m in re.findall(r'(\d{1,3}(?:\.\d{3})+,\d{2})', texto):
            try:
                v = float(m.replace(".", "").replace(",", "."))
                if 10 < v < 200000:
                    precos.append(v)
            except ValueError:
                pass

    return precos


LOJAS = {
    "amazon": "Amazon",
    "mercadolivre": "Mercado Livre",
    "produto.mercadolivre": "Mercado Livre",
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
    "nike": "Nike",
    "adidas": "Adidas",
    "netshoes": "Netshoes",
    "centauro": "Centauro",
    "dafiti": "Dafiti",
    "samsung": "Samsung",
    "apple": "Apple",
    "dell": "Dell",
    "lenovo": "Lenovo",
}


def identificar_loja(url):
    """Identifica a loja pelo dominio da URL."""
    domain = urlparse(url).netloc.lower()
    for chave, nome in LOJAS.items():
        if chave in domain:
            return nome
    domain = domain.replace("www.", "")
    parts = domain.split(".")
    return parts[0].capitalize() if parts else "Web"


def buscar_duckduckgo(query):
    """Busca no DuckDuckGo HTML e retorna lista de resultados."""
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "kl": "br-pt"},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for item in soup.select(".result"):
        title_el = item.select_one(".result__title a") or item.select_one(".result__a")
        snippet_el = item.select_one(".result__snippet")

        title = title_el.get_text(strip=True) if title_el else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        href = ""

        if title_el and title_el.get("href"):
            href = title_el["href"]
            if "uddg=" in href:
                match = re.search(r'uddg=([^&]+)', href)
                if match:
                    href = unquote(match.group(1))

        if title and href:
            results.append({"title": title, "snippet": snippet, "url": href})

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


def executar_query(query):
    """Executa uma query e retorna resultados brutos."""
    try:
        return buscar_duckduckgo(query)
    except Exception:
        return []


def buscar_produtos(produto):
    """Busca produtos com precos usando DuckDuckGo HTML."""
    resultados = []
    vistos = set()

    # Varias queries para maximizar resultados com precos
    queries = [
        f"{produto} preço reais",
        f"{produto} comprar R$",
        f"{produto} site:amazon.com.br",
        f"{produto} site:mercadolivre.com.br",
        f"{produto} site:magazineluiza.com.br",
        f"{produto} site:kabum.com.br",
        f"{produto} menor preço Brasil",
        f"{produto} oferta promoção preço",
    ]

    # Executa queries em paralelo (3 de cada vez)
    with ThreadPoolExecutor(max_workers=3) as pool:
        all_items = list(pool.map(executar_query, queries))

    for items in all_items:
        for item in items:
            try:
                titulo = item["title"]
                snippet = item["snippet"]
                url = item["url"]

                # Evita duplicatas por URL
                parsed_url = urlparse(url)
                chave_dup = parsed_url.netloc + parsed_url.path.rstrip("/")
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

                # Limpa titulo removendo precos e separadores finais
                nome = re.sub(r'\s*[-|–]\s*R\$.*', '', titulo).strip()
                nome = re.sub(r'\s*R\$\s*[\d.].*', '', nome).strip()
                nome = re.sub(r'\s*[-|–]\s*$', '', nome).strip()
                if len(nome) < 5:
                    nome = titulo

                resultados.append({
                    "nome": nome,
                    "preco": preco_valor,
                    "preco_texto": preco_texto,
                    "loja": loja,
                    "link": url,
                    "fonte": loja,
                    "imagem": "",
                    "avaliacao": "",
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
            self._respond(400, {"erro": "Parametro 'q' e obrigatorio."})
            return

        try:
            resultados = buscar_produtos(produto)
        except Exception as e:
            self._respond(200, {
                "produto": produto,
                "total": 0,
                "resultados": [],
                "avisos": [f"Erro: {e}"],
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

        self._respond(200, {
            "produto": produto,
            "total": len(filtrados),
            "resultados": filtrados,
            "avisos": [],
        })

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
