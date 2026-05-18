"""Prompt-toolkit key bindings for the MLP Copilot TUI."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings

from mlpcopilot.runtime.tui.overlays import is_tui_overlay_esc_closable
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.runtime.tui.input.input_controller import TuiInputController

DEFAULT_TUI_KEYMAP: dict[str, list[str]] = {
    "quit": ["c-c", "c-d"],
    "approve": ["c-y", "f2"],
    "reject": ["c-n", "f3"],
    "changes": ["f4"],
    "pager": ["c-t"],
    "tool_log": ["c-l"],
    "jobs": ["c-p"],
    "layout": ["c-o"],
    "model": ["f6"],
}

_ACTION_ALIASES = {
    "toolLog": "tool_log",
    "tool-log": "tool_log",
    "jobPicker": "jobs",
    "layoutPicker": "layout",
    "modelPicker": "model",
}

_KEY_ALIASES = {
    "ctrl": "c",
    "control": "c",
    "esc": "escape",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "page-up": "pageup",
    "page-down": "pagedown",
}

_KEY_LABELS = {
    "c-c": "Ctrl-C",
    "c-d": "Ctrl-D",
    "c-l": "Ctrl-L",
    "c-n": "Ctrl-N",
    "c-o": "Ctrl-O",
    "c-p": "Ctrl-P",
    "c-t": "Ctrl-T",
    "c-y": "Ctrl-Y",
    "escape": "Esc",
    "pageup": "PgUp",
    "pagedown": "PgDn",
}


def approval_pending_filter(controller: TuiInputController) -> Condition:
    return Condition(lambda: controller.overlay_is("approval"))


def pager_open_filter(state: RuntimeTuiState) -> Condition:
    return Condition(lambda: state.is_overlay_open("pager") or state.is_overlay_open("tool_log_pager"))


def build_tui_key_bindings(
    *,
    controller: TuiInputController,
    state: RuntimeTuiState,
    config: Any | None = None,
) -> KeyBindings:
    """Build the interactive TUI key map.

    The handlers intentionally stay thin: all state mutation lives in
    TuiInputController so this module only defines the user interaction contract.
    """
    key_bindings = KeyBindings()
    keymap = resolved_tui_keymap(config or controller.config)
    approval_pending = approval_pending_filter(controller)
    pager_is_open = Condition(lambda: controller.overlay_is("pager") or controller.overlay_is("tool_log_pager"))
    job_picker_is_open = Condition(lambda: controller.overlay_is("job_picker"))
    layout_picker_is_open = Condition(lambda: controller.overlay_is("layout_picker"))
    model_picker_is_open = Condition(lambda: controller.overlay_is("model_picker"))
    closable_overlay_is_open = Condition(
        lambda: is_tui_overlay_esc_closable(controller.active_overlay_id())
    )
    slash_menu_is_open = Condition(lambda: controller.slash_menu_is_open())

    @_bind_action(key_bindings, keymap, "quit")
    def _exit(event: Any) -> None:
        event.app.exit()

    @_bind_action(key_bindings, keymap, "approve")
    def _approve_first_pending(event: Any) -> None:
        controller.submit_approval_decision("approve")

    @_bind_action(key_bindings, keymap, "reject")
    def _reject_first_pending(event: Any) -> None:
        controller.submit_approval_decision("reject")

    @_bind_action(key_bindings, keymap, "changes")
    def _changes_first_pending(event: Any) -> None:
        controller.submit_approval_decision("changes")

    @key_bindings.add("up", filter=approval_pending)
    @key_bindings.add("left", filter=approval_pending)
    def _approval_previous(event: Any) -> None:
        controller.move_approval_selection(-1)

    @key_bindings.add("down", filter=approval_pending)
    @key_bindings.add("right", filter=approval_pending)
    def _approval_next(event: Any) -> None:
        controller.move_approval_selection(1)

    @key_bindings.add("escape", filter=approval_pending, eager=True)
    def _reject_with_escape(event: Any) -> None:
        controller.submit_approval_decision("reject")

    @_bind_action(key_bindings, keymap, "pager")
    def _toggle_pager(event: Any) -> None:
        controller.toggle_pager()

    @_bind_action(key_bindings, keymap, "tool_log")
    def _toggle_tool_log_pager(event: Any) -> None:
        controller.toggle_tool_log_pager()

    @_bind_action(key_bindings, keymap, "jobs")
    def _toggle_job_picker(event: Any) -> None:
        controller.toggle_job_picker()

    @_bind_action(key_bindings, keymap, "layout")
    def _toggle_layout_picker(event: Any) -> None:
        controller.toggle_layout_picker()

    @_bind_action(key_bindings, keymap, "model")
    def _toggle_model_picker(event: Any) -> None:
        controller.toggle_model_picker()

    @key_bindings.add("escape", filter=closable_overlay_is_open, eager=True)
    def _close_overlay(event: Any) -> None:
        controller.close_active_pager()

    @key_bindings.add("escape", filter=slash_menu_is_open, eager=True)
    def _close_slash_menu(event: Any) -> None:
        controller.close_slash_menu()

    @key_bindings.add("enter", filter=slash_menu_is_open, eager=True)
    def _accept_slash_menu(event: Any) -> None:
        controller.accept_slash_menu_selection(event.current_buffer)

    @key_bindings.add("up", filter=pager_is_open)
    def _pager_line_up(event: Any) -> None:
        controller.move_pager_scroll(-1)

    @key_bindings.add("down", filter=pager_is_open)
    def _pager_line_down(event: Any) -> None:
        controller.move_pager_scroll(1)

    @key_bindings.add("up", filter=job_picker_is_open)
    def _job_picker_previous(event: Any) -> None:
        controller.move_job_picker_selection(-1)

    @key_bindings.add("down", filter=job_picker_is_open)
    def _job_picker_next(event: Any) -> None:
        controller.move_job_picker_selection(1)

    @key_bindings.add("enter", filter=job_picker_is_open, eager=True)
    def _stop_selected_job(event: Any) -> None:
        controller.stop_selected_job()

    @key_bindings.add("up", filter=layout_picker_is_open)
    def _layout_picker_previous(event: Any) -> None:
        controller.move_layout_picker_selection(-1)

    @key_bindings.add("down", filter=layout_picker_is_open)
    def _layout_picker_next(event: Any) -> None:
        controller.move_layout_picker_selection(1)

    @key_bindings.add("enter", filter=layout_picker_is_open, eager=True)
    def _switch_selected_layout(event: Any) -> None:
        controller.accept_layout_picker_selection()

    @key_bindings.add("up", filter=model_picker_is_open)
    def _model_picker_previous(event: Any) -> None:
        controller.move_model_picker_selection(-1)

    @key_bindings.add("down", filter=model_picker_is_open)
    def _model_picker_next(event: Any) -> None:
        controller.move_model_picker_selection(1)

    @key_bindings.add("enter", filter=model_picker_is_open, eager=True)
    def _switch_selected_model(event: Any) -> None:
        controller.accept_model_picker_selection()

    @key_bindings.add("pageup", filter=pager_is_open)
    def _pager_page_up(event: Any) -> None:
        controller.move_pager_scroll(-controller.page_size())

    @key_bindings.add("pagedown", filter=pager_is_open)
    def _pager_page_down(event: Any) -> None:
        controller.move_pager_scroll(controller.page_size())

    @key_bindings.add("home", filter=pager_is_open)
    def _pager_home(event: Any) -> None:
        controller.pager_home()

    @key_bindings.add("end", filter=pager_is_open)
    def _pager_end(event: Any) -> None:
        controller.pager_end()

    @key_bindings.add("pageup", filter=~closable_overlay_is_open & ~approval_pending)
    def _chat_page_up(event: Any) -> None:
        controller.move_chat_page(1)

    @key_bindings.add("pagedown", filter=~closable_overlay_is_open & ~approval_pending)
    def _chat_page_down(event: Any) -> None:
        controller.move_chat_page(-1)

    @key_bindings.add("up", filter=slash_menu_is_open)
    def _slash_menu_previous(event: Any) -> None:
        controller.move_slash_menu_selection(-1)

    @key_bindings.add("down", filter=slash_menu_is_open)
    def _slash_menu_next(event: Any) -> None:
        controller.move_slash_menu_selection(1)

    @key_bindings.add("up", filter=~approval_pending & ~closable_overlay_is_open & ~slash_menu_is_open)
    def _history_previous(event: Any) -> None:
        controller.navigate_history(event.current_buffer, -1)

    @key_bindings.add("down", filter=~approval_pending & ~closable_overlay_is_open & ~slash_menu_is_open)
    def _history_next(event: Any) -> None:
        controller.navigate_history(event.current_buffer, 1)

    @key_bindings.add("tab")
    def _complete(event: Any) -> None:
        controller.complete(event.current_buffer)

    return key_bindings


def resolved_tui_keymap(config: Any | None) -> dict[str, list[str]]:
    """Return the TUI keymap after applying user overrides."""
    keymap = {action: list(keys) for action, keys in DEFAULT_TUI_KEYMAP.items()}
    configured = getattr(getattr(config, "tui", None), "keymap", None)
    if not isinstance(configured, dict):
        return keymap
    for raw_action, raw_keys in configured.items():
        action = _canonical_action(str(raw_action))
        if action not in keymap:
            continue
        if isinstance(raw_keys, str):
            values = [raw_keys]
        elif isinstance(raw_keys, list):
            values = [item for item in raw_keys if isinstance(item, str)]
        else:
            continue
        keymap[action] = [_normalize_key_sequence(value) for value in values if value.strip()]
    return keymap


def tui_action_key_label(config: Any | None, action: str) -> str:
    """Return a compact display label for a configured TUI action."""
    keymap = resolved_tui_keymap(config)
    sequences = keymap.get(_canonical_action(action), [])
    if not sequences:
        return "-"
    return "/".join(_label_key_sequence(sequence) for sequence in sequences)


def _bind_action(
    key_bindings: KeyBindings,
    keymap: dict[str, list[str]],
    action: str,
    *,
    filter: Any | None = None,
    eager: bool = False,
) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]:
    def decorator(handler: Callable[[Any], None]) -> Callable[[Any], None]:
        for sequence in keymap.get(action, []):
            keys = tuple(part for part in sequence.split() if part)
            if not keys:
                continue
            kwargs: dict[str, Any] = {}
            if filter is not None:
                kwargs["filter"] = filter
            if eager:
                kwargs["eager"] = eager
            try:
                key_bindings.add(*keys, **kwargs)(handler)
            except Exception as exc:
                label = " ".join(keys)
                raise ValueError(f"Invalid TUI key binding for {action}: {label}") from exc
        return handler

    return decorator


def _canonical_action(action: str) -> str:
    return _ACTION_ALIASES.get(action, action)


def _normalize_key_sequence(value: str) -> str:
    return " ".join(_normalize_key_token(part) for part in value.replace(",", " ").split())


def _normalize_key_token(value: str) -> str:
    token = value.strip().lower().replace("_", "-")
    if token in _KEY_ALIASES:
        return _KEY_ALIASES[token]
    for prefix in ("ctrl-", "control-"):
        if token.startswith(prefix) and len(token) > len(prefix):
            return f"c-{token[len(prefix):]}"
    return token


def _label_key_sequence(sequence: str) -> str:
    return " ".join(_label_key_token(part) for part in sequence.split())


def _label_key_token(token: str) -> str:
    if token in _KEY_LABELS:
        return _KEY_LABELS[token]
    if token.startswith("c-") and len(token) > 2:
        return f"Ctrl-{token[2:].upper()}"
    if token.startswith("f") and token[1:].isdigit():
        return token.upper()
    if token in {"up", "down", "left", "right", "home", "end", "enter", "tab"}:
        return token.capitalize()
    return token
