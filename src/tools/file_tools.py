from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
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


def find_file_in_input(filename: str) -> Path | None:
    """
    Find a file in the input directory by exact name first,
    then by case-insensitive match. 
    """
    if not INPUT_DIR.exists():
        return None

    exact_match = INPUT_DIR / filename
    if exact_match.exists() and exact_match.is_file():
        return exact_match

    lower_filename = filename.lower()
    for file in INPUT_DIR.iterdir():
        if file.is_file() and file.name.lower() == lower_filename:
            return file

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
    Read a PDF file and return its text content.
    NOTE: This is a placeholder implementation.
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{file_path}' does not exist."
    
    if not file_path.is_file():
        return f"Error: '{file_path}' is not a file."
    
    return (
        f"PDF reading for '{file_path.name}' has not been implemented yet. "
        "This will be added later."
    )


def read_file(path: str) -> str:
    """
    Read a file based on its extension,
    Currently supports text-like files directly and provides a placeholder for PDFs.
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
    elif suffix == ".pdf":
        return read_pdf_file(file_path)
    
    return f"Error: Unsupported file type '{suffix or 'unknown'}' is not supported yet."


def list_directory(path: str = ".") -> str:
    """
    Return the contents of a directory as a newline-separated string.
    This is used by the Executor Agent to inspect safe working directories,
    such as the input folder, and report available files back to the user.
    """
    dir_path = Path(path)

    if not dir_path.exists():
        return f"Error: Directory '{path}' does not exist."

    if not dir_path.is_dir():
        return f"Error: '{path}' is not a directory."

    try:
        items = sorted(item.name for item in dir_path.iterdir())
        return "\n".join(items) if items else "(empty directory)"
    except Exception as e:
        return f"Error listing directory '{path}': {e}"