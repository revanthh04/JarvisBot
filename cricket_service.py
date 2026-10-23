import requests
import xml.etree.ElementTree as ET

def get_live_cricket_scores() -> list:
    url = "https://static.cricinfo.com/rss/livescores.xml"
    headers = {"User-Agent": "JarvisBot/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        
        matches = []
        for item in root.findall(".//item"):
            title = item.find("title")
            description = item.find("description")
            link = item.find("link")
            
            t_text = title.text.strip() if title is not None and title.text else "Match"
            d_text = description.text.strip() if description is not None and description.text else ""
            l_text = link.text.strip() if link is not None and link.text else ""
            
            matches.append({
                "match": t_text,
                "status": d_text,
                "link": l_text
            })
            if len(matches) >= 6:
                break
        return matches if matches else [{"status": "No active live matches right now."}]
    except Exception as e:
        # Fallback to search query
        from search_service import search_web
        res = search_web("live cricket score today match status", max_results=3)
        return [{"status": r.get("title", "") + " - " + r.get("body", "")} for r in res]
