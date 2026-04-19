from agents.coordinator import CoordinatorAgent


def main() -> None:
    coordinator = CoordinatorAgent()

    while True:
        prompt = input("You: ").strip()

        if prompt.lower() in {"exit", "quit"}:
            print("Exiting Baby Claw.")
            break

        reply = coordinator.handle(prompt)
        print(f"\nBaby Claw: {reply}\n")


if __name__ == "__main__":
    main()