# Baby Claw

Baby Claw is a lightweight local multi-agent AI assistant built in Python and designed to run through Ollama. It was developed as part of a university assignment with the goal of creating a clear and minimal architecture rather than a feature-heavy system.

The system is based on a small set of cooperating agents with clearly separated responsibilities:

* **Coordinator Agent** – receives the user prompt, decides whether the request is simple or requires planning, and returns the final response
* **Planner Agent** – breaks complex requests into subtasks and decides whether memory or execution is required
* **Memory Agent** – manages short-term and long-term memory
* **Executor Agent** – performs approved actions such as file operations or safe commands
* **Reviewer Agent** – checks the final result for correctness and coherence

The language model is run locally through **Ollama**, using a model selected for a balance between reasoning quality and practical speed.

---

## Project Goal

The purpose of Baby Claw is to improve on existing agent systems by keeping the architecture:

* local-first
* easier to understand
* safer in terms of execution
* more modular through explicit agent roles

Instead of placing planning, memory, execution, and review inside one large loop, Baby Claw separates them into specialised components.

---

## Current Development Setup

During development, I used two different ways of running the model:

### 1. Standard local setup

The default and intended setup is that the Python code and Ollama both run on the **same machine**. In this case, the Ollama client connects to:

```text
http://localhost:11434
```

This is the setup that other users, such as the tutor, are expected to use.

### 2. Optional remote development setup

For convenience, I also added optional support for running the Python client on my **Mac** while using the model hosted on my **desktop PC**. This was done mainly for personal development and testing, since my desktop machine has stronger hardware for local inference.

This remote setup uses:

* **Tailscale** for private connectivity between devices
* an environment variable to point the Mac client to the PC-hosted Ollama instance

This remote option is not required to run the project. The system still works normally on a single local machine.

---

## Ollama Setup

First, Ollama was installed on the machine hosting the model.

A local model was then downloaded and tested through Ollama. The project was designed to support lightweight local models, and several models were tested during development in order to find a good balance between reasoning quality and speed.

The Python side communicates with Ollama through a small wrapper class in `ollama_client.py`.

By default, the client connects to:

```text
http://localhost:11434
```

This means that if Ollama is running locally on the same machine, no additional setup is required.

---

## Optional Remote Setup with Tailscale

This section describes the additional setup used for my personal workflow.

### Why this was added

My desktop PC provides stronger hardware for local inference, while my Mac is more convenient for coding and writing. To make development easier, I configured the project so that the Mac could send requests to Ollama running on the desktop PC.

### What was used

* **Tailscale** was used to create a private connection between the Mac and the PC
* Ollama was configured on the PC so that it could be reached through the Tailscale network
* the Mac was configured to use the PC’s Tailscale address instead of localhost

### Important note

This remote setup is optional and mainly intended for development convenience. It is **not required** for normal use of the project. If someone else clones the repository and wants to run Baby Claw normally, they can simply run Ollama locally and keep the default localhost configuration.

---

## Host Configuration

The Ollama host is configurable through an environment variable.

The client code uses:

```python
host = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
```

This means:

* if no environment variable is set, the project uses **localhost**
* if `OLLAMA_HOST_URL` is set, the project uses that address instead

This was done so that:

* a normal local user can run the project without editing the code
* I can optionally point the client on my Mac to the Ollama instance running on my PC

### Why this approach was chosen

Because my project files are synced through Google Drive, using a machine-specific `.env` file inside the project folder would have caused conflicts between the Mac and the PC. For that reason, I used a shell-level environment variable on the Mac instead of relying on a synced `.env` file.

---

## macOS Shell Configuration

On my Mac, I configured the environment variable in `~/.zshrc` so that the project would automatically connect to the PC-hosted Ollama instance.

The line added was:

```bash
export OLLAMA_HOST_URL="http://<tailscale-ip>:11434"
```

This allows the same codebase to behave differently depending on the machine:

* on the **PC**, the system uses `localhost`
* on the **Mac**, the system uses the Tailscale address of the PC

This setup is private to my own machines and is not required for others using the repository.

---

## Security Note

The public repository does **not** include my private Tailscale address.

The project is written so that remote connectivity is optional and configurable outside the code. This keeps the repository cleaner and avoids exposing personal network details.

Anyone using the repository normally should run the system locally with:

```text
http://localhost:11434
```

---

## Project Structure

```text
src/
├── agents/
│   ├── __init__.py
│   ├── coordinator.py
│   ├── planner.py
│   ├── memory.py
│   ├── executor.py
│   └── reviewer.py
├── main.py
├── memory_store.py
└── ollama_client.py
```

### Main files

* `main.py` – entry point of the system
* `ollama_client.py` – wrapper for communication with Ollama
* `memory_store.py` – memory storage logic
* `agents/coordinator.py` – Coordinator Agent
* `agents/planner.py` – Planner Agent
* `agents/memory.py` – Memory Agent
* `agents/executor.py` – Executor Agent
* `agents/reviewer.py` – Reviewer Agent

---

## How the System Works

1. The user enters a prompt through the terminal.
2. The **Coordinator Agent** receives the request.
3. If the request is simple, the Coordinator answers it directly through the model.
4. If the request is complex, it is sent to the **Planner Agent**.
5. The Planner decides whether memory retrieval or execution is required.
6. The **Memory Agent** provides relevant stored context if needed.
7. The **Executor Agent** performs approved actions if needed.
8. The **Reviewer Agent** checks the assembled result.
9. The Coordinator returns the final response to the user.

---

## Running the Project

### Standard local usage

Make sure Ollama is installed and running locally, then run:

```bash
python src/main.py
```

### Optional remote usage

If you want to use a remote Ollama instance, configure `OLLAMA_HOST_URL` before running the project.

Example:

```bash
export OLLAMA_HOST_URL="http://<remote-host>:11434"
python src/main.py
```

---

## Development Notes

During development, several local models were tested in order to evaluate:

* response speed
* reasoning quality
* planning quality
* practical usability for a multi-agent workflow

The final implementation was guided not only by model quality, but also by development practicality. Since Baby Claw may make multiple model calls during a single request, inference speed was an important factor in deciding which model to use during implementation.

---

## Final Note

The project is designed so that it can be run locally on one machine as intended by the assignment. The optional Mac-to-PC remote setup was added only for personal development convenience and does not change the core architecture of the system.

---
