WRITE_ACTIONS = frozenset(
    {
        "create_file",
        "write_file",
        "append_file",
        "delete_file",
        "delete_directory",
        "edit_file",
        "create_directory",
        "move_path",
        "move_directory_contents",
        "copy_path",
        "rename_path",
    }
)

CODE_MUTATING_ACTIONS = frozenset(
    {
        "create_file",
        "write_file",
        "append_file",
        "edit_file",
    }
)

INSPECTION_ACTIONS = frozenset(
    {
        "list_directory",
        "view_file",
        "find_file",
    }
)

PLANNER_INSPECTION_ACTIONS = INSPECTION_ACTIONS | frozenset({"read_file"})

EXECUTOR_ACTIONS = frozenset(
    {
        "get_current_time",
        "list_input_files",
        "read_file",
        "read_multiple_files",
        "list_directory",
        "view_file",
        "find_file",
        "run_python_file",
    }
) | WRITE_ACTIONS

ITERATIVE_ACTIONS = frozenset(
    {
        "NONE",
        "list_directory",
        "view_file",
        "find_file",
        "run_python_file",
    }
) | WRITE_ACTIONS

SKIP_SEARCH_DIRS = frozenset(
    {
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
)
