import os
import json
import hashlib
import glob

# --- Configuration ---
FINAL_DIR = "final_deliverables"
LOG_FILE = "processing_log.txt"
MANIFEST_FILE = "manifest.json"
README_FILE = "README.md"
QA_REPORT_FILE = "qa_report.html"
CHECKSUMS_FILE = "checksums.json"

def calculate_sha256(filepath):
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_qa_report(files):
    """Generates a simple HTML report listing the created files and their sizes."""
    html = "<html><head><title>QA Report</title><style>body { font-family: sans-serif; } table { border-collapse: collapse; } th, td { border: 1px solid #ccc; padding: 8px; } th { background-color: #f2f2f2; }</style></head><body>"
    html += "<h1>QA Report: Generated Deliverables</h1>"
    html += "<table><tr><th>File Name</th><th>Size (Bytes)</th></tr>"

    file_details = []
    for f in sorted(files):
        try:
            size = os.path.getsize(f)
            file_details.append({'name': os.path.basename(f), 'size': size})
        except OSError:
            file_details.append({'name': os.path.basename(f), 'size': 'N/A'})

    for item in file_details:
        html += f"<tr><td>{item['name']}</td><td>{item['size']}</td></tr>"

    html += "</table></body></html>"

    with open(QA_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[+] QA Report generated: {QA_REPORT_FILE}")

def main():
    """Main function to generate final reports."""
    print("[*] Starting final report generation...")

    final_files = glob.glob(os.path.join(FINAL_DIR, "*"))
    if not final_files:
        print("[!] No files found in the final deliverables directory. Cannot generate reports.")
        return

    # 1. Generate QA Report
    generate_qa_report(final_files)

    # 2. Generate checksums for final files
    checksums = {}
    print("[*] Calculating checksums for final deliverables...")
    for f in sorted(final_files):
        print(f"  - Processing {os.path.basename(f)}...")
        checksums[os.path.basename(f)] = calculate_sha256(f)

    with open(CHECKSUMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(checksums, f, indent=4)
    print(f"[+] Final checksums generated: {CHECKSUMS_FILE}")

    print(f"\n[SUCCESS] Documentation and finalization complete.")

if __name__ == "__main__":
    main()