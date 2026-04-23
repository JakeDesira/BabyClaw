import shutil
from pathlib import Path
import tools


class ExecutorAgent:
    def __init__(self, memory=None, filesystem_guard=None):
        self.memory = memory
        self.filesystem_guard = filesystem_guard


    def handle(self, action: str, action_input: str = "", original_prompt: str = "") -> str:
        if action == "get_current_time":
            return f"The current time is {tools.get_current_time()}."

        if action == "list_input_files":
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."
            return "Available files:\n" + "\n".join(files)

        if action == "read_file":
            lower_prompt = original_prompt.lower().strip()

            # 1. Explicit filename first
            if action_input and action_input != "NONE":
                file_path = tools.find_file_in_input(action_input)
                #
                print(f"[EXECUTOR DEBUG] Explicit file match: {file_path}")
                if file_path is not None:
                    file_content = tools.read_file(file_path)

                    if (
                        self.memory is not None
                        and not file_content.startswith("Error:")
                        and not file_content.startswith("Warning:")
                    ):
                        self.memory.set_last_active_file(file_path.name, file_content)

                    return file_content

            # 2. Follow-up references to currently active file
            if self.memory is not None:
                last_file_name = self.memory.get_last_active_file_name()
                last_file_content = self.memory.get_last_active_file_content()
                #
                print(f"[EXECUTOR DEBUG] Active file candidate: {last_file_name}")

                current_file_phrases = {
                    "read it",
                    "read the file",
                    "open it",
                    "open the file",
                    "show it",
                    "show the file",
                    "process it",
                    "summarise it",
                    "summarize it",
                    "explain it",
                    "what does it say",
                    "what does the file say",
                }

                if lower_prompt in current_file_phrases and last_file_name and last_file_content:
                    print(f"[EXECUTOR DEBUG] Actually reusing active file: {last_file_name}")
                    return last_file_content

            # 3. "Other file" support
            if self.memory is not None:
                previous_file_name = self.memory.get_previous_active_file_name()
                previous_file_content = self.memory.get_previous_active_file_content()

                if "other file" in lower_prompt and previous_file_name and previous_file_content:
                    #
                    print(f"[EXECUTOR DEBUG] Switching to previous file: {previous_file_name}")
                    # Promote previous to active when user explicitly switches to it
                    self.memory.set_last_active_file(previous_file_name, previous_file_content)
                    return previous_file_content

            # 4. Deterministic obvious-file fallback
            obvious_file = tools.get_single_obvious_file(original_prompt)
            if obvious_file is not None:
                #
                print(f"[EXECUTOR DEBUG] Obvious file fallback: {obvious_file}")
                file_content = tools.read_file(obvious_file)

                if (
                    self.memory is not None
                    and not file_content.startswith("Error:")
                    and not file_content.startswith("Warning:")
                ):
                    self.memory.set_last_active_file(obvious_file.name, file_content)

                return file_content

            # 5. Final clarification
            #
            print("[EXECUTOR DEBUG] Could not resolve file, asking user to specify")
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."

            return "Please specify which file to read. Available files:\n" + "\n".join(files)
        
        if action == "read_multiple_files":
            filenames = [f.strip() for f in action_input.split(",") if f.strip() and f.strip() != "NONE"]
            
            if not filenames:
                return "No filenames provided for read_multiple_files."

            results = []
            last_found_path = None

            for name in filenames:
                path = tools.find_file_in_input(name)
                print(f"[EXECUTOR DEBUG] Multi-file match for '{name}': {path}")
                if path is not None:
                    content = tools.read_file(path)
                    results.append(f"=== {path.name} ===\n{content}")
                    if (
                        self.memory is not None
                        and not content.startswith("Error:")
                        and not content.startswith("Warning:")
                    ):
                        self.memory.set_last_active_file(path.name, content)
                    last_found_path = path
                else:
                    results.append(f"=== {name} ===\nError: File not found.")

            return "\n\n".join(results) if results else "None of the specified files could be found."

        if action == "list_directory":
            safe = self.filesystem_guard.safe_path(action_input)
            if safe is None:
                return f"Access denied. '{action_input}' is not within an approved directory."
            if not safe.is_dir():
                return f"'{action_input}' is not a directory."
            files = sorted(safe.iterdir())
            if not files:
                return "Directory is empty."
            return "Contents:\n" + "\n".join(
                f"{'[DIR]' if f.is_dir() else '[FILE]'} {f.name}" for f in files
            )

        if action == "view_file":
            safe = self.filesystem_guard.safe_path(action_input)
            if safe is None:
                return f"Access denied. '{action_input}' is not within an approved directory."
            return tools.read_file(safe)

        if action == "create_file":
            # action_input format: "filepath::content"
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return "Error: create_file requires 'filepath::content' format."
            filepath, content = parts
            safe = self.filesystem_guard.safe_path(filepath)
            if safe is None:
                return f"Access denied. '{filepath}' is not within an approved directory."
            try:
                safe.parent.mkdir(parents=True, exist_ok=True)
                safe.write_text(content, encoding="utf-8")
                return f"File created: {safe}"
            except Exception as e:
                return f"Error creating file: {e}"

        if action == "append_file":
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return "Error: append_file requires 'filepath::content' format."
            filepath, content = parts
            safe = self.filesystem_guard.safe_path(filepath)
            if safe is None:
                return f"Access denied. '{filepath}' is not within an approved directory."
            try:
                with open(safe, "a", encoding="utf-8") as f:
                    f.write(content)
                return f"Content appended to: {safe}"
            except Exception as e:
                return f"Error appending to file: {e}"

        if action == "delete_file":
            safe = self.filesystem_guard.safe_path(action_input)
            if safe is None:
                return f"Access denied. '{action_input}' is not within an approved directory."
            if not safe.exists():
                return f"File not found: {action_input}"
            try:
                safe.unlink()
                return f"File deleted: {safe}"
            except Exception as e:
                return f"Error deleting file: {e}"
            
        if action == "edit_file":
            # action_input format: "filepath::improvement_instruction"
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return "Error: edit_file requires 'filepath::instruction' format."
            filepath, instruction = parts
            safe = self.filesystem_guard.safe_path(filepath)
            if safe is None:
                return f"Access denied. '{filepath}' is not within an approved directory."
            try:
                existing_content = safe.read_text(encoding="utf-8")
                return f"EDIT_READY::{filepath}::{instruction}::{existing_content}"
            except Exception as e:
                return f"Error reading file for editing: {e}"
            
        if action == "create_directory":
            safe = self.filesystem_guard.safe_path(action_input)
            if safe is None:
                return f"Access denied. '{action_input}' is not within an approved directory."

            try:
                safe.mkdir(parents=True, exist_ok=True)
                return f"Directory created: {safe}"
            except Exception as e:
                    return f"Error creating directory: {e}"

        if action == "move_path":
            parts = action_input.split("::", 1)

            if len(parts) != 2:
                if ":" in action_input:
                    source_raw, destination_raw = action_input.split(":", 1)
                else:
                    return "Error: move_path requires 'source::destination' format."
            else:
                source_raw, destination_raw = parts

            source_raw = source_raw.strip()
            destination_raw = destination_raw.strip()

            source = self.filesystem_guard.safe_path(source_raw)
            destination = self.filesystem_guard.safe_path(destination_raw)

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

        if action == "rename_path":
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return "Error: rename_path requires 'source::new_name' format."

            source_raw, new_name = parts
            source = self.filesystem_guard.safe_path(source_raw)

            if source is None:
                return f"Access denied. '{source_raw}' is not within an approved directory."

            if not source.exists():
                return f"Path not found: {source}"

            destination = source.with_name(new_name.strip())

            if not self.filesystem_guard.is_approved(destination):
                return f"Access denied. '{destination}' is not within an approved directory."

            try:
                source.rename(destination)
                return f"Renamed: {source} -> {destination}"
            except Exception as e:
                return f"Error renaming path: {e}"
            
        return f"Executor could not find a supported action for '{action}'."
