from pathlib import Path

from filesystem_guard import FilesystemGuard
import agents

def main() -> None:
    planning_model = "gemma4"
    reasoning_model = "gpt-oss:20b"
    debug = True

    filesystem_guard = FilesystemGuard()

    transaction_manager = agents.TransactionManager(filesystem_guard=filesystem_guard, snapshot_root=Path.home() / ".babyclaw_snapshots")
    execution_verifier = agents.ExecutionVerifier(filesystem_guard=filesystem_guard, debug=debug)

    memory_db_path = Path("src/agents/memory/babyclaw_memory.db")
    memory_store = agents.SQLiteMemoryStore(memory_db_path)
    memory = agents.MemoryAgent(memory_store=memory_store)
    memory_writer = agents.MemoryWriter(model=planning_model,debug=debug)

    saved_paths = memory.get_saved_accessible_path_values()

    for saved_path in saved_paths:
        filesystem_guard.approve(saved_path)

    if saved_paths:
        print("\nRestored saved accessible paths:")

        for approved_path in filesystem_guard.list_approved():
            print(f"- {approved_path}")

        print()

    executor = agents.ExecutorAgent(memory=memory, filesystem_guard=filesystem_guard, debug=debug)

    response_generator = agents.ResponseGenerator(memory=memory, reasoning_model=reasoning_model, debug=debug)
    plan_executor = agents.PlanExecutor(memory=memory, executor=executor, filesystem_guard=filesystem_guard, response_generator=response_generator, execution_verifier=execution_verifier, transaction_manager=transaction_manager, debug=debug)

    reviewer = agents.ReviewerAgent(model=reasoning_model, debug=debug)

    planner = agents.PlannerAgent(memory=memory, planning_model=planning_model, filesystem_guard=filesystem_guard, debug=debug)

    memory_router = agents.MemoryRouter(model=planning_model, debug=debug)
    
    coordinator = agents.CoordinatorAgent(planner=planner, plan_executor=plan_executor, response_generator=response_generator, reviewer=reviewer, memory=memory, model=planning_model, memory_router=memory_router, memory_writer=memory_writer, debug=debug)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break
        
        if prompt.lower() == "undo":
            result = transaction_manager.rollback_last_snapshot()
            print(f"\nBaby Claw: {result}\n")
            continue

        if prompt.lower().startswith("grant access "):
            raw_path = prompt[len("grant access "):].strip().strip("\"'")
            print(filesystem_guard.request_approval(raw_path))

            confirm = input("You: ").strip().upper()

            if confirm == "YES":
                if filesystem_guard.approve(raw_path):
                    resolved_path = Path(raw_path).expanduser().resolve()
                    memory_result = memory.save_accessible_path(str(resolved_path))

                    print(f"\nBaby Claw: Access granted to {resolved_path}")
                    print(memory_result + "\n")
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
                print(f"\nBaby Claw: Access revoked for {Path(raw_path).expanduser().resolve()}")
                print(memory_result + "\n")
            else:
                print("\nBaby Claw: That path was not currently approved.")
                print(memory_result + "\n")

            continue

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()