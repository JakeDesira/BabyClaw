from pathlib import Path
import html
import time
import shutil
from multiprocessing import Process, Queue
import streamlit.components.v1 as components

import streamlit as st

from filesystem_guard import FilesystemGuard
from reasoning_settings import ReasoningSettings
import agents
from paths import MEMORY_DB_PATH, MEDIA_INPUT_DIR


st.set_page_config(
    page_title="Baby Claw",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)


DEFAULT_PLANNING_MODEL = "gemma4"
DEFAULT_REASONING_MODEL = "gpt-oss:20b"


CUSTOM_CSS = """
<style>
    .block-container {
        max-width: 1040px;
        padding-top: 2.25rem;
        padding-bottom: 12rem;
    }

    .app-header {
        margin-top: 0.3rem;
        margin-bottom: 1.8rem;
        text-align: center;
    }

    .app-title-main {
        color: rgba(255, 255, 255, 0.18);
        font-size: clamp(4.5rem, 10vw, 8.5rem);
        font-weight: 900;
        letter-spacing: -0.025em;
        line-height: 0.95;
        user-select: none;
    }

    .app-title-sub {
        margin-top: 0.95rem;
        display: flex;
        justify-content: center;
        gap: 0.75rem;
        flex-wrap: wrap;
    }

    .model-pill {
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 999px;
        padding: 0.42rem 0.85rem;
        background: rgba(255, 255, 255, 0.04);
        color: rgba(255, 255, 255, 0.62);
        font-size: 0.78rem;
    }

    .empty-chat-hero {
        min-height: 32vh;
    }

    .bottom-spacer {
        height: 11rem;
    }

    /* Reasoning selector: floating pill attached to chat input */
    div[data-testid="stSelectbox"] {
        position: fixed !important;
        left: calc(50% - 380px) !important;
        bottom: var(--babyclaw-reasoning-bottom, 6.25rem) !important;
        transform: none !important;
        width: 180px !important;
        max-width: 180px !important;
        z-index: 102 !important;
    }

    div[data-testid="stSelectbox"] label {
        display: none !important;
    }

    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 38px !important;
        height: 38px !important;
        border-radius: 999px !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        background: rgba(255, 255, 255, 0.055) !important;
        box-shadow: none !important;
    }

    div[data-testid="stSelectbox"] [data-baseweb="select"] span {
        font-size: 0.82rem !important;
        font-weight: 700 !important;
        color: rgba(255, 255, 255, 0.72) !important;
    }

    /* Native Streamlit chat input */
    div[data-testid="stChatInput"] {
        position: fixed !important;
        left: 50% !important;
        bottom: 1.5rem !important;
        transform: translateX(-50%) !important;
        width: min(760px, calc(100vw - 3rem)) !important;
        z-index: 100 !important;
    }

    /* Hide Streamlit sidebar */
    section[data-testid="stSidebar"] {
        display: none;
    }

    /* Native Streamlit chat input: Enter sends, Shift+Enter creates newline */
    div[data-testid="stChatInput"] {
        position: fixed !important;
        left: 50% !important;
        bottom: 1.5rem !important;
        transform: translateX(-50%) !important;
        width: min(760px, calc(100vw - 3rem)) !important;
        z-index: 100 !important;
    }

    div[data-testid="stChatInput"] textarea {
        min-height: 48px !important;
        max-height: 150px !important;
        border-radius: 16px !important;
        font-size: 0.95rem !important;
        line-height: 1.4 !important;
    }

    div[data-testid="InputInstructions"] {
        display: none !important;
    }

    /* Bigger top tabs */
    div[data-testid="stTabs"] button {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        padding: 0.8rem 1.05rem !important;
    }

    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.35rem !important;
    }

    /* General buttons */
    div[data-testid="stButton"] button {
        border-radius: 14px;
        height: 48px;
        min-width: 52px;
        font-weight: 800;
    }

    /* Bigger chat messages */
    div[data-testid="stChatMessage"] {
        padding: 0.9rem 1.1rem !important;
        border-radius: 15px !important;
    }

    .message-text {
        line-height: 1.55;
        font-size: 1.02rem;
        font-weight: 450;
    }

    .message-text p {
        margin: 0.45rem 0 0.85rem 0;
    }

    .message-text strong {
        font-weight: 800;
    }

    .message-text a {
        color: #4da3ff;
        text-decoration: none;
        font-weight: 650;
    }

    .message-text a:hover {
        text-decoration: underline;
    }

    div[data-testid="stChatMessage"] {
        padding: 1rem 1.15rem !important;
        border-radius: 16px !important;
    }

    div[data-testid="stChatMessageAvatarUser"],
    div[data-testid="stChatMessageAvatarAssistant"] {
        width: 2.45rem !important;
        height: 2.45rem !important;
    }

    /* Clean Streamlit chrome */
    div[data-testid="stDecoration"] {
        display: none;
    }

    footer {
        display: none;
    }

    header {
        visibility: hidden;
    }

    /* Fake disabled input shown while agent is running */
    .working-input-bar {
        position: fixed;
        left: 50%;
        bottom: 1.5rem;
        transform: translateX(-50%);
        width: min(760px, calc(100vw - 3rem));
        height: 64px;
        border-radius: 16px;
        background: rgb(38, 40, 51);
        border: 1px solid rgba(255, 255, 255, 0.08);
        z-index: 100;
        display: flex;
        align-items: center;
        padding: 0 4.6rem 0 1.35rem;
    }

    .working-input-placeholder {
        color: rgba(255, 255, 255, 0.45);
        font-size: 0.95rem;
        font-weight: 600;
    }

    button.babyclaw-stop-button {
        position: fixed !important;
        left: calc(50% + 320px) !important;
        bottom: 2.15rem !important;
        z-index: 300 !important;

        width: 42px !important;
        height: 42px !important;
        min-width: 42px !important;

        border-radius: 13px !important;
        padding: 0 !important;

        background: #ff3038 !important;
        border: 1px solid #ff3038 !important;
        color: white !important;

        font-size: 0.9rem !important;
        font-weight: 800 !important;

        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* Small delete buttons in file/workspace rows */
    div[data-testid="stButton"] button[kind="secondary"] {
        min-width: 42px;
    }
</style>
"""


def build_backend(reasoning_mode: str):
    debug = False

    reasoning_settings = ReasoningSettings(mode=reasoning_mode)

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

    memory_writer = agents.MemoryWriter(
        model=DEFAULT_PLANNING_MODEL,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    memory_router = agents.MemoryRouter(
        model=DEFAULT_PLANNING_MODEL,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    executor = agents.ExecutorAgent(
        memory=memory,
        filesystem_guard=filesystem_guard,
        debug=debug,
    )

    response_generator = agents.ResponseGenerator(
        memory=memory,
        reasoning_model=DEFAULT_REASONING_MODEL,
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
        model=DEFAULT_REASONING_MODEL,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    planner = agents.PlannerAgent(
        memory=memory,
        planning_model=DEFAULT_PLANNING_MODEL,
        filesystem_guard=filesystem_guard,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    coordinator = agents.CoordinatorAgent(
        planner=planner,
        plan_executor=plan_executor,
        response_generator=response_generator,
        reviewer=reviewer,
        memory=memory,
        model=DEFAULT_PLANNING_MODEL,
        memory_router=memory_router,
        memory_writer=memory_writer,
        reasoning_settings=reasoning_settings,
        debug=debug,
    )

    return {
        "reasoning_settings": reasoning_settings,
        "filesystem_guard": filesystem_guard,
        "transaction_manager": transaction_manager,
        "memory": memory,
        "coordinator": coordinator,
        "plan_executor": plan_executor,
        "planner": planner,
        "response_generator": response_generator,
    }


def initialise_state():
    if "reasoning_mode" not in st.session_state:
        st.session_state.reasoning_mode = "medium"

    if "backend" not in st.session_state:
        st.session_state.backend = build_backend(st.session_state.reasoning_mode)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "last_trace" not in st.session_state:
        st.session_state.last_trace = {}

    if "workspace_notice" not in st.session_state:
        st.session_state.workspace_notice = ""

    if "memory_delete_result" not in st.session_state:
        st.session_state.memory_delete_result = ""

    if "current_task" not in st.session_state:
        st.session_state.current_task = None

    if "task_result_queue" not in st.session_state:
        st.session_state.task_result_queue = None

    if "current_task_id" not in st.session_state:
        st.session_state.current_task_id = 0

    if "cancelled_task_ids" not in st.session_state:
        st.session_state.cancelled_task_ids = set()

    if "chat_input_version" not in st.session_state:
        st.session_state.chat_input_version = 0

    if "last_snapshot_path" not in st.session_state:
        st.session_state.last_snapshot_path = ""

    if "last_snapshot_target" not in st.session_state:
        st.session_state.last_snapshot_target = ""


def get_model_labels() -> tuple[str, str]:
    backend = st.session_state.backend

    planning_model = DEFAULT_PLANNING_MODEL
    reasoning_model = DEFAULT_REASONING_MODEL

    try:
        planning_model = backend["planner"].planning_client.model
    except Exception:
        pass

    try:
        reasoning_model = backend["response_generator"].reasoning_client.model
    except Exception:
        pass

    return planning_model, reasoning_model


def rebuild_backend_if_mode_changed(selected_mode: str):
    if selected_mode != st.session_state.reasoning_mode:
        old_backend = st.session_state.backend

        st.session_state.reasoning_mode = selected_mode
        new_backend = build_backend(selected_mode)

        for approved_path in old_backend["filesystem_guard"].list_approved():
            new_backend["filesystem_guard"].approve(approved_path)

        st.session_state.backend = new_backend


def run_agent_task(
    reasoning_mode: str,
    prompt: str,
    task_id: int,
    approved_dirs: list[str],
    active_directory: str,
    result_queue: Queue,
):
    try:
        backend = build_backend(reasoning_mode)

        for directory in approved_dirs:
            backend["filesystem_guard"].approve(directory)

        if active_directory:
            backend["filesystem_guard"].set_active_directory(active_directory)

        print("CHILD APPROVED DIRS:", backend["filesystem_guard"].list_approved())
        print("CHILD ACTIVE DIR:", backend["filesystem_guard"].get_active_directory())

        coordinator = backend["coordinator"]

        reply = coordinator.handle(prompt)
        trace = shrink_trace_for_gui(getattr(coordinator, "last_trace", {}))

        result_queue.put(
            {
                "ok": True,
                "task_id": task_id,
                "reply": reply,
                "trace": trace,
            }
        )

    except Exception as e:
        result_queue.put(
            {
                "ok": False,
                "task_id": task_id,
                "reply": f"Error while running task: {e}",
                "trace": {},
            }
        )
def apply_reasoning_pill_follow_script():
    components.html(
        """
        <script>
            function updateReasoningPillPosition() {
                const doc = window.parent.document;

                const chatInput = doc.querySelector('div[data-testid="stChatInput"]');
                const workingInput = doc.querySelector(".working-input-bar");

                let inputElement = chatInput;

                if (!inputElement && workingInput) {
                    inputElement = workingInput;
                }

                if (!inputElement) {
                    doc.documentElement.style.setProperty(
                        "--babyclaw-reasoning-bottom",
                        "6.25rem"
                    );
                    return;
                }

                const rect = inputElement.getBoundingClientRect();
                const viewportHeight = window.parent.innerHeight;

                const distanceFromBottom = viewportHeight - rect.top;
                const extraGap = 14;

                const newBottom = distanceFromBottom + extraGap;

                doc.documentElement.style.setProperty(
                    "--babyclaw-reasoning-bottom",
                    newBottom + "px"
                );
            }

            if (!window.parent.__babyclawReasoningPillInterval) {
                window.parent.__babyclawReasoningPillInterval = setInterval(
                    updateReasoningPillPosition,
                    150
                );
            }

            updateReasoningPillPosition();
            setTimeout(updateReasoningPillPosition, 50);
            setTimeout(updateReasoningPillPosition, 150);
            setTimeout(updateReasoningPillPosition, 300);
        </script>
        """,
        height=0,
        width=0,
    )

def apply_stop_button_script():
    components.html(
        """
        <script>
            function styleStopButton() {
                const buttons = window.parent.document.querySelectorAll("button");

                buttons.forEach((button) => {
                    if (button.innerText.trim() === "■") {
                        button.classList.add("babyclaw-stop-button");

                        const wrapper = button.closest('div[data-testid="stButton"]');

                        if (wrapper) {
                            wrapper.style.position = "fixed";
                            wrapper.style.left = "calc(50% + 320px)";
                            wrapper.style.bottom = "2.15rem";
                            wrapper.style.zIndex = "300";
                            wrapper.style.width = "42px";
                            wrapper.style.height = "42px";
                        }
                    }
                });
            }

            styleStopButton();
            setTimeout(styleStopButton, 50);
            setTimeout(styleStopButton, 150);
            setTimeout(styleStopButton, 300);
        </script>
        """,
        height=0,
        width=0,
    )

def cancel_current_task():
    current_task = st.session_state.current_task

    if not current_task:
        return

    process = current_task["process"]

    if process.is_alive():
        process.terminate()
        process.join(timeout=1)

        if process.is_alive():
            process.kill()
            process.join(timeout=1)

    st.session_state.current_task = None
    st.session_state.task_result_queue = None

    st.session_state.messages.append(
    {
        "role": "assistant",
        "content": (
            "Task stopped. Any files changed during this task may still exist. "
            "Use 'Undo last filesystem change' in the Workspace tab to restore the project "
            "to how it was before this task started."
        ),
    }
)


def collect_finished_task():
    current_task = st.session_state.current_task
    result_queue = st.session_state.task_result_queue

    if not current_task or result_queue is None:
        return

    process = current_task["process"]

    result = None

    # Important:
    # Read from the queue even while the process is still alive.
    # Otherwise the child process can block forever while trying to put a large trace.
    try:
        if not result_queue.empty():
            result = result_queue.get_nowait()
    except Exception as e:
        result = {
            "ok": False,
            "reply": f"Error reading task result: {e}",
            "trace": {},
        }

    if result is None:
        if process.is_alive():
            return

        process.join(timeout=1)

        st.session_state.current_task = None
        st.session_state.task_result_queue = None

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Task ended without returning a result.",
            }
        )
        return

    if process.is_alive():
        process.join(timeout=1)

    if process.is_alive():
        process.terminate()
        process.join(timeout=1)

    st.session_state.current_task = None
    st.session_state.task_result_queue = None

    trace = result.get("trace", {})

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("reply", ""),
        }
    )

    st.session_state.last_trace = trace
    restore_snapshot_reference_from_trace(trace)


def render_header():
    planning_model, reasoning_model = get_model_labels()

    st.markdown(
        f"""
        <div class="app-header">
            <div class="app-title-main">BabyClaw</div>
            <div class="app-title-sub">
                <div class="model-pill">Planning model: <b>{html.escape(planning_model)}</b></div>
                <div class="model-pill">Reasoning model: <b>{html.escape(reasoning_model)}</b></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_message_text(content: str):
    st.markdown(
        """
        <div class="message-text">
        """,
        unsafe_allow_html=True,
    )

    st.markdown(content)

    st.markdown(
        """
        </div>
        """,
        unsafe_allow_html=True,
    )

def shorten_text(value, max_chars: int = 4000):
    if not isinstance(value, str):
        return value

    if len(value) <= max_chars:
        return value

    return value[:max_chars] + "\n\n... [truncated for GUI]"


def shrink_trace_for_gui(trace: dict) -> dict:
    if not isinstance(trace, dict):
        return {}

    cleaned = dict(trace)

    steps = cleaned.get("steps", [])

    if isinstance(steps, list):
        cleaned_steps = []

        for step in steps:
            if not isinstance(step, dict):
                continue

            cleaned_step = dict(step)
            cleaned_step["result"] = shorten_text(cleaned_step.get("result", ""))
            cleaned_step["resolved_input"] = shorten_text(cleaned_step.get("resolved_input", ""), 1500)
            cleaned_step["input"] = shorten_text(cleaned_step.get("input", ""), 1500)

            cleaned_steps.append(cleaned_step)

        cleaned["steps"] = cleaned_steps

    execution_data = cleaned.get("execution_data", {})

    if isinstance(execution_data, dict):
        cleaned_execution_data = dict(execution_data)
        cleaned_execution_data["execution_result"] = shorten_text(
            cleaned_execution_data.get("execution_result", "")
        )
        cleaned_execution_data["full_execution_result"] = shorten_text(
            cleaned_execution_data.get("full_execution_result", "")
        )
        cleaned_execution_data["source_text"] = shorten_text(
            cleaned_execution_data.get("source_text", "")
        )
        cleaned["execution_data"] = cleaned_execution_data

    return cleaned


def start_agent_task(prompt: str):
    st.session_state.current_task_id += 1
    task_id = st.session_state.current_task_id

    st.session_state.last_snapshot_path = ""
    st.session_state.last_snapshot_target = ""

    filesystem_guard = st.session_state.backend["filesystem_guard"]
    transaction_manager = st.session_state.backend["transaction_manager"]

    approved_dirs = filesystem_guard.list_approved()
    active_directory = filesystem_guard.get_active_directory()

    if active_directory:
        snapshot_result = transaction_manager.snapshot_directory(active_directory)

        if snapshot_result.startswith("Snapshot created:"):
            st.session_state.last_snapshot_path = snapshot_result.replace(
                "Snapshot created:",
                "",
                1,
            ).strip()
            st.session_state.last_snapshot_target = active_directory

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    result_queue = Queue()

    process = Process(
        target=run_agent_task,
        args=(
            st.session_state.reasoning_mode,
            prompt,
            task_id,
            approved_dirs,
            active_directory,
            result_queue,
        ),
    )

    process.start()

    st.session_state.task_result_queue = result_queue

    st.session_state.current_task = {
        "id": task_id,
        "prompt": prompt,
        "process": process,
    }


def render_workspace_tab():
    backend = st.session_state.backend
    filesystem_guard = backend["filesystem_guard"]
    memory = backend["memory"]

    st.subheader("Workspace access")

    if st.session_state.workspace_notice:
        st.success(st.session_state.workspace_notice)
        st.session_state.workspace_notice = ""

    approved_dirs = filesystem_guard.list_approved()

    if approved_dirs:
        st.success("Access granted")

        st.caption("Active directory")
        st.code(filesystem_guard.get_active_directory())

        with st.expander("All approved directories", expanded=True):
            for index, directory in enumerate(approved_dirs):
                col_path, col_remove = st.columns([12, 1], vertical_alignment="center")

                with col_path:
                    st.write(directory)

                with col_remove:
                    remove_clicked = st.button(
                        "✕",
                        key=f"remove_approved_dir_{index}",
                        help="Remove directory access",
                    )

                if remove_clicked:
                    live_revoked = filesystem_guard.revoke(directory)

                    try:
                        memory_result = memory.revoke_accessible_path(directory)
                    except AttributeError:
                        memory_result = "Memory path removal is not available."

                    if live_revoked:
                        active_directory = filesystem_guard.get_active_directory()

                        if active_directory:
                            active_result = memory.save_active_accessible_path(active_directory)
                        else:
                            active_result = memory.clear_active_accessible_path()

                        st.session_state.workspace_notice = (
                            f"Removed access for:\n\n{directory}\n\n"
                            f"{memory_result}\n"
                            f"{active_result}"
                        )
                    else:
                        st.session_state.workspace_notice = (
                            f"That directory was not currently approved:\n\n{directory}\n\n{memory_result}"
                        )

                    st.rerun()
    else:
        st.warning("No directory approved yet.")

    st.divider()

    st.subheader("Grant directory access")

    path_input = st.text_input(
        "Directory path",
        placeholder="/Users/jake/path/to/project",
    )

    grant_clicked = st.button("Grant access")

    if grant_clicked:
        cleaned_path = path_input.strip().strip("\"'")

        if not cleaned_path:
            st.error("Enter a directory path first.")
        elif filesystem_guard.approve(cleaned_path):
            resolved_path = Path(cleaned_path).expanduser().resolve()
            memory_result = memory.save_accessible_path(str(resolved_path))
            active_result = memory.save_active_accessible_path(str(resolved_path))

            st.session_state.workspace_notice = (
                f"Access granted to {resolved_path}\n\n"
                f"{memory_result}\n"
                f"{active_result}"
            )

            st.rerun()
        else:
            st.error("Could not approve that path. Make sure it exists and is a directory.")

    st.divider()

    st.subheader("Safety")

    if st.button("Undo last filesystem change"):
        result = undo_last_filesystem_change()
        st.info(result)

def restore_snapshot_reference_from_trace(trace: dict) -> None:
    """
    The agent runs in a separate process, so the snapshot is created there.
    This function stores the snapshot path and target path in Streamlit session_state
    so the GUI process can undo it later.
    """
    if not trace:
        return

    execution_data = trace.get("execution_data", {})

    snapshot_path = (
        trace.get("snapshot_path", "")
        or execution_data.get("snapshot_path", "")
    )

    snapshot_target = (
        trace.get("snapshot_target", "")
        or execution_data.get("snapshot_target", "")
    )

    if snapshot_path and snapshot_target:
        st.session_state.last_snapshot_path = snapshot_path
        st.session_state.last_snapshot_target = snapshot_target
        return

    snapshot_result = execution_data.get("snapshot_result", "")

    if not snapshot_result:
        return

    prefix = "Snapshot created:"

    if not snapshot_result.startswith(prefix):
        return

    snapshot_path = snapshot_result.replace(prefix, "", 1).strip()

    if not snapshot_path:
        return

    st.session_state.last_snapshot_path = snapshot_path

    target_directory = ""

    steps = trace.get("steps", [])

    if not steps:
        steps = execution_data.get("steps", [])

    for step in steps:
        resolved_input = step.get("resolved_input", "")

        if not resolved_input:
            continue

        file_part = resolved_input.split("::", 1)[0].strip()

        if file_part:
            target_directory = str(Path(file_part).expanduser().resolve().parent)
            break

    if not target_directory:
        try:
            target_directory = st.session_state.backend["filesystem_guard"].get_active_directory()
        except Exception:
            target_directory = ""

    st.session_state.last_snapshot_target = target_directory


def undo_last_filesystem_change() -> str:
    snapshot_path_value = st.session_state.get("last_snapshot_path", "")
    target_path_value = st.session_state.get("last_snapshot_target", "")

    if not snapshot_path_value:
        return "Nothing to undo. No snapshot is available."

    snapshot_path = Path(snapshot_path_value).expanduser().resolve()

    if not snapshot_path.exists() or not snapshot_path.is_dir():
        return f"Nothing to undo. Snapshot folder was not found: {snapshot_path}"

    if not target_path_value:
        return "Nothing to undo. The target directory for this snapshot is unknown."

    target_path = Path(target_path_value).expanduser().resolve()

    filesystem_guard = st.session_state.backend["filesystem_guard"]

    if not filesystem_guard.is_approved(target_path):
        return f"Undo failed: target directory is no longer approved: {target_path}"

    try:
        if target_path.exists():
            if target_path.is_file():
                target_path.unlink()
            else:
                shutil.rmtree(target_path)

        shutil.copytree(snapshot_path, target_path)

        st.session_state.last_snapshot_path = ""
        st.session_state.last_snapshot_target = ""

        return f"Undo complete. Restored: {target_path}"

    except Exception as e:
        return f"Undo failed: {e}"

def render_files_tab():
    st.subheader("Input files")
    st.caption("Upload files here so BabyClaw can read them from the media input directory.")

    upload_dir = MEDIA_INPUT_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)

    st.caption(f"Media input directory being used: {upload_dir}")

    if "file_uploader_version" not in st.session_state:
        st.session_state.file_uploader_version = 0

    if "files_notice" not in st.session_state:
        st.session_state.files_notice = ""

    uploaded_files = st.file_uploader(
        "Drag and drop files here",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.file_uploader_version}",
    )

    if uploaded_files:
        saved_names = []

        for uploaded_file in uploaded_files:
            safe_name = Path(uploaded_file.name).name
            destination = upload_dir / safe_name
            destination.write_bytes(uploaded_file.getbuffer())
            saved_names.append(safe_name)

        st.session_state.files_notice = "Uploaded: " + ", ".join(saved_names)

        # Reset the uploader so uploaded files do not remain visually stuck there.
        st.session_state.file_uploader_version += 1
        st.rerun()

    if st.session_state.files_notice:
        st.success(st.session_state.files_notice)
        st.session_state.files_notice = ""

    existing_files = sorted(
        path
        for path in upload_dir.iterdir()
        if path.is_file() and path.name != ".gitkeep"
    )

    if existing_files:
        st.write("Available input files:")

        for file_path in existing_files:
            col_name, col_delete = st.columns([12, 1], vertical_alignment="center")

            with col_name:
                file_size_kb = file_path.stat().st_size / 1024

                st.markdown(
                    f"""
                    <div style="
                        padding: 0.75rem 0.9rem;
                        border: 1px solid rgba(255,255,255,0.10);
                        border-radius: 12px;
                        background: rgba(255,255,255,0.025);
                        font-weight: 650;
                    ">
                        {html.escape(file_path.name)}
                        <span style="
                            color: rgba(255,255,255,0.45);
                            font-size: 0.82rem;
                            margin-left: 0.5rem;
                        ">
                            {file_size_kb:.1f} KB
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_delete:
                delete_clicked = st.button(
                    "✕",
                    key=f"delete_input_file_{file_path.name}",
                    help=f"Delete {file_path.name}",
                )

            if delete_clicked:
                try:
                    file_path.unlink()
                    st.session_state.files_notice = f"Deleted: {file_path.name}"
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not delete {file_path.name}: {e}")

    else:
        st.info("No input files uploaded yet.")


def render_memory_tab():
    backend = st.session_state.backend
    memory = backend["memory"]

    st.subheader("Saved memories")

    memories = memory.memory_store.list_recent_memories(limit=50)

    if memories:
        table_rows = []

        for item in memories:
            table_rows.append(
                {
                    "Memory ID": item.get("id"),
                    "Type": item.get("memory_type"),
                    "Importance": item.get("importance"),
                    "Content": item.get("content"),
                    "Created": item.get("created_at"),
                }
            )

        st.dataframe(
            table_rows,
            use_container_width=True,
            hide_index=True,
        )

        st.caption("Use the Memory ID when deleting a saved memory.")
    else:
        st.info("No saved memories yet.")

    st.divider()

    st.subheader("Delete memory")

    memory_id = st.text_input(
        "Memory ID",
        placeholder="Example: 20",
    )

    if st.button("Delete memory"):
        result = memory.delete_long_term_memory(memory_id)
        st.session_state.memory_delete_result = result
        st.rerun()

    if st.session_state.memory_delete_result:
        st.info(st.session_state.memory_delete_result)

def render_working_input_bar():
    clicked = st.button(
        "■",
        key="stop_inside_input",
        help="Stop current task",
    )

    st.markdown(
        """
        <div class="working-input-bar">
            <div class="working-input-placeholder">BabyClaw is working...</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    apply_stop_button_script()

    if clicked:
        cancel_current_task()
        st.rerun()


def render_chat_tab():
    collect_finished_task()

    current_task = st.session_state.current_task
    task_is_running = current_task is not None

    if not st.session_state.messages and not task_is_running:
        st.markdown('<div class="empty-chat-hero"></div>', unsafe_allow_html=True)
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                render_message_text(message["content"])

    if task_is_running:
        with st.chat_message("assistant"):
            st.spinner("BabyClaw is working...")

    st.markdown('<div class="bottom-spacer"></div>', unsafe_allow_html=True)


    selected_mode = st.selectbox(
        "Reasoning mode",
        options=["low", "medium", "high"],
        index=["low", "medium", "high"].index(st.session_state.reasoning_mode),
        format_func=lambda value: {
            "low": "Low Thinking",
            "medium": "Medium Thinking",
            "high": "High Thinking",
        }[value],
        label_visibility="collapsed",
        disabled=task_is_running,
    )

    if task_is_running:
        render_working_input_bar()
    else:
        rebuild_backend_if_mode_changed(selected_mode)
        st.session_state.backend["reasoning_settings"].mode = st.session_state.reasoning_mode

        user_prompt = st.chat_input("Ask anything")

        if user_prompt:
            cleaned_prompt = user_prompt.strip()

            if cleaned_prompt:
                start_agent_task(cleaned_prompt)
                st.rerun()

    apply_reasoning_pill_follow_script()

    if task_is_running:
        time.sleep(0.4)
        st.rerun()


def render_debug_tab():
    trace = st.session_state.last_trace or {}

    st.subheader("Agent internals")

    planner_tab, executor_tab, verification_tab, raw_tab = st.tabs(
        [
            "Planner",
            "Executor",
            "Verification",
            "Raw trace",
        ]
    )

    with planner_tab:
        plan = trace.get("plan")

        if plan:
            st.json(plan)
        else:
            st.caption("No planner output yet.")

    with executor_tab:
        steps = trace.get("steps", [])

        if steps:
            for index, step in enumerate(steps, start=1):
                with st.container(border=True):
                    st.markdown(f"### Step {index}: `{step.get('action', '')}`")

                    st.caption("Input")
                    st.code(step.get("input", ""))

                    st.caption("Resolved input")
                    st.code(step.get("resolved_input", ""))

                    st.caption("Result")
                    st.code(step.get("result", ""))
        else:
            st.caption("No executor actions yet.")

    with verification_tab:
        steps = trace.get("steps", [])
        found_verification = False

        for index, step in enumerate(steps, start=1):
            verification = step.get("verification")

            if verification:
                found_verification = True

                with st.container(border=True):
                    st.markdown(f"### Step {index}: `{step.get('action', '')}`")
                    st.json(verification)

        if not found_verification:
            st.caption("No verification results yet.")

    with raw_tab:
        if trace:
            st.json(trace)
        else:
            st.caption("No trace available yet.")


def render_app():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    render_header()

    chat_tab, workspace_tab, files_tab, memory_tab, debug_tab = st.tabs(
        [
            "Chat",
            "Workspace",
            "Files",
            "Memory",
            "Debug / Internals",
        ]
    )

    with chat_tab:
        render_chat_tab()

    with workspace_tab:
        render_workspace_tab()

    with files_tab:
        render_files_tab()

    with memory_tab:
        render_memory_tab()

    with debug_tab:
        render_debug_tab()


def main():
    initialise_state()
    render_app()


if __name__ == "__main__":
    main()