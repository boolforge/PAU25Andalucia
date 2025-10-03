import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin, urlparse
import time
import hashlib

# --- Configuration ---
USER_AGENT = "PAU-Collector/1.0 (+https://your.agent)"
SUBJECT_MAPPING = {
    "80": "Matematicas",
    "79": "Lengua_Castellana",
    "73": "Biologia",
    "140": "Comentario_de_texto",
    "78": "Ingles"
}
SEED_URLS = [
    "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php?etapa=6&materia=80",
    "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php?etapa=6&materia=79",
    "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php?etapa=6&materia=73",
    "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php?etapa=6&materia=140",
    "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php?etapa=6&materia=78"
]
ALLOWED_PATTERNS = [r'viewscorm\.jsp.*vi=downloadIms']
MANIFEST_FILE = "manifest.json"

def is_allowed(url):
    for pattern in ALLOWED_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False

def get_subject_from_url(url):
    try:
        query = urlparse(url).query
        params = dict(q.split('=') for q in query.split('&'))
        materia_id = params.get('materia', 'unknown')
        return SUBJECT_MAPPING.get(materia_id, f"unknown_subject_{materia_id}")
    except Exception:
        return "unknown_subject"

def discover_links(seed_url):
    discovered_resources = []
    headers = {'User-Agent': USER_AGENT}
    print(f"[*] Crawling seed URL for subject: {get_subject_from_url(seed_url)}")
    try:
        response = requests.get(seed_url, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[!] Error fetching {seed_url}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', href=True)
    subject = get_subject_from_url(seed_url)

    for link in links:
        href = link['href']
        absolute_url = urljoin(seed_url, href)
        if is_allowed(absolute_url):
            resource_id = hashlib.md5(absolute_url.encode()).hexdigest()
            resource_info = {
                'id': resource_id,
                'source_seed': seed_url,
                'url': absolute_url,
                'link_text': link.get_text(strip=True),
                'inferred_type': 'scorm_package',
                'referer_origin': seed_url,
                'subject': subject
            }
            if not any(d['url'] == absolute_url for d in discovered_resources):
                discovered_resources.append(resource_info)
    return discovered_resources

def main():
    all_discovered_resources = []
    print("[*] Starting discovery process...")
    for url in SEED_URLS:
        resources = discover_links(url)
        all_discovered_resources.extend(resources)
        print(f"[*] Found {len(resources)} unique packages for subject: {get_subject_from_url(url)}")
        time.sleep(1)

    all_discovered_resources.sort(key=lambda x: x['subject'])
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_discovered_resources, f, indent=4, ensure_ascii=False)
    print(f"\n[SUCCESS] Discovery complete. Manifest saved to: {MANIFEST_FILE}")

if __name__ == "__main__":
    main()