try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup

def search_web(query: str, max_results: int = 5) -> list:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [{"title": r.get("title"), "href": r.get("href"), "body": r.get("body")} for r in results]
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]

def fetch_page_summary(url: str, max_chars: int = 2000) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip scripts and styles
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.extract()

        text = ' '.join(soup.stripped_strings)
        return text[:max_chars]
    except Exception as e:
        return f"Failed to fetch content from {url}: {e}"
