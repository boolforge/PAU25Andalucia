import requests
import json
import os
import io
import zipfile
import subprocess
import time
import shutil
import sys
from collections import defaultdict
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import pikepdf

# --- Configuration ---
MANIFEST_FILE = "manifest.json"
OUTPUT_DIR = "final_deliverables"
USER_AGENT = "PAU-Collector/1.0 (+https://your.agent)"
LOG_FILE = "processing_log.txt"
TEMP_DIR = "temp_processing"

def logger(message):
    """Logs a message to both the console and the log file."""
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(message + '\n')

def get_resources_for_subject(target_subject):
    """Reads the manifest and returns resources for a specific subject."""
    if not os.path.exists(MANIFEST_FILE):
        logger(f"[!!!] CRITICAL: Manifest file not found: {MANIFEST_FILE}")
        return None

    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        resources = json.load(f)

    subject_resources = [r for r in resources if r['subject'] == target_subject]

    if not subject_resources:
        logger(f"[!] No resources found in manifest for subject: {target_subject}")
        return None

    logger(f"[*] Found {len(subject_resources)} resources for subject: {target_subject}")
    return subject_resources

def process_subject(subject, resources, browser):
    """Processes all resources for a single subject using a pure in-memory workflow."""
    logger(f"\n{'='*40}")
    logger(f"[*] Starting processing for subject: {subject}")
    logger(f"{'='*40}")

    pdf_page_files = []
    epub_chapters_content = []

    temp_subject_dir = os.path.join(TEMP_DIR, subject)
    os.makedirs(temp_subject_dir, exist_ok=True)

    for i, resource in enumerate(resources):
        logger(f"\n--- Processing resource {i+1}/{len(resources)} for {subject} ---")
        logger(f"  URL: {resource['url']}")

        try:
            response = requests.get(resource['url'], headers={'User-Agent': USER_AGENT}, timeout=180)
            response.raise_for_status()
            zip_buffer = io.BytesIO(response.content)
            logger("  [+] Downloaded resource to memory.")

            with zipfile.ZipFile(zip_buffer) as z:
                html_files = [f for f in z.namelist() if f.endswith(('.html', '.htm'))]
                if not html_files:
                    logger("  [!] No HTML file found. Skipping.")
                    continue

                index_file = next((f for f in html_files if 'index' in f.lower()), html_files[0])

                extract_path = os.path.join(temp_subject_dir, f"res_{i+1}")
                z.extractall(extract_path)

                html_path = os.path.join(extract_path, index_file)
                logger(f"  [*] Extracted to temp path for rendering: {html_path}")

                page_pdf_path = os.path.join(temp_subject_dir, f"page_{i+1}.pdf")
                browser_page = browser.new_page()
                browser_page.goto(f"file://{os.path.abspath(html_path)}", wait_until='networkidle', timeout=60000)
                time.sleep(3)
                browser_page.pdf(path=page_pdf_path, format='A4', print_background=True)
                browser_page.close()
                pdf_page_files.append(page_pdf_path)
                logger(f"  [+] Rendered PDF page: {page_pdf_path}")

                with open(html_path, 'r', encoding='utf-8') as f_in:
                    soup = BeautifulSoup(f_in.read(), 'html.parser')
                    title = soup.title.string if soup.title else f"Chapter {i+1}"
                    chapter_content = f"<h1>{title}</h1>\n{soup.body}"
                    epub_chapters_content.append(chapter_content)
                logger("  [+] Extracted EPUB content.")

                shutil.rmtree(extract_path)

        except Exception as e:
            logger(f"[!!!] FAILED to process resource {resource['url']}. Error: {e}")

    logger(f"\n[*] Finalizing files for subject: {subject}")

    if pdf_page_files:
        final_pdf_path = os.path.join(OUTPUT_DIR, f"PAU_{subject}_CREA.pdf")
        try:
            with pikepdf.Pdf.new() as pdf:
                for page_file in pdf_page_files:
                    with pikepdf.Pdf.open(page_file) as src:
                        pdf.pages.extend(src.pages)
                pdf.save(final_pdf_path)
            logger(f"  [SUCCESS] Saved final PDF: {final_pdf_path}")
        except Exception as e:
            logger(f"[!!!] FAILED to save final PDF for {subject}. Error: {e}")

    if epub_chapters_content:
        final_epub_path = os.path.join(OUTPUT_DIR, f"PAU_{subject}_CREA.epub")
        full_html_content = "\n".join(epub_chapters_content)
        try:
            process = subprocess.run(
                ['pandoc', '-f', 'html', '-t', 'epub', '--toc', f'--metadata=title:{subject}', '-o', final_epub_path],
                input=full_html_content, text=True, check=True, capture_output=True
            )
            logger(f"  [SUCCESS] Saved final EPUB: {final_epub_path}")
        except subprocess.CalledProcessError as e:
            logger(f"[!!!] FAILED to save final EPUB for {subject}. Pandoc Error: {e.stderr}")

    shutil.rmtree(temp_subject_dir)
    logger(f"  [+] Cleaned up temporary files for {subject}.")

def main():
    """Main function to orchestrate the processing of a single subject."""
    if len(sys.argv) != 2:
        print("Usage: python process_crea.py <SubjectName>")
        print("Example: python process_crea.py Matematicas")
        sys.exit(1)

    target_subject = sys.argv[1]

    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, 'w').close() # Create log file if it doesn't exist

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    resources = get_resources_for_subject(target_subject)
    if not resources:
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        process_subject(target_subject, resources, browser)
        browser.close()

    logger(f"\n[SUCCESS] Processing for subject {target_subject} is complete.")

if __name__ == "__main__":
    main()