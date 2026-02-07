"""
Vercel Serverless Function - Busca de precos usando DuckDuckGo.
Sem API key, sem bloqueio de IP, 100% gratis.
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from duckduckgo_search import DDGS


def extrair_precos(texto):
    """Extrai todos os precos em R$ de um texto."""
    # Padroes: R$ 1.299,90 / R$1299,90 / R$ 1299.90 / R$ 99,90
    padroes = re.findall(
        r'R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)',
        texto
    )
    precos = []
    for p in padroes:
        try:
            valor = p.replace(".", "").replace(",", ".")
            valor = float(valor)
            if valor > 0:
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
        "extra.com": "Extra",
        "kabum": "KaBuM!",
        "pichau": "Pichau",
        "terabyte": "Terabyteshop",
        "shopee": "Shopee",
        "aliexpress": "AliExpress",
        "carrefour": "Carrefour",
        "pontofrio": "Ponto Frio",
        "submarino": "Submarino",
        "zoom.com": "Zoom",
        "buscape": "Buscape",
        "pelando": "Pelando",
        "promobit": "Promobit",
    }
    for chave, nome in lojas.items():
        if chave in domain:
            return nome
    # Retorna dominio limpo
    domain = domain.replace("www.", "")
    return domain.split(".")[0].capitalize() if domain else ""


def buscar_produtos(produto, max_resultados=30):
    """Busca produtos e precos no DuckDuckGo."""
    resultados = []
    vistos = set()  # evitar duplicatas por URL

    queries = [
        f"{produto} preço comprar",
        f"{produto} menor preço loja online",
    ]

    with DDGS() as ddgs:
        for query in queries:
            try:
                items = ddgs.text(
                    query,
                    region="br-pt",
                    max_results=max_resultados,
                )
            except Exception:
                continue

            for item in items:
                try:
                    titulo = item.get("title", "")
                    snippet = item.get("body", "")
                    url = item.get("href", "")

                    if not titulo or not url:
                        continue

                    # Evita duplicatas
                    dominio_path = urlparse(url).netloc + urlparse(url).path
                    if dominio_path in vistos:
                        continue
                    vistos.add(dominio_path)

                    # Extrai precos do titulo e snippet
                    texto_completo = f"{titulo} {snippet}"
                    precos = extrair_precos(texto_completo)

                    if not precos:
                        continue

                    # Usa o menor preco encontrado no texto
                    preco_valor = min(precos)

                    # Formata preco texto
                    if preco_valor >= 1000:
                        inteiro = int(preco_valor)
                        centavos = int(round((preco_valor - inteiro) * 100))
                        inteiro_fmt = f"{inteiro:,}".replace(",", ".")
                        preco_texto = f"R$ {inteiro_fmt},{centavos:02d}"
                    else:
                        preco_texto = f"R$ {preco_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    loja = identificar_loja(url)

                    # Limpa titulo removendo precos e lixo
                    nome = re.sub(r'\s*[-|]\s*R\$.*', '', titulo).strip()
                    nome = re.sub(r'\s*R\$\s*\d.*', '', nome).strip()
                    if not nome:
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
                "avisos": [f"Erro na busca: {e}"],
            })
            return

        # Ordena por preco crescente
        resultados.sort(key=lambda x: x["preco"])

        # Remove duplicatas muito similares (mesmo preco + mesmo dominio)
        filtrados = []
        visto_preco_loja = set()
        for r in resultados:
            chave = (r["preco"], r["loja"])
            if chave not in visto_preco_loja:
                visto_preco_loja.add(chave)
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
