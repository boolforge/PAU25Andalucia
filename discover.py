from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin, urlparse, parse_qs
import sys
import re
import time

# --- Configuration ---
BASE_URL = "https://www.juntadeandalucia.es/educacion/permanente/materiales/index.php"
USER_AGENT = "PAU-Collector/2.0 (+https://your.agent)"
SUBJECT_ID = ""

# --- Helper Functions ---

def classify_resource(url: str):
    """Classifies a resource based on its URL pattern."""
    url_lower = url.lower()
    if 'viewscorm.jsp' in url_lower:
        return 'scorm_zip' if 'downloadims=true' in url_lower else 'scorm_html'
    if '.zip' in url_lower: return 'zip'
    if '.pdf' in url_lower: return 'pdf'
    if 'pluginfile.php' in url_lower: return 'pluginfile'
    if 'agrega.juntadeandalucia.es' in url_lower: return 'agrega_html'
    return 'other'

def get_page_content_with_playwright(url: str):
    """Uses Playwright to fully load a page and return its HTML content."""
    print(f"Fetching with Playwright: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            # A short wait can help ensure all elements are stable
            page.wait_for_timeout(1500)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"FATAL: Playwright failed for {url}. Reason: {e}")
        return None

# --- Core Discovery Logic ---

def find_unit_urls(main_subject_url: str):
    """Scans the main subject page to find links to all individual unit pages."""
    print("--- Phase 1: Discovering Unit URLs ---")
    html_content = get_page_content_with_playwright(main_subject_url)
    if not html_content:
        return {}

    soup = BeautifulSoup(html_content, 'lxml')
    unit_links = {}

    # Corrected Selector: The unit links are in a <ul> with specific classes
    unit_nav = soup.find('ul', class_='nav-tabs')
    if not unit_nav:
        print("FATAL: Could not find unit navigation bar ('ul.nav-tabs'). Cannot proceed.")
        return {}

    unit_pattern = re.compile(r'Unidad\s*(\d+)', re.IGNORECASE)
    for a_tag in unit_nav.find_all('a', href=re.compile(r'unidad=\d+')):
        text = a_tag.get_text(strip=True)
        match = unit_pattern.search(text)
        if match:
            unit_name = f"Unidad {match.group(1)}"
            full_url = urljoin(BASE_URL, a_tag['href'])
            unit_links[unit_name] = full_url
            print(f"Found unit: '{unit_name}' -> {full_url}")

    return unit_links

def extract_resources_from_unit_page(unit_url: str):
    """Visits a unit page and extracts all resource links from the main content table."""
    print(f"\n--- Processing Unit Page: {unit_url} ---")
    html_content = get_page_content_with_playwright(unit_url)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'lxml')
    # Corrected Selector: The resources are inside this specific table
    content_table = soup.find('table', class_='table-hover')
    if not content_table:
        print(f"WARN: Could not find content table ('table.table-hover') on {unit_url}. Skipping unit.")
        return []

    resources = []
    processed_urls = set()

    for a_tag in content_table.find_all('a', href=True):
        href = a_tag['href']
        full_url = urljoin(unit_url, href)
        resource_type = classify_resource(full_url)

        if resource_type == 'other':
            continue

        # Prefer download links for SCORM packages
        if resource_type == 'scorm_html':
            download_url = full_url.replace('?.vi=file', '?.vi=downloadIms&scormtree.download=true')
            if download_url in processed_urls:
                continue
            full_url = download_url
            resource_type = 'scorm_zip'

        if full_url in processed_urls:
            continue

        # Find meaningful text for the resource
        row = a_tag.find_parent('tr')
        text = "Enlace de Recurso"
        if row:
            # The text is usually in the first or second cell of the row
            first_th = row.find('th')
            first_td = row.find('td')
            if first_th and first_th.get_text(strip=True):
                text = first_th.get_text(strip=True)
            elif first_td and first_td.get_text(strip=True):
                text = first_td.get_text(strip=True)

        resources.append({
            'url': full_url,
            'text': text,
            'type': resource_type,
        })
        processed_urls.add(full_url)
        print(f"  -> Found: [{resource_type}] {text}")

    return resources

# --- Main Execution ---

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <subject_name> <subject_url>")
        sys.exit(1)

    subject_name = sys.argv[1]
    subject_url = sys.argv[2]

    global SUBJECT_ID
    parsed_q = parse_qs(urlparse(subject_url).query)
    SUBJECT_ID = parsed_q.get('materia', [''])[0]
    if not SUBJECT_ID:
        print("FATAL: Could not get 'materia' ID from URL.")
        sys.exit(1)

    print(f"=== Starting FINAL Discovery for: {subject_name} (ID: {SUBJECT_ID}) ===")

    unit_urls_map = find_unit_urls(subject_url)
    if not unit_urls_map:
        sys.exit(1)

    resources_by_unit = {}
    for unit_name, unit_url in sorted(unit_urls_map.items()):
        resources = extract_resources_from_unit_page(unit_url)
        if resources:
            for res in resources:
                res['unit'] = unit_name
            resources_by_unit[unit_name] = resources

    flat_resource_list = [res for _, unit_res in sorted(resources_by_unit.items()) for res in unit_res]

    manifest = {
        'subject': subject_name,
        'seed_url': subject_url,
        'resources_by_unit': resources_by_unit,
        'resource_list_ordered': flat_resource_list
    }

    manifest_filename = f"manifest_{subject_name}.json"
    with open(manifest_filename, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\n=== Discovery Complete ===")
    print(f"Manifest created: {manifest_filename}")
    print(f"Found {len(flat_resource_list)} relevant resources in {len(resources_by_unit)} units.")

if __name__ == "__main__":
    main()