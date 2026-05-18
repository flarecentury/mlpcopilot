from .common import *  # noqa: F403


def test_tui_accept_buffer_preserves_prompt_toolkit_history_append() -> None:
    submitted = []
    buffer = _FakeInputBuffer("hello")

    keep_text = _accept_tui_buffer(
        buffer,
        submit=submitted.append,
        has_pending_approval=lambda: False,
        submit_selected_approval_decision=lambda: submitted.append("selected"),
    )

    assert keep_text is False
    assert submitted == ["hello"]
    assert buffer.reset_called is False

def test_tui_accept_empty_buffer_uses_selected_approval() -> None:
    submitted = []
    buffer = _FakeInputBuffer("")

    keep_text = _accept_tui_buffer(
        buffer,
        submit=submitted.append,
        has_pending_approval=lambda: True,
        submit_selected_approval_decision=lambda: submitted.append("selected"),
    )

    assert keep_text is False
    assert submitted == ["selected"]
    assert buffer.reset_called is False

def test_tui_accept_buffer_applies_selected_completion_before_submit() -> None:
    from prompt_toolkit.completion import Completion

    submitted = []
    buffer = _FakeInputBuffer("/sta")
    completion = Completion("/status", start_position=-4)
    buffer.complete_state = _FakeCompletionState(completion)

    keep_text = _accept_tui_buffer(
        buffer,
        submit=submitted.append,
        has_pending_approval=lambda: False,
        submit_selected_approval_decision=lambda: submitted.append("selected"),
    )

    assert keep_text is False
    assert buffer.applied_completion is completion
    assert submitted == ["/status"]

def test_tui_navigates_input_history_and_completion_menu() -> None:
    buffer = _FakeInputBuffer()

    _navigate_input_history(buffer, -1)
    _navigate_input_history(buffer, 1)
    buffer.complete_state = object()
    _navigate_input_history(buffer, -1)
    _navigate_input_history(buffer, 1)

    assert buffer.calls == [
        "load",
        "backward",
        "load",
        "forward",
        "complete_previous",
        "complete_next",
    ]

def test_tui_keymap_builds_expected_bindings(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    controller = TuiInputController(
        config=config,
        state=RuntimeTuiState(),
        queue=_FakeQueue(),
        app_ref={},
    )

    bindings = build_tui_key_bindings(controller=controller, state=controller.state)

    key_sets = {tuple(binding.keys) for binding in bindings.bindings}
    assert ("c-y",) in key_sets
    assert ("f2",) in key_sets
    assert ("escape",) in key_sets
    assert any(str(key) in {"Keys.ControlM", "enter", "c-m"} for keys in key_sets for key in keys)
    assert ("c-t",) in key_sets
    assert ("c-l",) in key_sets
    assert ("c-p",) in key_sets
    assert ("c-o",) in key_sets
    assert ("f6",) in key_sets
    assert any(str(key) in {"Keys.ControlI", "c-i", "tab"} for keys in key_sets for key in keys)
    assert ("pageup",) in key_sets
    assert ("pagedown",) in key_sets

def test_tui_keymap_supports_configured_shortcuts(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
            "tui": {
                "keymap": {
                    "pager": "f7",
                    "toolLog": ["f8", "ctrl-x ctrl-t"],
                    "jobs": ["f9"],
                    "layout": [],
                }
            },
        }
    )
    controller = TuiInputController(
        config=config,
        state=RuntimeTuiState(),
        queue=_FakeQueue(),
        app_ref={},
    )

    bindings = build_tui_key_bindings(
        controller=controller,
        state=controller.state,
        config=config,
    )

    key_sets = {tuple(binding.keys) for binding in bindings.bindings}
    assert ("f7",) in key_sets
    assert ("f8",) in key_sets
    assert ("c-x", "c-t") in key_sets
    assert ("f9",) in key_sets
    assert ("c-t",) not in key_sets
    assert ("c-l",) not in key_sets
    assert ("c-p",) not in key_sets
    assert ("c-o",) not in key_sets

def test_tui_overlay_priority_prefers_approval() -> None:
    assert active_tui_overlay_id(approval_pending=False, pager_open=False) is None
    assert active_tui_overlay_id(approval_pending=False, pager_open=True) == "pager"
    assert (
        active_tui_overlay_id(
            approval_pending=False,
            pager_open=False,
            tool_log_pager_open=True,
        )
        == "tool_log_pager"
    )
    assert (
        active_tui_overlay_id(
            approval_pending=False,
            pager_open=True,
            tool_log_pager_open=True,
            overlay_stack=["pager", "tool_log_pager"],
        )
        == "tool_log_pager"
    )
    assert (
        active_tui_overlay_id(
            approval_pending=False,
            pager_open=False,
            overlay_stack=["job_picker"],
        )
        == "job_picker"
    )
    assert (
        active_tui_overlay_id(
            approval_pending=False,
            pager_open=False,
            overlay_stack=["layout_picker"],
        )
        == "layout_picker"
    )
    assert (
        active_tui_overlay_id(
            approval_pending=False,
            pager_open=False,
            overlay_stack=["model_picker"],
        )
        == "model_picker"
    )
    assert active_tui_overlay_id(approval_pending=True, pager_open=True) == "approval"

def test_tui_overlay_specs_drive_escape_close_behavior() -> None:
    assert get_tui_overlay_spec("approval").blocks_input is True
    assert is_tui_overlay_esc_closable("approval") is False
    assert is_tui_overlay_esc_closable("pager") is True
    assert is_tui_overlay_esc_closable("tool_log_pager") is True
    assert is_tui_overlay_esc_closable("job_picker") is True
    assert is_tui_overlay_esc_closable("layout_picker") is True
    assert is_tui_overlay_esc_closable("model_picker") is True
    assert is_tui_overlay_esc_closable("missing") is False

def test_tui_input_controller_reports_active_overlay(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(pager_open=True)
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    assert controller.active_overlay_id() == "pager"
    assert controller.overlay_is("pager") is True
    ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approve exec",
        request="Run a command",
    )
    assert controller.active_overlay_id() == "approval"
    assert controller.overlay_is("approval") is True

def test_tui_prompt_layout_pager_filter_respects_overlay_priority(tmp_path) -> None:
    sync_mlpcopilot_workspace(tmp_path, silent=True)
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(pager_open=True)
    pager_filter = _active_overlay_filter(config, state, "pager")

    assert pager_filter() is True
    ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approve exec",
        request="Run a command",
    )
    assert pager_filter() is False

def test_tui_input_controller_toggles_pager_overlay(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    state.add_chat("assistant", "long message")
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.toggle_pager()

    assert state.overlay_stack == ["pager"]
    assert state.pager_open is True
    assert controller.active_overlay_id() == "pager"

    controller.toggle_pager()

    assert state.overlay_stack == []
    assert state.pager_open is False

def test_tui_input_controller_closes_esc_closable_overlay_by_spec(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    state.open_overlay("model_picker")
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.close_active_pager()

    assert state.overlay_stack == []

def test_tui_input_controller_toggles_tool_log_pager_overlay(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState(tool_log=[ToolLogEntry(name="exec", status="ok", detail="ls")])
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.toggle_tool_log_pager()

    assert state.overlay_stack == ["tool_log_pager"]
    assert state.is_overlay_open("tool_log_pager") is True
    assert controller.active_overlay_id() == "tool_log_pager"

    controller.toggle_tool_log_pager()

    assert state.overlay_stack == []
    assert state.is_overlay_open("tool_log_pager") is False

def test_tui_input_controller_reports_empty_tool_log_pager(tmp_path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(tmp_path)}},
        }
    )
    state = RuntimeTuiState()
    controller = TuiInputController(
        config=config,
        state=state,
        queue=_FakeQueue(),
        app_ref={},
    )

    controller.toggle_tool_log_pager()

    assert state.overlay_stack == []
    assert state.chat[-1].role == "system"
    assert state.chat[-1].content == "No tool log entries are available."
