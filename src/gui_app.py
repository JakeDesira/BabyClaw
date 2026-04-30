from pathlib import Path
import html
import logging
import sys
import traceback
import time
import shutil
from multiprocessing import Process, Queue
import streamlit.components.v1 as components
from queue import Empty
import re

import streamlit as st

from backend_factory import build_backend as create_backend
from reasoning_settings import ReasoningSettings
from paths import MEDIA_INPUT_DIR, PROJECT_ROOT
from config import DEFAULT_PLANNING_MODEL, DEFAULT_REASONING_MODEL

ASSET_DIR = Path(__file__).resolve().parent / "assets"
STREAMLIT_LOG_PATH = PROJECT_ROOT / "babyclaw_streamlit.log"
_STD_STREAM_LOG = None

st.set_page_config(
    page_title="Baby Claw",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_asset(name: str) -> str:
    """Load a GUI asset file from the local assets directory."""
    return (ASSET_DIR / name).read_text(encoding="utf-8")


def stream_is_usable(stream) -> bool:
    """Return whether a standard stream can be flushed safely."""
    try:
        stream.flush()
        return True
    except Exception:
        return False


def ensure_valid_std_streams() -> None:
    """Redirect broken standard streams before multiprocessing flushes them."""
    global _STD_STREAM_LOG

    stdout_is_usable = stream_is_usable(sys.stdout)
    stderr_is_usable = stream_is_usable(sys.stderr)

    if stdout_is_usable and stderr_is_usable:
        return

    if _STD_STREAM_LOG is None or _STD_STREAM_LOG.closed:
        _STD_STREAM_LOG = STREAMLIT_LOG_PATH.open("a", encoding="utf-8")

    if not stdout_is_usable:
        sys.stdout = _STD_STREAM_LOG

    if not stderr_is_usable:
        sys.stderr = _STD_STREAM_LOG

    for logger_name in ("", "streamlit"):
        logger = logging.getLogger(logger_name)

        for handler in logger.handlers:
            stream = getattr(handler, "stream", None)

            if stream is not None and not stream_is_usable(stream):
                handler.stream = _STD_STREAM_LOG


def render_gui_assets() -> None:
    """Render CSS and JavaScript assets used by the Streamlit GUI."""
    st.markdown(f"<style>{load_asset('gui.css')}</style>", unsafe_allow_html=True)
    components.html(
        f"<script>{load_asset('gui.js')}</script>",
        height=0,
        width=0,
    )


def build_backend(reasoning_mode: str):
    """Build the shared BabyClaw backend object graph."""
    return create_backend(
        reasoning_settings=ReasoningSettings(mode=reasoning_mode),
    )


def initialise_state():
    """Initialise state."""
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
    """Return model labels."""
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
    """Rebuild backend if mode changed."""
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
    recent_messages: list[dict],
    result_queue: Queue,
):
    """Run agent task."""
    try:
        backend = build_backend(reasoning_mode)

        for directory in approved_dirs:
            backend["filesystem_guard"].approve(directory)

        if active_directory:
            backend["filesystem_guard"].set_active_directory(active_directory)

        print("CHILD APPROVED DIRS:", backend["filesystem_guard"].list_approved())
        print("CHILD ACTIVE DIR:", backend["filesystem_guard"].get_active_directory())

        memory = backend.get("memory")

        if memory is not None:
            for message in recent_messages:
                role = str(message.get("role", "")).strip()
                content = str(message.get("content", "")).strip()

                if role in {"user", "assistant"} and content:
                    try:
                        memory.save_short_term(role=role, content=content)
                    except AttributeError:
                        break

        coordinator = backend["coordinator"]

        def publish_trace(trace: dict) -> None:
            """Send a live trace snapshot back to the GUI process."""
            result_queue.put(
                {
                    "type": "trace",
                    "ok": True,
                    "task_id": task_id,
                    "trace": shrink_trace_for_gui(trace),
                }
            )

        try:
            coordinator.set_trace_callback(publish_trace)
        except AttributeError:
            pass

        reply = coordinator.handle(prompt)
        trace = shrink_trace_for_gui(getattr(coordinator, "last_trace", {}))

        result_queue.put(
            {
                "type": "result",
                "ok": True,
                "task_id": task_id,
                "reply": reply,
                "trace": trace,
            }
        )

    except Exception as e:
        result_queue.put(
            {
                "type": "result",
                "ok": False,
                "task_id": task_id,
                "reply": (
                    f"Error while running task: {e}\n\n"
                    f"{traceback.format_exc()}"
                ),
                "trace": {},
            }
        )


def cancel_current_task():
    """Cancel current task."""
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


def handle_task_queue_event(event: dict, current_task: dict) -> dict | None:
    """Apply an interim task event and return a final result event when present."""
    if not isinstance(event, dict):
        return {
            "ok": False,
            "reply": "Error reading task result: task returned a non-dictionary event.",
            "trace": {},
        }

    event_task_id = event.get("task_id")
    current_task_id = current_task.get("id")

    if event_task_id is not None and event_task_id != current_task_id:
        return None

    if event.get("type") == "trace":
        trace = event.get("trace", {})

        if trace:
            st.session_state.last_trace = trace
            restore_snapshot_reference_from_trace(trace)

        return None

    return event


def collect_finished_task():
    """Collect finished task."""
    current_task = st.session_state.current_task
    result_queue = st.session_state.task_result_queue

    if not current_task or result_queue is None:
        return

    process = current_task["process"]

    result = None

    while True:
        try:
            event = result_queue.get_nowait()
        except Empty:
            break
        except Exception as e:
            result = {
                "ok": False,
                "reply": f"Error reading task result: {e}",
                "trace": {},
            }
            break

        possible_result = handle_task_queue_event(event, current_task)

        if possible_result is not None:
            result = possible_result
            break

    if result is None:
        if process.is_alive():
            return

        process.join(timeout=1)

        while True:
            try:
                event = result_queue.get(timeout=0.2)
            except Empty:
                break
            except Exception as e:
                result = {
                    "ok": False,
                    "reply": f"Error reading task result after process ended: {e}",
                    "trace": {},
                }
                break

            possible_result = handle_task_queue_event(event, current_task)

            if possible_result is not None:
                result = possible_result
                break

    if result is None:
        st.session_state.current_task = None
        st.session_state.task_result_queue = None

        try:
            result_queue.close()
            result_queue.join_thread()
        except Exception:
            pass

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "Task ended without returning a result.\n\n"
                    f"Child process exit code: {process.exitcode}\n"
                    f"Check Streamlit logs: {STREAMLIT_LOG_PATH}"
                ),
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

    try:
        result_queue.close()
        result_queue.join_thread()
    except Exception:
        pass

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
    """Render header."""
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


def normalise_latex_for_streamlit(text: str) -> str:
    """Convert common LLM LaTeX patterns into Streamlit-friendly markdown math."""
    cleaned = text

    # Convert \( ... \) to $ ... $
    cleaned = re.sub(
        r"\\\((.*?)\\\)",
        r"$\1$",
        cleaned,
        flags=re.DOTALL,
    )

    # Convert \[ ... \] to $$ ... $$
    cleaned = re.sub(
        r"\\\[(.*?)\\\]",
        r"\n\n$$\n\1\n$$\n\n",
        cleaned,
        flags=re.DOTALL,
    )

    # Convert standalone [ formula ] blocks into $$ formula $$,
    # but only when the bracket content looks like LaTeX/math.
    def replace_square_math(match):
        inner = match.group(1).strip()

        math_markers = (
            "\\frac",
            "\\sum",
            "\\theta",
            "\\hat",
            "\\text",
            "_",
            "^",
            "\\log",
            "\\in",
            "\\rightarrow",
        )

        if any(marker in inner for marker in math_markers):
            return f"\n\n$$\n{inner}\n$$\n\n"

        return match.group(0)

    cleaned = re.sub(
        r"\[\s*([^\[\]]{8,300})\s*\]",
        replace_square_math,
        cleaned,
    )

    return cleaned


def render_message_text(content: str):
    """Render message text while preserving markdown and LaTeX."""
    content_text = str(content or "").strip()

    if not content_text:
        return

    content_text = normalise_latex_for_streamlit(content_text)

    has_markdown_or_latex = any(
        marker in content_text
        for marker in (
            "```",
            "# ",
            "## ",
            "### ",
            "- ",
            "* ",
            "1. ",
            "|",
            "$",
            "$$",
            "\\frac",
            "\\sum",
            "\\theta",
            "\\hat",
            "\\in",
            "\\rightarrow",
        )
    )

    lines = [line for line in content_text.splitlines() if line.strip()]

    if len(lines) >= 8 and not has_markdown_or_latex:
        st.markdown(
            f'<pre class="plain-message-output">{html.escape(content_text)}</pre>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(content_text)


def shorten_text(value, max_chars: int = 4000):
    """Shorten text."""
    if not isinstance(value, str):
        return value

    if len(value) <= max_chars:
        return value

    return value[:max_chars] + "\n\n... [truncated for GUI]"


def shrink_step_for_gui(step: dict) -> dict:
    """Shrink step for gui."""
    if not isinstance(step, dict):
        return {}

    cleaned_step = dict(step)

    cleaned_step["result"] = shorten_text(
        cleaned_step.get("result", "")
    )

    cleaned_step["resolved_input"] = shorten_text(
        cleaned_step.get("resolved_input", ""),
        1500,
    )

    cleaned_step["input"] = shorten_text(
        cleaned_step.get("input", ""),
        1500,
    )

    return cleaned_step


def shrink_trace_for_gui(trace: dict) -> dict:
    """Shrink trace for gui."""
    if not isinstance(trace, dict):
        return {}

    cleaned = dict(trace)

    steps = cleaned.get("steps", [])

    if isinstance(steps, list):
        cleaned["steps"] = [
            shrink_step_for_gui(step)
            for step in steps
            if isinstance(step, dict)
        ]

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

        execution_steps = cleaned_execution_data.get("steps", [])

        if isinstance(execution_steps, list):
            cleaned_execution_data["steps"] = [
                shrink_step_for_gui(step)
                for step in execution_steps
                if isinstance(step, dict)
            ]

        cleaned["execution_data"] = cleaned_execution_data

    final_step = cleaned.get("final_step")

    if isinstance(final_step, dict):
        cleaned_final_step = dict(final_step)
        cleaned_final_step["input"] = shorten_text(
            cleaned_final_step.get("input", ""),
            1500,
        )
        cleaned_final_step["final_response"] = shorten_text(
            cleaned_final_step.get("final_response", ""),
            2000,
        )
        cleaned["final_step"] = cleaned_final_step

    return cleaned


def start_agent_task(prompt: str):
    """Start agent task."""
    st.session_state.current_task_id += 1
    task_id = st.session_state.current_task_id

    st.session_state.last_snapshot_path = ""
    st.session_state.last_snapshot_target = ""
    st.session_state.last_trace = {
        "status": "Task started",
        "prompt": prompt,
        "steps": [],
    }

    filesystem_guard = st.session_state.backend["filesystem_guard"]
    transaction_manager = st.session_state.backend["transaction_manager"]

    approved_dirs = filesystem_guard.list_approved()
    active_directory = filesystem_guard.get_active_directory()
    recent_messages = [
        {
            "role": message.get("role", ""),
            "content": message.get("content", ""),
        }
        for message in st.session_state.messages[-10:]
    ]

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

    ensure_valid_std_streams()

    result_queue = Queue()

    process = Process(
        target=run_agent_task,
        args=(
            st.session_state.reasoning_mode,
            prompt,
            task_id,
            approved_dirs,
            active_directory,
            recent_messages,
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
    """Render workspace tab."""
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
    """Undo last filesystem change."""
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

    restore_tmp = target_path.with_name(target_path.name + "_babyclaw_restore_tmp")
    backup_tmp = target_path.with_name(target_path.name + "_babyclaw_backup_tmp")

    try:
        if restore_tmp.exists():
            shutil.rmtree(restore_tmp, ignore_errors=True)

        if backup_tmp.exists():
            shutil.rmtree(backup_tmp, ignore_errors=True)

        # First copy the snapshot into a temporary restore folder.
        # If this fails, the real project is untouched.
        shutil.copytree(snapshot_path, restore_tmp)

        # Then move the current target out of the way.
        if target_path.exists():
            target_path.rename(backup_tmp)

        # Put the restored snapshot in place.
        restore_tmp.rename(target_path)

        # Only delete the backup after the restore succeeded.
        if backup_tmp.exists():
            shutil.rmtree(backup_tmp, ignore_errors=True)

        st.session_state.last_snapshot_path = ""
        st.session_state.last_snapshot_target = ""

        return f"Undo complete. Restored: {target_path}"

    except Exception as e:
        # Try to recover if the original was moved to backup but restore failed.
        try:
            if not target_path.exists() and backup_tmp.exists():
                backup_tmp.rename(target_path)
        except Exception:
            pass

        return f"Undo failed safely. Original project was not intentionally deleted. Error: {e}"

def render_files_tab():
    """Render files tab."""
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
    """Render memory tab."""
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


def apply_reasoning_pill_follow_script():
    components.html(
        """
        <script>
            function positionReasoningButton() {
                const doc = window.parent.document;

                const chatInput = doc.querySelector('div[data-testid="stChatInput"]');

                if (!chatInput) {
                    return;
                }

                const buttons = Array.from(doc.querySelectorAll("button"));

                const gearButton = buttons.find((button) => {
                    return button.innerText.includes("⚙");
                });

                if (!gearButton) {
                    return;
                }

                const wrapper =
                    gearButton.closest('div[data-testid="stPopover"]') ||
                    gearButton.closest('div[data-testid="stButton"]') ||
                    gearButton.parentElement;

                if (!wrapper) {
                    return;
                }

                const chatRect = chatInput.getBoundingClientRect();

                const size = 42;
                const gapFromRightEdge = 68;
                const gapFromBottom = 12;

                wrapper.style.position = "fixed";
                wrapper.style.left = (chatRect.right - gapFromRightEdge - size) + "px";
                wrapper.style.top = (chatRect.bottom - gapFromBottom - size) + "px";
                wrapper.style.width = size + "px";
                wrapper.style.height = size + "px";
                wrapper.style.zIndex = "260";
                wrapper.style.margin = "0";
                wrapper.style.padding = "0";
                wrapper.style.transform = "none";

                gearButton.classList.add("babyclaw-reasoning-button");
            }

            if (window.parent.__babyclawReasoningButtonInterval) {
                clearInterval(window.parent.__babyclawReasoningButtonInterval);
            }

            window.parent.__babyclawReasoningButtonInterval = setInterval(
                positionReasoningButton,
                150
            );

            positionReasoningButton();
            setTimeout(positionReasoningButton, 50);
            setTimeout(positionReasoningButton, 150);
            setTimeout(positionReasoningButton, 300);
            setTimeout(positionReasoningButton, 700);
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


def render_working_input_bar():
    """Render fake input bar while the agent is running."""
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
    """Render chat tab."""
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

    if task_is_running:
        render_working_input_bar()
    else:
        with st.popover("⚙", use_container_width=False):
            st.caption("Thinking")

            selected_mode = st.radio(
                "Reasoning mode",
                options=["low", "medium", "high"],
                index=["low", "medium", "high"].index(st.session_state.reasoning_mode),
                format_func=lambda value: {
                    "low": "Low",
                    "medium": "Medium",
                    "high": "High",
                }[value],
                label_visibility="collapsed",
                key="reasoning_mode_radio",
            )

        rebuild_backend_if_mode_changed(selected_mode)
        st.session_state.backend["reasoning_settings"].mode = st.session_state.reasoning_mode

        user_prompt = st.chat_input("Ask anything")

        apply_reasoning_pill_follow_script()

        if user_prompt:
            cleaned_prompt = user_prompt.strip()

            if cleaned_prompt:
                start_agent_task(cleaned_prompt)
                st.rerun()



def render_debug_tab():
    """Render debug tab."""
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
        planner_steps = trace.get("planner_steps", [])

        if plan:
            st.json(plan)

        if planner_steps:
            st.divider()
            st.subheader("Iterative planner steps")

            for index, planner_step in enumerate(planner_steps, start=1):
                with st.container(border=True):
                    st.markdown(f"### Planner step {index}")

                    st.caption("Thought")
                    st.write(planner_step.get("thought_summary", ""))

                    st.caption("Status")
                    st.code(planner_step.get("status", ""))

                    st.caption("Action")
                    st.code(planner_step.get("action", ""))

                    st.caption("Input")
                    st.code(planner_step.get("input", ""))

                    final_response = planner_step.get("final_response", "")

                    if final_response:
                        st.caption("Final response")
                        st.write(final_response)

        if not plan and not planner_steps:
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
    """Render app."""
    ensure_valid_std_streams()
    render_gui_assets()

    # Collect live trace/result events before rendering any tab.
    collect_finished_task()

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

    # Keep polling while a child agent process is running.
    if st.session_state.current_task is not None:
        time.sleep(0.4)
        st.rerun()


def main():
    """Run the module entry point."""
    initialise_state()
    render_app()


if __name__ == "__main__":
    main()
