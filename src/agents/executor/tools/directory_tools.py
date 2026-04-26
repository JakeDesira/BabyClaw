from pathlib import Path
import shutil


def list_directory(path: str | Path, filesystem_guard) -> str:
    safe = filesystem_guard.safe_path(path)

    if safe is None:
        return f"Access denied. '{path}' is not within an approved directory."

    if not safe.is_dir():
        return f"'{path}' is not a directory."

    items = sorted(safe.iterdir(), key=lambda item: item.name.lower())

    if not items:
        return "Directory is empty."

    return "Contents:\n" + "\n".join(
        f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}"
        for item in items
    )


def create_directory(path: str | Path, filesystem_guard) -> str:
    safe = filesystem_guard.safe_path(path)

    if safe is None:
        return f"Access denied. '{path}' is not within an approved directory."

    try:
        safe.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {safe}"
    except Exception as e:
        return f"Error creating directory: {e}"


def move_path(action_input: str, filesystem_guard) -> str:
    parts = action_input.split("::", 1)

    if len(parts) != 2:
        return "Error: move_path requires 'source::destination' format."

    source_raw, destination_raw = parts
    destination_raw = destination_raw.strip()

    source = filesystem_guard.safe_path(source_raw)
    destination = filesystem_guard.safe_path(destination_raw)

    if source is None:
        return f"Access denied. '{source_raw}' is not within an approved directory."

    if destination is None:
        return f"Access denied. '{destination_raw}' is not within an approved directory."

    if not source.exists():
        return f"Source not found: {source}"

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return f"Moved: {source} -> {destination}"
    except Exception as e:
        return f"Error moving path: {e}"


def rename_path(action_input: str, filesystem_guard) -> str:
    parts = action_input.split("::", 1)

    if len(parts) != 2:
        return "Error: rename_path requires 'source::new_name' format."

    source_raw, new_name = parts
    source_raw = source_raw.strip()
    new_name = new_name.strip()

    if not new_name:
        return "Error: rename_path requires a new name."

    if "/" in new_name or "\\" in new_name:
        return "Error: rename_path only accepts a new name, not a full path."

    source = filesystem_guard.safe_path(source_raw)

    if source is None:
        return f"Access denied. '{source_raw}' is not within an approved directory."

    if not source.exists():
        return f"Path not found: {source}"

    destination = source.with_name(new_name)

    if not filesystem_guard.is_approved(destination):
        return f"Access denied. '{destination}' is not within an approved directory."

    try:
        source.rename(destination)
        return f"Renamed: {source} -> {destination}"
    except Exception as e:
        return f"Error renaming path: {e}"
    

def copy_path(action_input: str, filesystem_guard) -> str:
    parts = action_input.split("::", 1)

    if len(parts) != 2:
        return "Error: copy_path requires 'source::destination' format."

    source_raw, destination_raw = parts
    source_raw = source_raw.strip()
    destination_raw = destination_raw.strip()

    source = filesystem_guard.safe_path(source_raw)
    destination = filesystem_guard.safe_path(destination_raw)

    if source is None:
        return f"Access denied. '{source_raw}' is not within an approved directory."

    if destination is None:
        return f"Access denied. '{destination_raw}' is not within an approved directory."

    if not source.exists():
        return f"Source not found: {source}"

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)

        return f"Copied: {source} -> {destination}"
    except Exception as e:
        return f"Error copying path: {e}"
    
from pathlib import Path
import shutil


def move_directory_contents(action_input: str, filesystem_guard) -> str:
    parts = action_input.split("::", 1)

    if len(parts) != 2:
        return "Error: move_directory_contents requires 'source_directory::destination_directory' format."

    source_raw, destination_raw = parts
    source_raw = source_raw.strip()
    destination_raw = destination_raw.strip()

    source = filesystem_guard.safe_path(source_raw)
    destination = filesystem_guard.safe_path(destination_raw)

    if source is None:
        return f"Access denied. '{source_raw}' is not within an approved directory."

    if destination is None:
        return f"Access denied. '{destination_raw}' is not within an approved directory."

    if not source.exists() or not source.is_dir():
        return f"'{source}' is not a directory."

    try:
        destination.mkdir(parents=True, exist_ok=True)

        source = source.resolve()
        destination = destination.resolve()

        moved_items = []
        skipped_items = []

        for item in source.iterdir():
            item = item.resolve()

            # Never move the destination folder into itself.
            if item == destination:
                skipped_items.append(item.name)
                continue

            # If destination is inside source, skip anything already inside destination.
            try:
                item.relative_to(destination)
                skipped_items.append(item.name)
                continue
            except ValueError:
                pass

            target = destination / item.name

            if target.exists():
                skipped_items.append(f"{item.name} already exists in destination")
                continue

            shutil.move(str(item), str(target))
            moved_items.append(item.name)

        if not moved_items:
            return (
                f"No items were moved from '{source}' to '{destination}'.\n"
                f"Skipped: {', '.join(skipped_items) if skipped_items else 'none'}"
            )

        result = (
            f"Moved {len(moved_items)} item(s) from '{source}' to '{destination}':\n"
            + "\n".join(f"- {name}" for name in moved_items)
        )

        if skipped_items:
            result += "\n\nSkipped:\n" + "\n".join(f"- {name}" for name in skipped_items)

        return result

    except Exception as e:
        return f"Error moving directory contents: {e}"