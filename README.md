# Project: PAU+25 (Junta de Andalucía) Material Processor

This project automates the collection, processing, and packaging of educational materials for the PAU+25 program from the Junta de Andalucía's educational portal.

## Goal

The primary goal was to process the web-based educational materials for five key subjects (Matemáticas, Lengua Castellana, Biología, Comentario de texto, and Inglés) and convert them into high-quality, portable, and accessible formats. The final deliverables for each subject are:

*   A high-fidelity, bookmarked, and searchable **PDF** file.
*   A well-structured and navigable **EPUB** file.

## Final, Successful Strategy: Chunked In-Memory Processing

After encountering several critical environmental limitations, the final, successful strategy was a **chunked, purely in-memory processing workflow**. This approach was designed to be highly efficient and robust, specifically to handle the resource constraints of the execution environment.

The workflow is orchestrated by two scripts:

1.  **`discover.py`**: This script first crawls the seed URLs to create a `manifest.json` file, which acts as a blueprint for the entire operation. It correctly maps the `materia` IDs from the URLs to their proper subject names.

2.  **`process_crea.py`**: This is the core processing engine. It is designed to be run **one time for each subject**, taking the subject name as a command-line argument (e.g., `python3 process_crea.py Biologia`). This "chunked" execution ensures that each run is short and stays well within the environment's timeout limits. For each subject, the script performs the following actions:
    *   **Download to RAM**: It fetches a single SCORM package (`.zip`) directly into a memory buffer (`io.BytesIO`), avoiding all disk writes for intermediate files.
    *   **Extract in RAM**: It uses the `zipfile` library to access the contents of the zip file directly from the memory buffer.
    *   **Process to PDF/EPUB**: For each HTML file within the package, it uses `Playwright` to render the page to a high-fidelity PDF page (stored temporarily on disk for assembly) and `pandoc` to prepare the HTML content for the EPUB.
    *   **Assemble and Save**: After all resources for the subject have been processed, the script merges the individual PDF pages into a final, bookmarked PDF and assembles the EPUB file, saving them directly to the `final_deliverables` directory.
    *   **Cleanup**: All temporary files for the subject are deleted before the script exits, ensuring a minimal disk footprint.

This strategy proved to be the most effective, as it successfully navigated all the environment's constraints.

## Challenges & "Marrones" (Failures) Encountered

The path to the final solution involved several significant failures. These are documented here transparently as requested.

1.  **Initial Compilation Failures**: The initial plan to compile the `scantailor-experimental` tool from source was a critical error. It led to a cascade of missing dependency errors and wasted significant time. The lesson is that pre-compiled binaries or standard package managers are always preferable to manual compilation in a constrained environment.

2.  **Critical Disk Space Error**: An intermediate strategy attempted to download all files for a subject before processing. This failed with a `total size is too large` error, as even the temporary files for one subject exceeded the available disk quota. This was a major failure in planning.

3.  **Critical Timeout Error**: The subsequent "all-in-one" in-memory processing script was a better design but also failed. It was designed to process all 50+ resources for all 5 subjects in a single run. While it solved the disk space issue, the total execution time was too long, causing the environment to time out.

4.  **Misunderstanding the `submit` command**: I incorrectly reported the task as complete after using the `submit` command, failing to understand that it only prepares the branch and requires user approval to be pushed. This was a fundamental error in understanding my own tools and led to confusion and wasted time.

The final, successful strategy of processing **one subject at a time** was the direct result of learning from all of these failures. It is robust against disk space limits, memory limits, and, most importantly, execution time limits.