from pathlib import Path
import os

from filesystem_guard import FilesystemGuard
import agents
from reasoning_settings import ReasoningSettings
from paths import MEMORY_DB_PATH
from config import DEFAULT_PLANNING_MODEL, DEFAULT_REASONING_MODEL, BABYCLAW_DEBUG

def build_backend(reasoning_settings: ReasoningSettings, planning_model: str, reasoning_model: str, debug: bool):
    filesystem_guard = FilesystemGuard()

    transaction_manager = agents.TransactionManager(
        filesystem_guard=filesystem_guard,
        snapshot_root=Path.home() / ".babyclaw_snapshots",
    )

    execution_verifier = agents.ExecutionVerifier(
        filesystem_guard=filesystem_guard,
        debug=debug,
    )

    memory_store = agents.SQLiteMemoryStore(MEMORY_DB_PATH)
    memory = agents.MemoryAgent(memory_store=memory_store)

    saved_paths = memory.get_saved_accessible_path_values()

    for saved_path in saved_paths:
        filesystem_guard.approve(saved_path)

    saved_active_path = memory.get_active_accessible_path()

    if saved_active_path:
        filesystem_guard.set_active_directory(saved_active_path)

    if saved_paths:
        print("\nRestored saved accessible paths:")

        for approved_path in filesystem_guard.list_approved():
            active_marker = ""

            if approved_path == filesystem_guard.get_active_directory():
                active_marker = " (active)"

            print(f"- {approved_path}{active_marker}")

        print()

    executor = agents.ExecutorAgent(
        memory=memory,
        filesystem_guard=filesystem_guard,
        debug=debug,
    )

    response_generator = agents.ResponseGenerator(
        memory=memory,
        reasoning_model=reasoning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    plan_executor = agents.PlanExecutor(
        memory=memory,
        executor=executor,
        filesystem_guard=filesystem_guard,
        response_generator=response_generator,
        execution_verifier=execution_verifier,
        transaction_manager=transaction_manager,
        debug=debug,
    )

    reviewer = agents.ReviewerAgent(
        model=reasoning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    planner = agents.PlannerAgent(
        memory=memory,
        planning_model=planning_model,
        filesystem_guard=filesystem_guard,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    memory_writer = agents.MemoryWriter(
        model=planning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    memory_router = agents.MemoryRouter(
        model=planning_model,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    coordinator = agents.CoordinatorAgent(
        planner=planner,
        plan_executor=plan_executor,
        response_generator=response_generator,
        reviewer=reviewer,
        memory=memory,
        model=planning_model,
        memory_router=memory_router,
        memory_writer=memory_writer,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    return {
        "filesystem_guard": filesystem_guard,
        "transaction_manager": transaction_manager,
        "memory": memory,
        "coordinator": coordinator,
    }


def main() -> None:
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
            print("\nBaby Claw trace:")
            print(coordinator.last_trace if coordinator.last_trace else "No trace available yet.")
            print()
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
                    print("\nBaby Claw: Could not approve that path. Make sure it exists and is a directory.\n")
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

            continue

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()