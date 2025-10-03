import json
import os
import subprocess
import hashlib
import time

# --- Configuration ---
MANIFEST_FILE = "manifest_discovery.json"
DOWNLOAD_DIR = "downloads"
CHECKSUMS_FILE = "checksums.json"
USER_AGENT = "PAU-Collector/1.0 (+https://your.agent)"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 8, 30]

def calculate_sha256(filepath):
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def download_file(resource_info):
    """
    Downloads a single file using wget, with retries and backoff.
    """
    url = resource_info['url']
    subject = resource_info['subject']

    # Create a directory for the subject if it doesn't exist
    subject_dir = os.path.join(DOWNLOAD_DIR, subject)
    os.makedirs(subject_dir, exist_ok=True)

    # We only want to download the SCORM packages, which are zip files.
    # The links with "downloadIms" are the ones that provide the zip file.
    if "downloadIms" not in url:
        return None, "skipped_not_a_package"

    command = [
        'wget',
        '--content-disposition',
        '--no-check-certificate',
        f'--user-agent={USER_AGENT}',
        f'--referer={resource_info["referer_origin"]}',
        '-P', subject_dir,
        url
    ]

    for attempt in range(MAX_RETRIES):
        try:
            print(f"[*] Downloading (Attempt {attempt + 1}/{MAX_RETRIES}): {url}")
            process = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)

            for line in process.stderr.splitlines():
                if 'Saving to: ‘' in line:
                    filepath = line.split('Saving to: ‘')[-1].strip().replace('’', '')
                    print(f"  [+] Saved to: {filepath}")
                    return filepath, "downloaded"

            print(f"[!] Download succeeded but could not determine filename for {url}")
            return None, "failed_to_get_filename"

        except subprocess.CalledProcessError as e:
            print(f"[!] wget error for {url}. Return code: {e.returncode}")
            print(f"  Stderr: {e.stderr}")
        except subprocess.TimeoutExpired:
            print(f"[!] Timeout expired for {url}.")

        if attempt < MAX_RETRIES - 1:
            backoff_time = RETRY_BACKOFF_SECONDS[attempt]
            print(f"  [*] Retrying in {backoff_time} seconds...")
            time.sleep(backoff_time)

    print(f"[!!!] FAILED to download {url} after {MAX_RETRIES} attempts.")
    return None, "failed_after_retries"

def main():
    """
    Main function to orchestrate the download process.
    """
    if not os.path.exists(MANIFEST_FILE):
        print(f"[!] Manifest file not found: {MANIFEST_FILE}")
        return

    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        resources = json.load(f)

    checksums = {}
    if os.path.exists(CHECKSUMS_FILE):
        with open(CHECKSUMS_FILE, 'r') as f:
            checksums = json.load(f)

    for resource in resources:
        if resource['url'] in checksums and checksums[resource['url']]['sha256'] != 'download_failed':
            print(f"[*] Skipping already downloaded file: {resource['url']}")
            continue

        downloaded_filepath, status = download_file(resource)

        if status == "downloaded" and downloaded_filepath and os.path.exists(downloaded_filepath):
            checksum = calculate_sha256(downloaded_filepath)
            checksums[resource['url']] = {
                'local_path': downloaded_filepath,
                'sha256': checksum,
                'status': 'downloaded'
            }
            print(f"  [+] Checksum (SHA256): {checksum}")
        elif status != "skipped_not_a_package":
            checksums[resource['url']] = {
                'local_path': None,
                'sha256': 'download_failed',
                'status': status
            }

        # Save checksums after each attempt to checkpoint progress
        with open(CHECKSUMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(checksums, f, indent=4)

    print("\n[SUCCESS] Download stage complete.")

if __name__ == "__main__":
    main()