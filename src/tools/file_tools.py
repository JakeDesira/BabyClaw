import re
from pathlib import Path
from pypdf import PdfReader


BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "media_input"


def list_input_files():
    """
    Return a sorted list of file names inside the input directory.
    Only files are returned, not subdirectories.
    """
    if not INPUT_DIR.exists():
        return []

    return sorted(
        file.name
        for file in INPUT_DIR.iterdir()
        if file.is_file()
    )


def _normalize_query(text: str) -> str:
    """
    Normalize a prompt/file query for looser matching.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s.-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_file_in_input(filename: str) -> Path | None:
    """
    Find a file in the input directory using:
    1. exact path match
    2. case-insensitive exact filename match
    3. exact stem match
    4. extension-aware loose matching
    Important rule:
    If the query includes an extension, only files with that same extension
    may be matched.
    """
    if not INPUT_DIR.exists():
        return None

    query = filename.strip()

    if not query:
        return None

    exact_match = INPUT_DIR / query
    if exact_match.exists() and exact_match.is_file():
        return exact_match

    query_path = Path(query)
    query_name = query_path.name
    query_suffix = query_path.suffix.lower()
    query_stem = query_path.stem
    query_name_normalized = _normalize_query(query_name)
    query_stem_normalized = _normalize_query(query_stem)

    files = [file for file in INPUT_DIR.iterdir() if file.is_file()]

    # 1. Case-insensitive exact filename match
    for file in files:
        if file.name.lower() == query_name.lower():
            return file

    # 2. Exact stem match, but respect extension if supplied
    for file in files:
        if query_suffix and file.suffix.lower() != query_suffix:
            continue
        if _normalize_query(file.stem) == query_stem_normalized:
            return file

    # 3. Loose matching, but extension-aware if supplied
    candidates = []
    for file in files:
        if query_suffix and file.suffix.lower() != query_suffix:
            continue

        file_name_normalized = _normalize_query(file.name)
        file_stem_normalized = _normalize_query(file.stem)

        if query_name_normalized in file_name_normalized:
            candidates.append(file)
            continue

        if query_stem_normalized in file_stem_normalized:
            candidates.append(file)
            continue

        if file_stem_normalized in query_stem_normalized:
            candidates.append(file)
            continue

    if len(candidates) == 1:
        return candidates[0]

    return None


def get_input_files_by_extension(extensions: set[str]) -> list[Path]:
    """
    Return all files in the input directory whose suffix matches one of the given extensions.
    """
    if not INPUT_DIR.exists():
        return []

    return sorted(
        [
            file for file in INPUT_DIR.iterdir()
            if file.is_file() and file.suffix.lower() in extensions
        ],
        key=lambda f: f.name.lower()
    )


def get_single_obvious_file(prompt: str) -> Path | None:
    """
    Try to choose a single obvious file deterministically from the input directory.
    """
    if not INPUT_DIR.exists():
        return None

    all_files = [file for file in INPUT_DIR.iterdir() if file.is_file()]
    if len(all_files) == 1:
        return all_files[0]

    lower_prompt = prompt.lower()

    pdf_files = get_input_files_by_extension({".pdf"})
    text_files = get_input_files_by_extension({".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js"})

    if "pdf" in lower_prompt and len(pdf_files) == 1:
        return pdf_files[0]

    if ("text file" in lower_prompt or "txt file" in lower_prompt or "text" in lower_prompt) and len(text_files) == 1:
        return text_files[0]

    return None


def read_text_file(path):
    """
    Read a plain text file and return its content.
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{path}' is not a file."

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading text file '{path}': {e}"


def read_pdf_file(path):
    """
    Read a PDF file and return its extracted text content.
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{file_path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{file_path}' is not a file."

    try:
        reader = PdfReader(str(file_path))
        extracted_pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()

            if page_text and page_text.strip():
                extracted_pages.append(
                    f"--- Page {page_number} ---\n{page_text.strip()}"
                )

        if not extracted_pages:
            return (
                f"Warning: No extractable text was found in '{file_path.name}'. "
                "The PDF may contain scanned images instead of selectable text."
            )

        return "\n\n".join(extracted_pages)

    except Exception as e:
        return f"Error reading PDF file '{file_path.name}': {e}"


def read_file(path: str) -> str:
    """
    Read a file based on its extension.
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{path}' is not a file."

    suffix = file_path.suffix.lower()
    text_extensions = {".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js"}

    if suffix in text_extensions:
        return read_text_file(file_path)
    if suffix == ".pdf":
        return read_pdf_file(file_path)

    return f"Error: Unsupported file type '{suffix or 'unknown'}' is not supported yet."