from agents.coordinator import CoordinatorAgent
from agents.planner import PlannerAgent
from agents.memory import MemoryAgent


def main() -> None:
    memory = MemoryAgent()
    planner = PlannerAgent(memory=memory)
    coordinator = CoordinatorAgent(planner=planner, memory=memory)

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()