from mlpcopilot.bus.events import OutboundMessage
from mlpcopilot.command.builtin import register_builtin_commands
from mlpcopilot.command.router import CommandRouter
from mlpcopilot.session.manager import SessionManager


class _FakeLoop:
    def __init__(self, workspace, exec_tool=None):
        self.workspace = workspace
        self.sessions = SessionManager(workspace)
        self.commands = CommandRouter()
        self.model = "openai-codex/gpt-5.4-mini"
        self.provider = None
        self.context_window_tokens = 0
        self.tools = _FakeTools(exec_tool)
        self.consolidator = _FakeConsolidator()
        self.background_tasks = []
        self.direct_inputs = []
        register_builtin_commands(self.commands)

    async def process_direct(self, content, **kwargs):
        self.direct_inputs.append((content, kwargs))
        return OutboundMessage(
            channel=kwargs.get("channel", "cli"),
            chat_id=kwargs.get("chat_id", "direct"),
            content="continued after approval",
            metadata={},
        )

    async def _cancel_active_tasks(self, key: str) -> int:
        return 0

    def _apply_provider_snapshot(self, snapshot) -> None:
        self.provider = snapshot.provider
        self.model = snapshot.model
        self.context_window_tokens = snapshot.context_window_tokens

    def mcp_status(self):
        return {"state": "disconnected", "connected_count": 0, "configured_count": 0}

    def _schedule_background(self, awaitable):
        self.background_tasks.append(awaitable)
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()


class _FakeTools:
    def __init__(self, exec_tool=None):
        self.exec_tool = exec_tool

    def get(self, name: str):
        if name == "exec":
            return self.exec_tool
        return None


class _FakeConsolidator:
    async def archive(self, snapshot):
        return None


class _FakeExecTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return "Exit code: 0\nstdout"


class _FakeInputBuffer:
    def __init__(self, text: str = ""):
        self.text = text
        self.reset_called = False
        self.complete_state = None
        self.calls = []
        self.applied_completion = None

    def reset(self):
        self.reset_called = True

    def load_history_if_not_yet_loaded(self):
        self.calls.append("load")

    def history_backward(self):
        self.calls.append("backward")

    def history_forward(self):
        self.calls.append("forward")

    def complete_previous(self):
        self.calls.append("complete_previous")

    def complete_next(self):
        self.calls.append("complete_next")

    def apply_completion(self, completion):
        self.applied_completion = completion
        self.text = completion.text


class _FakeInputBox:
    def __init__(self, buffer):
        self.buffer = buffer


class _FakeCompletionState:
    def __init__(self, current_completion):
        self.current_completion = current_completion


class _FakeQueue:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)

    def qsize(self):
        return len(self.items)


class _FakeTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True
