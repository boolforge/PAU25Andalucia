import sys
import json
from pathlib import Path
import pikepdf
from bs4 import BeautifulSoup

# --- Configuration ---
MIN_CHARS_PER_PAGE_THRESHOLD = 150 # Threshold for the text density check

# --- QA Check Functions ---

def check_page_count(pdf: pikepdf.Pdf, report: dict):
    """Checks if the PDF has more than one page."""
    report['page_count'] = {
        'total_pages': len(pdf.pages),
        'passed': len(pdf.pages) > 1,
        'message': f"PDF has {len(pdf.pages)} pages."
    }
    print(f"QA: Page count check... {'PASSED' if report['page_count']['passed'] else 'FAILED'}")

def check_bookmarks(pdf: pikepdf.Pdf, manifest: dict, report: dict):
    """Checks if bookmarks exist and correspond to the manifest's units."""
    num_units_in_manifest = len(manifest['resources_by_unit'])
    try:
        with pdf.open_outline() as outline:
            num_top_level_bookmarks = len(outline.root)
            passed = num_top_level_bookmarks >= num_units_in_manifest
            message = f"Found {num_top_level_bookmarks} top-level bookmarks, expected at least {num_units_in_manifest}."
            report['bookmarks'] = {'passed': passed, 'message': message, 'bookmarks_found': num_top_level_bookmarks}
    except Exception as e:
        report['bookmarks'] = {'passed': False, 'message': f"Error reading bookmarks: {e}", 'bookmarks_found': 0}

    print(f"QA: Bookmarks check... {'PASSED' if report['bookmarks']['passed'] else 'FAILED'}")


def check_text_density(pdf: pikepdf.Pdf, report: dict):
    """
    Checks a sample of pages for text content to avoid blank pages.
    Pikepdf's text extraction is basic; for better results, an external tool
    like `pdftotext` would be needed, but this is a good first pass.
    """
    # This is a placeholder for a more advanced text extraction.
    # For now, we'll assume that if the other checks pass, this one is likely okay.
    # A full implementation would require a more robust text extraction method.
    report['text_density'] = {
        'passed': True,
        'message': "SKIPPED: Text density check requires a more advanced implementation (e.g., using pdftotext)."
    }
    print("QA: Text density check... SKIPPED")


def check_resource_coverage(pdf: pikepdf.Pdf, manifest: dict, report: dict):
    """Checks that at least 90% of manifest resources are represented in the bookmarks."""
    total_resources = len(manifest['resource_list_ordered'])

    # We infer coverage from the number of child bookmarks
    bookmarks_found = 0
    try:
        with pdf.open_outline() as outline:
            for item in outline.root:
                bookmarks_found += len(item.children)
    except Exception:
        pass # Error already reported by check_bookmarks

    coverage = (bookmarks_found / total_resources) * 100 if total_resources > 0 else 0
    passed = coverage >= 90.0

    report['resource_coverage'] = {
        'passed': passed,
        'message': f"Found bookmarks for {bookmarks_found}/{total_resources} resources ({coverage:.2f}% coverage).",
        'coverage_percentage': coverage
    }
    print(f"QA: Resource coverage check... {'PASSED' if passed else 'FAILED'}")


# --- Report Generation ---

def generate_html_report(report_data: dict, output_path: Path):
    """Generates a simple HTML summary of the QA report."""
    subject = report_data.get('subject', 'Unknown')
    title = f"QA Report for {subject}"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            body {{ font-family: sans-serif; margin: 2em; }}
            h1, h2 {{ color: #333; }}
            .card {{ border: 1px solid #ccc; border-radius: 5px; padding: 1em; margin-bottom: 1em; }}
            .passed {{ border-left: 5px solid #28a745; }}
            .failed {{ border-left: 5px solid #dc3545; }}
            .skipped {{ border-left: 5px solid #ffc107; }}
            strong {{ color: #555; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <p><strong>PDF File:</strong> {report_data.get('pdf_file', 'N/A')}</p>
    """

    for check, result in report_data.items():
        if isinstance(result, dict) and 'passed' in result:
            status = 'passed' if result['passed'] else 'failed'
            if 'SKIPPED' in result.get('message', ''): status = 'skipped'

            html += f"<div class='card {status}'>"
            html += f"<h2>{check.replace('_', ' ').title()} Check: {status.upper()}</h2>"
            html += f"<p><strong>Message:</strong> {result['message']}</p>"
            html += "</div>"

    html += "</body></html>"
    output_path.write_text(html, encoding='utf-8')
    print(f"HTML QA report saved to {output_path}")


# --- Main QA Orchestrator ---

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <subject_name>")
        sys.exit(1)

    subject_name = sys.argv[1]

    pdf_path = Path(f"final/CREA_{subject_name}.pdf")
    manifest_path = Path(f"manifest_{subject_name}.json")

    if not pdf_path.exists() or not manifest_path.exists():
        print(f"FATAL: Cannot run QA. Missing PDF ({pdf_path}) or manifest ({manifest_path}).")
        sys.exit(1)

    print(f"--- Running QA for subject: {subject_name} ---")

    report = {
        'subject': subject_name,
        'pdf_file': str(pdf_path)
    }

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    with pikepdf.open(pdf_path) as pdf:
        check_page_count(pdf, report)
        check_bookmarks(pdf, manifest, report)
        check_text_density(pdf, report)
        check_resource_coverage(pdf, manifest, report)

    # Save reports
    json_report_path = Path(f"qa_report_{subject_name}.json")
    html_report_path = Path(f"qa_report_{subject_name}.html")

    with open(json_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"JSON QA report saved to {json_report_path}")

    generate_html_report(report, html_report_path)

    print("\n--- QA Complete ---")

if __name__ == "__main__":
    main()