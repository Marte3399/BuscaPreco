import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def buscar_amazon(produto, num_resultados=10):
    """Busca precos de produtos na Amazon Brasil via scraping."""
    url = f"https://www.amazon.com.br/s?k={quote_plus(produto)}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    resultados = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[Amazon] Erro na requisicao: {e}")
        return resultados

    soup = BeautifulSoup(response.text, "html.parser")

    # Amazon product cards
    items = soup.select("div[data-component-type='s-search-result']")

    for item in items[:num_resultados]:
        try:
            # Extract product name
            nome_el = item.select_one("h2 a span") or item.select_one("h2 span")
            nome = nome_el.get_text(strip=True) if nome_el else "Produto sem nome"

            # Extract price - whole part and fraction
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

            # Extract price display text
            preco_symbol_el = item.select_one("span.a-price-symbol")
            simbolo = preco_symbol_el.get_text(strip=True) if preco_symbol_el else "R$"
            preco_texto = f"{simbolo} {preco_inteiro_el.get_text(strip=True)},{preco_frac}"

            # Extract link
            link_el = item.select_one("h2 a[href]")
            link = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("http"):
                    link = href
                else:
                    link = "https://www.amazon.com.br" + href

            # Extract rating (optional)
            rating_el = item.select_one("span.a-icon-alt")
            rating = rating_el.get_text(strip=True) if rating_el else ""

            resultados.append({
                "nome": nome,
                "preco": preco_valor,
                "preco_texto": preco_texto,
                "loja": "Amazon",
                "link": link,
                "fonte": "Amazon",
                "avaliacao": rating,
            })
        except Exception:
            continue

    return resultados
