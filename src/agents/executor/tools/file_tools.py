import re
import subprocess
import sys
from pathlib import Path
from pypdf import PdfReader


from paths import MEDIA_INPUT_DIR


INPUT_DIR = MEDIA_INPUT_DIR
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js"}

SKIP_SEARCH_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
}


def list_input_files() -> list[str]:
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


def _safe_rglob_by_name(root: Path, target_name: str, max_matches: int = 25) -> list[Path]:
    """
    Recursively search for files/directories by exact name while skipping heavy folders.
    """
    matches = []

    try:
        for candidate in root.rglob(target_name):
            if any(part in SKIP_SEARCH_DIRS for part in candidate.parts):
                continue

            if candidate.exists():
                matches.append(candidate)

            if len(matches) >= max_matches:
                break

    except Exception:
        return matches

    return matches


def _split_action_pair(action_input: str, action_name: str) -> tuple[str, str] | str:
    """
    Split low-level tool input in the format left::right.

    Returns either:
    - (left, right)
    - error string
    """
    parts = action_input.split("::", 1)

    if len(parts) != 2:
        return f"Error: {action_name} requires 'filepath::content' format."

    left, right = parts
    left = left.strip()

    if not left:
        return f"Error: {action_name} requires a file path."

    return left, right


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

    for file in files:
        if file.name.lower() == query_name.lower():
            return file

    for file in files:
        if query_suffix and file.suffix.lower() != query_suffix:
            continue
        if _normalize_query(file.stem) == query_stem_normalized:
            return file

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
    text_files = get_input_files_by_extension(TEXT_EXTENSIONS)

    if "pdf" in lower_prompt and len(pdf_files) == 1:
        return pdf_files[0]

    if ("text file" in lower_prompt or "txt file" in lower_prompt) and len(text_files) == 1:
        return text_files[0]

    return None


def read_text_file(path: str | Path) -> str:
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


def read_pdf_file(path: str | Path) -> str:
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
                extracted_pages.append(f"--- Page {page_number} ---\n{page_text.strip()}")

        if not extracted_pages:
            return (
                f"Warning: No extractable text was found in '{file_path.name}'. "
                "The PDF may contain scanned images instead of selectable text."
            )

        return "\n\n".join(extracted_pages)

    except Exception as e:
        return f"Error reading PDF file '{file_path.name}': {e}"


def read_file(path: str | Path) -> str:
    """
    Read a file based on its extension.
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{path}' is not a file."

    suffix = file_path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        return read_text_file(file_path)

    if suffix == ".pdf":
        return read_pdf_file(file_path)

    return f"Error: Unsupported file type '{suffix or 'unknown'}'."

def read_multiple_files(filenames: list[str]) -> str:
    """
    Read multiple files and return their contents clearly labelled.
    """
    results = []
    not_found = []

    for name in filenames:
        path = find_file_in_input(name.strip())

        if path is not None:
            content = read_file(path)
            results.append(f"=== {path.name} ===\n{content}")
        else:
            not_found.append(name.strip())

    if not_found:
        results.append(f"Could not find: {', '.join(not_found)}")

    return "\n\n".join(results) if results else "None of the specified files could be found."


def view_guarded_file(path: str | Path, filesystem_guard) -> str:
    """
    Read a file only if it is inside an approved directory.
    """
    safe = filesystem_guard.safe_path(path)

    if safe is None:
        return f"Access denied. '{path}' is not within an approved directory."

    return read_file(safe)


def create_guarded_file(action_input: str, filesystem_guard) -> str:
    """
    Create a file only if it is inside an approved directory.
    Expected format:
        filepath::content
    """
    pair = _split_action_pair(action_input, "create_file")

    if isinstance(pair, str):
        return pair

    filepath, content = pair

    safe = filesystem_guard.safe_path(filepath)

    if safe is None:
        return f"Access denied. '{filepath}' is not within an approved directory."

    if safe.exists():
        return f"Error: File already exists: {safe}"

    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")

        return f"File created: {safe}"

    except Exception as e:
        return f"Error creating file: {e}"


def append_guarded_file(action_input: str, filesystem_guard) -> str:
    """
    Append content to a file only if it is inside an approved directory.
    Expected format:
        filepath::content
    """
    pair = _split_action_pair(action_input, "append_file")

    if isinstance(pair, str):
        return pair

    filepath, content = pair

    safe = filesystem_guard.safe_path(filepath)

    if safe is None:
        return f"Access denied. '{filepath}' is not within an approved directory."

    if not safe.exists():
        return f"Error: File does not exist: {safe}"

    if not safe.is_file():
        return f"Error: Path is not a file: {safe}"

    try:
        with safe.open("a", encoding="utf-8") as file:
            file.write(content)

        return f"Content appended to: {safe}"

    except Exception as e:
        return f"Error appending to file: {e}"


def delete_guarded_file(path: str | Path, filesystem_guard) -> str:
    """
    Delete a file only if it is inside an approved directory.
    """
    safe = filesystem_guard.safe_path(path)

    if safe is None:
        return f"Access denied. '{path}' is not within an approved directory."

    if not safe.exists():
        return f"File not found: {path}"

    if not safe.is_file():
        return f"Error: '{path}' is not a file."

    try:
        safe.unlink()
        return f"File deleted: {safe}"
    except Exception as e:
        return f"Error deleting file: {e}"


def prepare_guarded_edit_file(action_input: str, filesystem_guard) -> str:
    """
    Prepare a file for editing only if it is inside an approved directory.
    Expected format:
        filepath::instruction
    """
    pair = _split_action_pair(action_input, "edit_file")

    if isinstance(pair, str):
        return pair.replace("filepath::content", "filepath::instruction")

    filepath, instruction = pair

    safe = filesystem_guard.safe_path(filepath)

    if safe is None:
        return f"Access denied. '{filepath}' is not within an approved directory."

    if not safe.exists():
        return f"File not found: {filepath}"

    if not safe.is_file():
        return f"Error: '{filepath}' is not a file."

    try:
        existing_content = safe.read_text(encoding="utf-8")
        return f"EDIT_READY::{safe}::{instruction}::{existing_content}"

    except Exception as e:
        return f"Error reading file for editing: {e}"
    
    
def write_guarded_file(action_input: str, filesystem_guard=None) -> str:
    """
    Overwrite an existing file only if it is inside an approved directory.
    Expected format:
        filepath::content
    """
    if filesystem_guard is None:
        return "Access denied: no filesystem guard available."

    pair = _split_action_pair(action_input, "write_file")

    if isinstance(pair, str):
        return pair

    file_path, content = pair

    safe_path = filesystem_guard.safe_path(file_path)

    if safe_path is None:
        return f"Access denied: {file_path}"

    if not safe_path.exists():
        return f"Error: File does not exist: {safe_path}"

    if not safe_path.is_file():
        return f"Error: Path is not a file: {safe_path}"

    try:
        safe_path.write_text(content, encoding="utf-8")
        return f"File updated: {safe_path}"

    except Exception as e:
        return f"Error writing file: {e}"

def find_guarded_file(file_name: str, filesystem_guard=None) -> str:
    """
    Search for a file or directory inside approved directories.
    """
    if filesystem_guard is None:
        return "Access denied: no filesystem guard available."

    approved_dirs = filesystem_guard.list_approved()

    if not approved_dirs:
        return "No approved directories available."

    query = file_name.strip().strip("\"'")

    if not query:
        return "Error: No file name provided."

    matches = []

    for approved_dir in approved_dirs:
        root = Path(approved_dir)

        if not root.exists() or not root.is_dir():
            continue

        direct_candidate = root / query

        if direct_candidate.exists():
            matches.append(direct_candidate)

        name = Path(query).name

        if name:
            matches.extend(_safe_rglob_by_name(root, name))

    unique_matches = []

    for match in matches:
        resolved_match = match.resolve()

        if resolved_match not in unique_matches:
            unique_matches.append(resolved_match)

    if not unique_matches:
        return f"No matching file found for: {query}"

    if len(unique_matches) == 1:
        return f"Found file: {unique_matches[0]}"

    return "Found multiple files:\n" + "\n".join(str(match) for match in unique_matches)

def run_python_file(path: str | Path, filesystem_guard=None, timeout_seconds: int = 10) -> str:
    """
    Run an approved Python file and return stdout/stderr.

    This is intentionally restricted:
    - only approved paths
    - only .py files
    - timeout enforced
    """
    if filesystem_guard is None:
        return "Access denied: no filesystem guard available."

    safe = filesystem_guard.safe_path(path)

    if safe is None:
        return f"Access denied. '{path}' is not within an approved directory."

    if not safe.exists():
        return f"Error: Python file does not exist: {safe}"

    if not safe.is_file():
        return f"Error: '{safe}' is not a file."

    if safe.suffix.lower() != ".py":
        return f"Error: run_python_file only supports Python files, got '{safe.suffix or 'unknown'}'."

    try:
        result = subprocess.run(
            [sys.executable, str(safe)],
            cwd=str(safe.parent),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        output = (
            f"Return code: {result.returncode}\n"
            f"STDOUT:\n{stdout if stdout else '(empty)'}\n\n"
            f"STDERR:\n{stderr if stderr else '(empty)'}"
        )

        if result.returncode != 0:
            return f"Error: Python file failed: {safe}\n\n{output}"

        return f"Python file ran successfully: {safe}\n\n{output}"

    except subprocess.TimeoutExpired:
        return f"Error: Python file timed out after {timeout_seconds} seconds: {safe}"

    except Exception as e:
        return f"Error running Python file '{safe}': {e}"