import os
import sys
import json
import requests
import zipfile
import io
import shutil
import hashlib
import re
import argparse
from urllib.parse import urlparse
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pikepdf

# --- Configuration ---
USER_AGENT = "PAU-Collector/2.0 (+https://your.agent)"
VIEWPORT_SIZE = {"width": 1200, "height": 800}
BASE_TEMP_DIR = Path("/tmp/pau_crea_processing")

# --- HTML to PDF Rendering ---
def render_html_to_pdf(url_or_path: str, output_pdf_path: Path, raw_dumps_dir: Path, dump_filename_base: str):
    """
    Renders a given URL or local HTML file to a PDF using Playwright.
    Handles MathJax rendering and creates fallback dumps on error.
    """
    print(f"Rendering to PDF: {url_or_path}")
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    raw_dumps_dir.mkdir(parents=True, exist_ok=True)

    p, browser, page = None, None, None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(user_agent=USER_AGENT, viewport=VIEWPORT_SIZE)

        # Set a generous default timeout for all page operations
        page.set_default_timeout(90000)

        page.goto(str(url_or_path), wait_until='networkidle')

        # Wait for MathJax to finish rendering
        try:
            print("Checking for MathJax...")
            page.evaluate("""
                async () => {
                    if (window.MathJax) {
                        console.log('MathJax found. Awaiting typeset promise...');
                        if (window.MathJax.typesetPromise) { // v3
                            await window.MathJax.typesetPromise();
                        } else if (window.MathJax.Hub && window.MathJax.Hub.Queue) { // v2
                            await new Promise(resolve => window.MathJax.Hub.Queue(resolve));
                        }
                    }
                }
            """)
            print("MathJax rendering complete or not found.")
        except PlaywrightTimeoutError:
            print("WARN: MathJax processing timed out. Formulas might be missing.")

        page.wait_for_timeout(500)

        page.pdf(
            path=str(output_pdf_path),
            format='A4',
            print_background=True,
            margin={'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'}
        )

        fallback_text_path = raw_dumps_dir / f"{dump_filename_base}_fallback.txt"
        fallback_text_path.write_text(page.inner_text('body'), encoding='utf-8')
        return output_pdf_path
    except Exception as e:
        print(f"FATAL: Playwright PDF generation failed. Reason: {e}")
        if page:
            try:
                screenshot_path = raw_dumps_dir / f"{dump_filename_base}.png"
                html_dump_path = raw_dumps_dir / f"{dump_filename_base}.html"
                page.screenshot(path=str(screenshot_path), full_page=True)
                html_dump_path.write_text(page.content(), encoding='utf-8')
                print(f"Saved error dumps to {raw_dumps_dir}")
            except Exception as dump_e:
                print(f"Could not save debug dumps. Reason: {dump_e}")
        return None
    finally:
        if browser: browser.close()
        if p: p.stop()

# --- Resource Processors ---
def process_scorm_zip(resource: dict, resource_temp_dir: Path, raw_dumps_dir: Path, dump_filename_base: str):
    print("Downloading SCORM zip...")
    response = requests.get(resource['url'], headers={'User-Agent': USER_AGENT}, timeout=120)
    response.raise_for_status()
    extract_path = resource_temp_dir / "unzipped"
    extract_path.mkdir()
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall(extract_path)
    entry_point = None
    manifest_path = extract_path / "imsmanifest.xml"
    if manifest_path.exists():
        match = re.search(r'<resource.*?href="([^"]+\.html?)".*?>', manifest_path.read_text(encoding='utf-8', errors='ignore'))
        if match: entry_point = extract_path / match.group(1)
    if not entry_point or not entry_point.exists():
        for name in ['index.html', 'index.htm', 'main.html', 'content.html', 'start.html']:
            if (extract_path / name).exists():
                entry_point = extract_path / name
                break
    if not entry_point:
        print("ERROR: No HTML entry point found in SCORM package.")
        return None
    return render_html_to_pdf(entry_point.as_uri(), resource_temp_dir / "output.pdf", raw_dumps_dir, dump_filename_base)

def process_direct_pdf(resource: dict, resource_temp_dir: Path):
    print("Downloading direct PDF...")
    response = requests.get(resource['url'], headers={'User-Agent': USER_AGENT}, timeout=120)
    response.raise_for_status()
    output_pdf_path = resource_temp_dir / "direct.pdf"
    output_pdf_path.write_bytes(response.content)
    try:
        pikepdf.open(output_pdf_path)
        return output_pdf_path
    except Exception:
        print("ERROR: Downloaded file is not a valid PDF.")
        return None

# --- Main Orchestrator ---
def process_subject_batch(subject_name: str, start_index: int, count: int):
    manifest_path = Path(f"manifest_{subject_name}.json")
    if not manifest_path.exists():
        print(f"FATAL: Manifest not found for '{subject_name}'")
        sys.exit(1)
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    subject_temp_dir = BASE_TEMP_DIR / subject_name
    raw_dumps_dir = Path(f"raw_dumps/{subject_name}")
    raw_dumps_dir.mkdir(parents=True, exist_ok=True)

    resources = manifest.get('resource_list_ordered', [])
    end_index = min(start_index + count, len(resources))

    print(f"=== Processing subject: {subject_name} | Batch: {start_index}-{end_index-1} of {len(resources)} ===")

    for i in range(start_index, end_index):
        resource = resources[i]
        print("-" * 80)
        print(f"Processing resource {i+1}/{len(resources)}: [{resource['type']}] \"{resource['text']}\"")

        resource_hash = hashlib.sha1(resource['url'].encode()).hexdigest()[:10]
        resource_temp_dir = subject_temp_dir / f"{i:03d}_{resource_hash}"

        if resource_temp_dir.exists() and ( (resource_temp_dir / "output.pdf").exists() or (resource_temp_dir / "direct.pdf").exists()):
            print("Already processed. Skipping.")
            continue

        shutil.rmtree(resource_temp_dir, ignore_errors=True)
        resource_temp_dir.mkdir(parents=True)
        dump_filename_base = f"{i:03d}_{resource_hash}"

        try:
            if resource['type'] == 'scorm_zip':
                process_scorm_zip(resource, resource_temp_dir, raw_dumps_dir, dump_filename_base)
            elif resource['type'] in ['agrega_html', 'scorm_html']:
                render_html_to_pdf(resource['url'], resource_temp_dir / "output.pdf", raw_dumps_dir, dump_filename_base)
            elif resource['type'] == 'pdf':
                process_direct_pdf(resource, resource_temp_dir)
        except Exception as e:
            print(f"ERROR: Unhandled exception for resource {resource['url']}. Reason: {e}")

    print(f"=== Finished batch {start_index}-{end_index-1} ===")

# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a subject's resources in batches.")
    parser.add_argument("subject_name", type=str, help="The name of the subject to process.")
    parser.add_argument("--start", type=int, default=0, help="The starting index of the resources to process.")
    parser.add_argument("--count", type=int, default=10, help="The number of resources to process in this batch.")
    args = parser.parse_args()

    process_subject_batch(args.subject_name, args.start, args.count)