import json
from pathlib import Path

from backend_factory import build_backend
from reasoning_settings import ReasoningSettings
from config import DEFAULT_PLANNING_MODEL, DEFAULT_REASONING_MODEL, BABYCLAW_DEBUG


def print_restored_accessible_paths(filesystem_guard) -> None:
    """Print restored approved directories for the terminal UI."""
    approved_paths = filesystem_guard.list_approved()

    if not approved_paths:
        return

    print("\nRestored saved accessible paths:")

    for approved_path in approved_paths:
        active_marker = ""

        if approved_path == filesystem_guard.get_active_directory():
            active_marker = " (active)"

        print(f"- {approved_path}{active_marker}")

    print()


def main() -> None:
    """Run the terminal REPL: build the backend, restore state, and loop on user input."""
    planning_model = DEFAULT_PLANNING_MODEL
    reasoning_model = DEFAULT_REASONING_MODEL
    debug = BABYCLAW_DEBUG

    reasoning_settings = ReasoningSettings(mode="medium")

    backend = build_backend(
        reasoning_settings=reasoning_settings,
        planning_model=planning_model,
        reasoning_model=reasoning_model,
        debug=debug,
    )

    filesystem_guard = backend["filesystem_guard"]
    transaction_manager = backend["transaction_manager"]
    memory = backend["memory"]
    coordinator = backend["coordinator"]

    print_restored_accessible_paths(filesystem_guard)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        if prompt.lower().startswith("reasoning "):
            requested_mode = prompt[len("reasoning "):].strip().lower()

            if requested_mode not in {"low", "medium", "high"}:
                print("\nBaby Claw: Please choose low, medium, or high.\n")
            else:
                reasoning_settings.mode = requested_mode
                print(f"\nBaby Claw: Reasoning mode set to {reasoning_settings.mode}.\n")

            continue

        if prompt.lower() == "undo":
            result = transaction_manager.rollback_last_snapshot()
            print(f"\nBaby Claw: {result}\n")
            continue

        if prompt.lower() in {"list access", "list approved", "list approved directories"}:
            approved_paths = filesystem_guard.list_approved()

            if not approved_paths:
                print("\nBaby Claw: No directories are currently approved.\n")
            else:
                print("\nBaby Claw: Approved directories:")

                for approved_path in approved_paths:
                    print(f"- {approved_path}")

                print()

            continue

        if prompt.lower() in {"active directory", "active folder", "pwd"}:
            active_directory = filesystem_guard.get_active_directory()

            if active_directory:
                print(f"\nBaby Claw: Active directory is:\n{active_directory}\n")
            else:
                print("\nBaby Claw: No active directory is set.\n")

            continue

        if prompt.lower() == "trace":
            if coordinator.last_trace:
                print("\nBaby Claw trace:")
                print(json.dumps(coordinator.last_trace, indent=2, default=str))
                print()
            else:
                print("\nBaby Claw: No trace available yet.\n")
            continue

        if prompt.lower().startswith("grant access "):
            raw_path = prompt[len("grant access "):].strip().strip("\"'")
            print(filesystem_guard.request_approval(raw_path))

            confirm = input("You: ").strip().upper()

            if confirm == "YES":
                if filesystem_guard.approve(raw_path):
                    resolved_path = Path(raw_path).expanduser().resolve()
                    memory_result = memory.save_accessible_path(str(resolved_path))
                    active_result = memory.save_active_accessible_path(str(resolved_path))

                    print(f"\nBaby Claw: Access granted to {resolved_path}")
                    print(memory_result)
                    print(active_result + "\n")
                else:
                    resolved_path = Path(raw_path).expanduser().resolve()

                    if not resolved_path.exists():
                        print(f"\nBaby Claw: Path does not exist: {resolved_path}\n")
                    elif not resolved_path.is_dir():
                        print(f"\nBaby Claw: Path is not a directory: {resolved_path}\n")
                    else:
                        print(f"\nBaby Claw: Could not approve that path: {resolved_path}\n")
            else:
                print("\nBaby Claw: Access denied.\n")

            continue

        if prompt.lower().startswith("revoke access "):
            raw_path = prompt[len("revoke access "):].strip().strip("\"'")

            live_revoked = filesystem_guard.revoke(raw_path)
            memory_result = memory.revoke_accessible_path(raw_path)

            if live_revoked:
                active_directory = filesystem_guard.get_active_directory()

                if active_directory:
                    active_result = memory.save_active_accessible_path(active_directory)
                else:
                    active_result = memory.clear_active_accessible_path()

                print(f"\nBaby Claw: Access revoked for {Path(raw_path).expanduser().resolve()}")
                print(memory_result)
                print(active_result + "\n")
            else:
                print(f"\nBaby Claw: That path was not currently approved.")
                print(memory_result + "\n")

            continue

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()
