"""Picker actions for jobs, layouts, and models in the TUI input controller."""

from __future__ import annotations

from mlpcopilot.runtime.tui.overlays.job_picker import job_picker_jobs, selected_job
from mlpcopilot.runtime.tui.overlays.layout_picker import (
    layout_picker_specs,
    selected_layout,
    sync_layout_picker_selection,
)
from mlpcopilot.runtime.tui.overlays.model_picker import (
    model_picker_models,
    selected_model,
    sync_model_picker_selection,
)


class TuiPickerActions:
    """Mixin containing job, layout, and model picker actions."""

    def toggle_job_picker(self) -> None:
        if self.state.is_overlay_open("job_picker"):
            self.state.close_overlay("job_picker")
        elif job_picker_jobs(self.config.workspace_path):
            self.state.job_picker_selection = 0
            self.state.open_overlay("job_picker")
        else:
            self.state.add_chat("system", "Jobs: none.")
        self.invalidate()

    def move_job_picker_selection(self, delta: int) -> None:
        jobs = job_picker_jobs(self.config.workspace_path)
        if not jobs:
            return
        self.state.job_picker_selection = (
            self.state.job_picker_selection + delta
        ) % len(jobs)
        self.invalidate()

    def stop_selected_job(self) -> None:
        jobs = job_picker_jobs(self.config.workspace_path)
        job = selected_job(self.state, jobs)
        if job is None:
            self.state.add_chat("system", "Jobs: none.")
            self.state.close_overlay("job_picker")
            self.invalidate()
            return
        from mlpcopilot.runtime.tui.commands.command_runtime import stop_tui_job
        from mlpcopilot.runtime.tui.views.logs import save_persisted_tool_log

        result = stop_tui_job(self.config, job.job_id, state=self.state)
        self.state.add_chat("system", result)
        if self.state.tool_log:
            save_persisted_tool_log(
                self.config.workspace_path,
                self.state.tool_log,
                session_id=self.state.active_session_id,
            )
        self.invalidate()

    def open_layout_picker(self) -> None:
        sync_layout_picker_selection(self.state)
        self.state.open_overlay("layout_picker")
        self.invalidate()

    def toggle_layout_picker(self) -> None:
        if self.state.is_overlay_open("layout_picker"):
            self.state.close_overlay("layout_picker")
        else:
            self.open_layout_picker()
            return
        self.invalidate()

    def move_layout_picker_selection(self, delta: int) -> None:
        specs = layout_picker_specs()
        if not specs:
            return
        self.state.layout_picker_selection = (
            self.state.layout_picker_selection + delta
        ) % len(specs)
        self.invalidate()

    def accept_layout_picker_selection(self) -> None:
        spec = selected_layout(self.state, layout_picker_specs())
        if spec is None:
            self.state.add_chat("system", "Layouts: none.")
            self.state.close_overlay("layout_picker")
            self.invalidate()
            return
        from mlpcopilot.runtime.tui.commands.command_runtime import switch_tui_layout

        result = switch_tui_layout(self.state, spec.name, workspace=self.config.workspace_path)
        self.state.add_chat("system", result)
        self.state.close_overlay("layout_picker")
        self.invalidate()

    def open_model_picker(self) -> None:
        if self.state.running:
            self.state.add_chat("system", "/model is disabled while a task is running.")
            self.invalidate()
            return
        sync_model_picker_selection(self.state, self.config)
        self.state.open_overlay("model_picker")
        self.invalidate()

    def toggle_model_picker(self) -> None:
        if self.state.is_overlay_open("model_picker"):
            self.state.close_overlay("model_picker")
        else:
            self.open_model_picker()
            return
        self.invalidate()

    def move_model_picker_selection(self, delta: int) -> None:
        models = model_picker_models(self.config)
        if not models:
            return
        self.state.model_picker_selection = (
            self.state.model_picker_selection + delta
        ) % len(models)
        self.invalidate()

    def accept_model_picker_selection(self) -> None:
        model = selected_model(self.state, model_picker_models(self.config))
        if model is None:
            self.state.add_chat("system", "Models: none.")
            self.state.close_overlay("model_picker")
            self.invalidate()
            return
        from mlpcopilot.runtime.tui.commands.command_runtime import switch_tui_model

        result = switch_tui_model(self.config, self.agent_loop, model) if self.agent_loop is not None else (
            "Error: /model <model> requires an active TUI runtime"
        )
        self.state.add_chat("system", result)
        self.state.close_overlay("model_picker")
        self.invalidate()
