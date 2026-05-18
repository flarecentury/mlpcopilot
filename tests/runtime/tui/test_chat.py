from .common import *  # noqa: F403


def test_tui_chat_renders_markdown_without_single_line_truncation() -> None:
    state = RuntimeTuiState()
    long_tail = "tail-marker-after-old-short-limit"
    state.add_chat(
        "assistant",
        "**Files**\n\n- First point\n- Second point\n\n" + ("x" * 240) + long_tail,
    )

    console = Console(record=True, width=100)
    console.print(_chat_renderable(state))
    output = console.export_text(styles=False)

    assert "Files" in output
    assert "**Files**" not in output
    assert "First point" in output
    assert "Second point" in output
    assert long_tail in output

def test_tui_exec_resume_output_renders_preformatted() -> None:
    state = RuntimeTuiState()
    state.add_chat(
        "system",
        "Approval apr_test marked approved\n\n"
        "Resumed exec after approval:\n"
        "      .-/+oossssoo+/-.               flare@host\n"
        "   `:+ssssssssssssssssss+:`           OS: Ubuntu",
    )

    renderable = _chat_message_renderable(state.chat[0])

    assert renderable.no_wrap is True
    assert ".-/+oossssoo+/-." in renderable.plain

def test_tui_approval_output_summary_renders_preformatted() -> None:
    state = RuntimeTuiState()
    state.add_chat(
        "system",
        "Approval apr_test marked approved\n"
        "exec \"neofetch\" completed OK in 0.10s.\n"
        "Output:\n"
        "      .-/+oossssoo+/-.               flare@host\n"
        "   `:+ssssssssssssssssss+:`           OS: Ubuntu",
    )

    renderable = _chat_message_renderable(state.chat[0])

    assert renderable.no_wrap is True
    assert ".-/+oossssoo+/-." in renderable.plain

def test_tui_approval_output_summary_strips_terminal_controls() -> None:
    state = RuntimeTuiState()
    state.add_chat(
        "system",
        "Approval apr_test marked approved\n"
        "exec \"neofetch\" completed OK in 0.10s.\n"
        "Output:\n"
        "\x1b[?25l\x1b[?7llogo\n"
        "\x1b[20A\x1b[9999999D\x1b[43C\x1b[31mCPU\x1b[0m: AMD",
    )

    renderable = _chat_message_renderable(state.chat[0])

    assert "\x1b[?25l" not in renderable.plain
    assert "\x1b[20A" not in renderable.plain
    assert "CPU: AMD" in renderable.plain

def test_tui_short_approval_prompt_collapses_extra_blank_line() -> None:
    state = RuntimeTuiState()
    state.add_chat(
        "assistant",
        "审批 ID: apr_f73803c33ccb\n\n"
        "请发送 /approve apr_f73803c33ccb 批准执行。",
    )

    renderable = _chat_message_renderable(state.chat[0])

    assert "\n\n" not in renderable.plain
    assert "审批 ID: apr_f73803c33ccb\n请发送 /approve" in renderable.plain

def test_tui_inline_approval_prompt_breaks_before_approval_command() -> None:
    state = RuntimeTuiState()
    state.add_chat(
        "assistant",
        "需要你的批准才能执行 sleep 3。 审批 ID: apr_f56618f8d421 "
        "请回复 /approve apr_f56618f8d421 或在终端运行 "
        "mlpcopilot mlp approve apr_f56618f8d421",
    )

    renderable = _chat_message_renderable(state.chat[0])

    assert "审批 ID: apr_f56618f8d421\n请回复 /approve" in renderable.plain
    assert "\n或在终端运行 mlpcopilot mlp approve apr_f56618f8d421" in renderable.plain

def test_tui_chat_scroll_slices_from_bottom() -> None:
    lines = [f"line-{idx}" for idx in range(10)]

    bottom = _slice_chat_lines_from_bottom(lines, height=4, scroll_from_bottom=0)
    scrolled = _slice_chat_lines_from_bottom(lines, height=4, scroll_from_bottom=3)

    assert _clamp_scroll_from_bottom(lines, height=4, scroll_from_bottom=999) == 6
    assert "older line(s) above" in bottom[0]
    assert bottom[-1] == "line-9"
    assert "older line(s) above" in scrolled[0]
    assert any("line-4" in line for line in scrolled)
    assert "newer line(s) below" in scrolled[-1]

def test_tui_chat_renderable_uses_viewport_scroll() -> None:
    state = RuntimeTuiState()
    state.add_chat("user", "\n".join(f"line-{idx}" for idx in range(20)))

    console = Console(record=True, width=80)
    console.print(_chat_renderable(state, viewport_width=60, viewport_height=5))
    bottom = console.export_text(styles=False)

    state.chat_scroll = 8
    console = Console(record=True, width=80)
    console.print(_chat_renderable(state, viewport_width=60, viewport_height=5))
    scrolled = console.export_text(styles=False)

    assert "line-19" in bottom
    assert "line-0" not in bottom
    assert "newer line(s) below" in scrolled
    assert "line-19" not in scrolled

def test_tui_chat_viewport_reserves_bottom_padding() -> None:
    state = RuntimeTuiState()
    state.add_chat("user", "\n".join(f"line-{idx}" for idx in range(20)))

    rendered = _chat_renderable(state, viewport_width=60, viewport_height=5)

    assert len(rendered.plain.splitlines()) == 4
    assert "line-19" in rendered.plain

def test_tui_chat_viewport_scrolls_all_retained_messages() -> None:
    state = RuntimeTuiState()
    for idx in range(12):
        state.add_chat("user", f"message-{idx}")

    console = Console(record=True, width=80)
    console.print(_chat_renderable(state, viewport_width=60, viewport_height=6))
    bottom = console.export_text(styles=False)

    state.chat_scroll = 999
    console = Console(record=True, width=80)
    console.print(_chat_renderable(state, viewport_width=60, viewport_height=6))
    scrolled = console.export_text(styles=False)

    assert "message-11" in bottom
    assert "message-0" not in bottom
    assert state.chat_scroll < 999
    assert "message-0" in scrolled
    assert "message-11" not in scrolled

def test_tui_chat_history_retains_more_than_initial_view() -> None:
    state = RuntimeTuiState()
    for idx in range(_CHAT_HISTORY_LIMIT + 5):
        state.add_chat("user", f"message-{idx}")

    assert len(state.chat) == _CHAT_HISTORY_LIMIT
    assert state.chat[0].content == "message-5"

def test_tui_chat_stream_appends_to_active_assistant_message() -> None:
    state = RuntimeTuiState()

    stream_index = state.start_chat_stream()
    stream_index = state.append_chat_stream(stream_index, "Hel")
    stream_index = state.append_chat_stream(stream_index, "lo")

    assert len(state.chat) == 1
    assert state.chat[0].role == "assistant"
    assert state.chat[0].content == "Hello"

def test_tui_chat_scroll_metrics_use_chat_viewport_size() -> None:
    state = RuntimeTuiState()
    for idx in range(20):
        state.add_chat("user", f"message-{idx}")

    page, max_scroll = _chat_scroll_metrics(
        state,
        terminal_width=100,
        terminal_height=30,
        has_pending=False,
    )

    assert 1 <= page < 20
    assert max_scroll > page

def test_tui_pager_opens_latest_message_and_scrolls() -> None:
    state = RuntimeTuiState()
    state.add_chat("user", "short")
    state.add_chat("assistant", "\n".join(f"poem line {idx}" for idx in range(20)))

    assert _open_pager_for_latest_message(state) is True
    first_page = _pager_ansi(state, width=80, height=8)
    state.pager_scroll = 10
    later_page = _pager_ansi(state, width=80, height=8)

    assert state.pager_open is False
    assert state.pager_message_index == 1
    assert "assistant message 2/2" in first_page
    assert "poem line 0" in first_page
    assert "poem line 0" not in later_page
    assert "poem line 10" in later_page

def test_tui_loads_existing_session_chat() -> None:
    session = Session(key="tui:default")
    session.add_message("user", "old question")
    session.add_message("assistant", "old answer")
    state = RuntimeTuiState()

    _load_session_chat(state, session)

    assert [(item.role, item.content) for item in state.chat] == [
        ("user", "old question"),
        ("assistant", "old answer"),
    ]
