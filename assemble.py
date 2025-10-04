import os
import sys
import json
import shutil
import hashlib
from pathlib import Path
import pikepdf

# --- Configuration ---
BASE_TEMP_DIR = Path("/tmp/pau_crea_processing")

# --- PDF Assembly (Corrected based on documentation) ---

def assemble_final_pdf(pdf_parts: list, manifest: dict, output_path: Path):
    """Merges all PDF parts into a single file, adding hierarchical bookmarks."""
    if not pdf_parts:
        print("No PDF parts were found to assemble.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Assembling {len(pdf_parts)} PDF parts into {output_path}...")

    page_offset = 0
    with pikepdf.Pdf.new() as final_pdf:
        # CORRECTED: Use the documented context manager for outlines
        with final_pdf.open_outline() as outline:
            for unit_name, resources_in_unit in manifest['resources_by_unit'].items():

                parts_for_this_unit = [p for p in pdf_parts if p['resource']['unit'] == unit_name]
                if not parts_for_this_unit: continue

                # The destination page for the unit will be the first page of its first resource
                unit_destination_page = page_offset
                unit_outline_item = pikepdf.OutlineItem(unit_name, unit_destination_page)
                # CORRECTED: Append to the root of the outline for top-level items
                outline.root.append(unit_outline_item)

                for resource in resources_in_unit:
                    matching_part = next((p for p in parts_for_this_unit if p['resource']['url'] == resource['url']), None)
                    if not matching_part: continue

                    try:
                        with pikepdf.open(matching_part['path']) as src:
                            # Create a bookmark for the resource itself, pointing to the current end of the document
                            resource_destination_page = page_offset
                            resource_outline_item = pikepdf.OutlineItem(resource['text'], resource_destination_page)
                            unit_outline_item.children.append(resource_outline_item)

                            final_pdf.pages.extend(src.pages)
                            page_offset += len(src.pages)
                    except Exception as e:
                        print(f"WARN: Could not append PDF part {matching_part['path']}. It may be corrupt. Reason: {e}")

    print(f"Saving final PDF with {len(final_pdf.pages)} pages...")
    try:
        final_pdf.save(output_path)
        print(f"Final PDF saved successfully to {output_path}")
    except Exception as e:
        print(f"FATAL: Could not save the final PDF. Reason: {e}")


# --- Main Assembly Logic ---

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <subject_name>")
        sys.exit(1)

    subject_name = sys.argv[1]

    manifest_path = Path(f"manifest_{subject_name}.json")
    if not manifest_path.exists():
        print(f"FATAL: Manifest file not found for '{subject_name}'")
        sys.exit(1)

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    subject_temp_dir = BASE_TEMP_DIR / subject_name
    if not subject_temp_dir.exists():
        print(f"FATAL: Temp directory for subject '{subject_name}' not found. Nothing to assemble.")
        sys.exit(1)

    print(f"--- Searching for pre-processed PDF parts in {subject_temp_dir} ---")

    found_parts = []
    resources = manifest.get('resource_list_ordered', [])

    for i, resource in enumerate(resources):
        resource_hash = hashlib.sha1(resource['url'].encode()).hexdigest()[:10]
        resource_temp_dir = subject_temp_dir / f"{i:03d}_{resource_hash}"

        potential_pdf_path = resource_temp_dir / "output.pdf"
        if not potential_pdf_path.exists():
            potential_pdf_path = resource_temp_dir / "direct.pdf"

        if potential_pdf_path.exists():
            # print(f"Found part for resource {i+1}: {potential_pdf_path}")
            found_parts.append({'path': potential_pdf_path, 'resource': resource})
        else:
            print(f"INFO: No pre-processed part found for resource {i+1} ('{resource['text']}'). It will be skipped.")

    final_pdf_path = Path("final") / f"CREA_{subject_name}.pdf"
    assemble_final_pdf(found_parts, manifest, final_pdf_path)

    print("\nAssembly complete.")

if __name__ == "__main__":
    main()