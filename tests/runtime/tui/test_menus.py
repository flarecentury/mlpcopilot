from .common import *  # noqa: F403


def test_tui_slash_menu_candidates_follow_registry_and_running_gate() -> None:
    idle = slash_menu_candidates("/mo", running=False)
    running = slash_menu_candidates("/mo", running=True)

    assert [command.name for command in idle] == ["/model"]
    assert running == []
    assert slash_menu_candidates("/status now", running=False) == []

def test_tui_slash_menu_render_marks_selection() -> None:
    state = RuntimeTuiState(slash_menu_selection=1)

    output = _render_slash_menu_ansi(state, "/", width=90, height=6)

    assert "slash commands" in output
    assert "> /reject" in output
    assert "/approve" in output
    assert "Enter confirm" in output

def test_tui_input_controller_drives_slash_menu_selection(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    buffer = _FakeInputBuffer("/")
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )
    controller.input_box = _FakeInputBox(buffer)

    assert controller.slash_menu_is_open() is True
    controller.move_slash_menu_selection(1)
    assert state.slash_menu_selection == 1
    controller.close_slash_menu()

    assert slash_menu_visible(state, buffer.text) is False
    buffer.text = "/s"
    assert controller.slash_menu_is_open() is True

def test_tui_history_recalled_slash_command_does_not_trap_up_down(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    buffer = _FakeInputBuffer("")

    def history_backward() -> None:
        buffer.calls.append("backward")
        buffer.text = "/status"

    buffer.history_backward = history_backward
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )
    controller.input_box = _FakeInputBox(buffer)

    controller.navigate_history(buffer, -1)

    assert buffer.calls == ["load", "backward"]
    assert buffer.text == "/status"
    assert controller.slash_menu_is_open() is False

    buffer.text = "/sta"
    assert controller.slash_menu_is_open() is True

def test_tui_input_controller_accepts_slash_menu_no_arg_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    buffer = _FakeInputBuffer("/sta")
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )
    controller.input_box = _FakeInputBox(buffer)

    controller.accept_slash_menu_selection(buffer)

    assert buffer.text == "/status"
    assert buffer.reset_called is True
    assert state.chat[0].content == "/status"
    assert "profile=mlpcopilot" in state.chat[1].content

def test_tui_input_controller_accepts_slash_menu_arg_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    buffer = _FakeInputBuffer("/app")
    queue = _FakeQueue()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref={},
    )
    controller.input_box = _FakeInputBox(buffer)

    controller.accept_slash_menu_selection(buffer)

    assert buffer.text == "/approve "
    assert buffer.reset_called is False
    assert queue.items == []
    assert state.chat == []

def test_tui_layout_picker_renders_current_layout() -> None:
    state = RuntimeTuiState(layout_name="compact", layout_picker_selection=1)

    output = _render_layout_picker_ansi(
        state,
        list_tui_layout_specs(),
        width=100,
        height=8,
    )

    assert "layouts | Up/Down select" in output
    assert "Current: compact" in output
    assert ">* compact" in output
    assert "campaign_focus" in output

def test_tui_input_controller_opens_layout_picker_from_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(layout_name="campaign_focus")
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.submit("/layout")

    assert state.chat[0].content == "/layout"
    assert state.overlay_stack == ["layout_picker"]
    assert controller.active_overlay_id() == "layout_picker"
    assert state.layout_picker_selection == 2

def test_tui_model_picker_renders_current_model(tmp_path) -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "workspace": str(tmp_path),
                    "model": "openai-codex/gpt-5.4-mini",
                }
            },
        }
    )
    state = RuntimeTuiState(model_picker_selection=1)

    output = _render_model_picker_ansi(
        state,
        config,
        width=100,
        height=8,
    )

    assert "models | Up/Down select" in output
    assert "Current: openai-codex/gpt-5.4-mini" in output
    assert " * openai-codex/gpt-5.4-mini" in output
    assert ">  openai-codex/gpt-5.3-codex" in output

def test_tui_input_controller_opens_model_picker_from_command(tmp_path) -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "workspace": str(tmp_path),
                    "model": "openai-codex/gpt-5.4-mini",
                }
            },
        }
    )
    state = RuntimeTuiState()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
        agent_loop=_FakeLoop(tmp_path),
    )

    controller.submit("/model")

    assert state.chat[0].content == "/model"
    assert state.overlay_stack == ["model_picker"]
    assert controller.active_overlay_id() == "model_picker"
    assert state.model_picker_selection == 0

def test_tui_input_controller_blocks_model_picker_while_running(tmp_path) -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "workspace": str(tmp_path),
                    "model": "openai-codex/gpt-5.4-mini",
                }
            },
        }
    )
    state = RuntimeTuiState(running=True)
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
        agent_loop=_FakeLoop(tmp_path),
    )

    controller.submit("/model")

    assert state.overlay_stack == []
    assert state.chat[-1].content == "/model is disabled while a task is running."
