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

    # Padrao 1: R$ 1.299,90 / R$99,90 / R$ 99.90
    for m in re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})', texto):
        try:
            v = float(m.replace(".", "").replace(",", "."))
            if 1 < v < 200000:
                precos.append(v)
        except ValueError:
            pass

    # Padrao 2: "por 1.299,90" / "por 99,90" / "a partir de 99,90"
    if not precos:
        for m in re.findall(r'(?:por|partir de|desde|price|preco|preço|valor)\s*:?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})', texto, re.IGNORECASE):
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

    # Padrao 4: R$ com ponto como decimal (ex: "R$ 1299.90", "R$ 99.90")
    if not precos:
        for m in re.findall(r'R\$\s*(\d+\.\d{2})\b', texto):
            try:
                v = float(m)
                if 1 < v < 200000:
                    precos.append(v)
            except ValueError:
                pass

    # Padrao 5: apenas "R$ 99" ou "R$ 1299" (sem centavos)
    if not precos:
        for m in re.findall(r'R\$\s*(\d{2,6})\b(?!\s*[.,]\d)', texto):
            try:
                v = float(m)
                if 5 < v < 200000:
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
    "visa": "Visanet",
    "mercadolibre": "Mercado Livre",
    "shoptime": "Shoptime",
    "bemol": "Bemol",
    "havan": "Havan",
    "leroy": "Leroy Merlin",
    "leroymerlin": "Leroy Merlin",
    "madeira": "MadeiraMadeira",
    "consul": "Consul",
    "brastemp": "Brastemp",
    "electrolux": "Electrolux",
    "lg.com": "LG",
    "motorola": "Motorola",
    "xiaomi": "Xiaomi",
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


# Dominios de lojas conhecidas para incluir resultados mesmo sem preco visivel
DOMINIOS_LOJAS = [
    "amazon.com.br", "mercadolivre.com.br", "magazineluiza.com.br",
    "magalu.com.br", "americanas.com.br", "casasbahia.com.br",
    "kabum.com.br", "pichau.com.br", "terabyteshop.com.br",
    "shopee.com.br", "carrefour.com.br", "submarino.com.br",
    "fastshop.com.br", "extra.com.br", "pontofrio.com.br",
    "havan.com.br", "madeiramadeira.com.br", "colombo.com.br",
    "netshoes.com.br", "centauro.com.br", "dafiti.com.br",
]


def eh_loja_conhecida(url):
    """Verifica se a URL pertence a uma loja conhecida."""
    domain = urlparse(url).netloc.lower()
    return any(loja in domain for loja in DOMINIOS_LOJAS)


def buscar_produtos(produto):
    """Busca produtos com precos usando DuckDuckGo HTML."""
    resultados = []
    resultados_sem_preco = []
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
        f"{produto} site:americanas.com.br",
        f"{produto} site:casasbahia.com.br",
        f"{produto} comprar online barato",
        f"{produto} site:shopee.com.br",
    ]

    # Executa queries em paralelo (5 de cada vez para mais velocidade)
    with ThreadPoolExecutor(max_workers=5) as pool:
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

                loja = identificar_loja(url)

                # Limpa titulo removendo precos e separadores finais
                nome = re.sub(r'\s*[-|–]\s*R\$.*', '', titulo).strip()
                nome = re.sub(r'\s*R\$\s*[\d.].*', '', nome).strip()
                nome = re.sub(r'\s*[-|–]\s*$', '', nome).strip()
                if len(nome) < 5:
                    nome = titulo

                if precos:
                    preco_valor = min(precos)
                    preco_texto = formatar_preco(preco_valor)
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
                elif eh_loja_conhecida(url):
                    # Inclui resultados de lojas conhecidas mesmo sem preco
                    resultados_sem_preco.append({
                        "nome": nome,
                        "preco": 999999999,
                        "preco_texto": "Ver na loja",
                        "loja": loja,
                        "link": url,
                        "fonte": loja,
                        "imagem": "",
                        "avaliacao": "",
                    })
            except Exception:
                continue

    return resultados, resultados_sem_preco


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        produto = params.get("q", [""])[0].strip()

        if not produto:
            self._respond(400, {"erro": "Parametro 'q' e obrigatorio."})
            return

        try:
            resultados, resultados_sem_preco = buscar_produtos(produto)
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

        # Remove duplicatas (mesmo preco + mesma loja + nome similar)
        filtrados = []
        visto = set()
        for r in resultados:
            # Usa preco + loja + primeiras 30 chars do nome para dedup
            nome_curto = r["nome"][:30].lower().strip()
            chave = (r["preco"], r["loja"], nome_curto)
            if chave not in visto:
                visto.add(chave)
                filtrados.append(r)

        # Adiciona resultados sem preco ao final (de lojas conhecidas)
        for r in resultados_sem_preco:
            nome_curto = r["nome"][:30].lower().strip()
            chave_nome = (r["loja"], nome_curto)
            # Evita duplicar se ja temos resultado com preco da mesma loja/produto
            ja_tem = any(
                (f["loja"], f["nome"][:30].lower().strip()) == chave_nome
                for f in filtrados
            )
            if not ja_tem:
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
