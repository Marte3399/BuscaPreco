import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def buscar_google_shopping(produto, num_resultados=10):
    """Busca precos de produtos no Google Shopping via scraping."""
    url = f"https://www.google.com/search?q={quote_plus(produto)}&tbm=shop&hl=pt-BR"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    resultados = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[Google Shopping] Erro na requisicao: {e}")
        return resultados

    soup = BeautifulSoup(response.text, "html.parser")

    # Google Shopping results are in div.sh-dgr__content or similar containers
    items = soup.select("div.sh-dgr__content")

    if not items:
        # Fallback: try alternative selectors
        items = soup.select("div.sh-dlr__list-result")

    if not items:
        items = soup.select("div.xcR77")

    for item in items[:num_resultados]:
        try:
            # Extract product name
            nome_el = item.select_one("h3") or item.select_one("h4") or item.select_one("a")
            nome = nome_el.get_text(strip=True) if nome_el else "Produto sem nome"

            # Extract price
            preco_el = item.select_one("span.a8Pemb") or item.select_one("span.HRLxBb")
            if not preco_el:
                preco_el = item.select_one("span[aria-label*='R$']")
            if not preco_el:
                # Try to find any element with R$
                for span in item.find_all("span"):
                    text = span.get_text(strip=True)
                    if "R$" in text:
                        preco_el = span
                        break

            if not preco_el:
                continue

            preco_texto = preco_el.get_text(strip=True)
            preco_valor = _parse_preco(preco_texto)

            if preco_valor is None:
                continue

            # Extract seller/store
            loja_el = item.select_one("div.aULzUe") or item.select_one("div.IuHnof")
            loja = loja_el.get_text(strip=True) if loja_el else "Loja nao identificada"

            # Extract link
            link_el = item.select_one("a[href]")
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://www.google.com" + link

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


def _parse_preco(texto):
    """Converte texto de preco (ex: 'R$ 1.299,90') para float."""
    try:
        texto = texto.replace("R$", "").strip()
        texto = texto.replace("\xa0", "").replace(" ", "")
        # Handle Brazilian format: 1.299,90
        texto = texto.replace(".", "").replace(",", ".")
        return float(texto)
    except (ValueError, AttributeError):
        return None
