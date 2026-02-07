"""Endpoint de teste para verificar se o deploy esta atualizado."""

import json
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Testa se as dependencias funcionam
        status = {}
        try:
            import requests
            status["requests"] = "ok"
        except ImportError as e:
            status["requests"] = str(e)

        try:
            from bs4 import BeautifulSoup
            status["beautifulsoup4"] = "ok"
        except ImportError as e:
            status["beautifulsoup4"] = str(e)

        # Testa busca no DuckDuckGo
        try:
            import requests as req
            resp = req.post(
                "https://html.duckduckgo.com/html/",
                data={"q": "teste preço R$ 100,00", "kl": "br-pt"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            status["duckduckgo_status"] = resp.status_code
            status["duckduckgo_length"] = len(resp.text)

            from bs4 import BeautifulSoup as BS
            soup = BS(resp.text, "html.parser")
            results = soup.select(".result")
            status["duckduckgo_results"] = len(results)
            if results:
                t = results[0].select_one(".result__title a") or results[0].select_one(".result__a")
                status["first_title"] = t.get_text(strip=True)[:100] if t else "nenhum"
        except Exception as e:
            status["duckduckgo_error"] = str(e)

        data = {
            "versao": "duckduckgo-html-v2",
            "status": status,
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
