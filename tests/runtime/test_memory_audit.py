from mlpcopilot.runtime.memory_audit import audit_workspace_memory, format_memory_audit_report


def test_memory_audit_flags_likely_stale_dpgen_state(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join([
            "# Memory",
            "- User prefers Apptainer SIFs under /opt/mlpcopilot/sifs.",
            "- Current status: iter.000021 stage0 make_train, next stage1 run_train.",
            "- Queue sub 8478 done 7562 rec 12 err 36.",
            "- dpdispatcher.log has traceback and keyboard interrupt.",
            "- Do not store current DP-GEN status in durable memory.",
        ]),
        encoding="utf-8",
    )

    path, findings = audit_workspace_memory(tmp_path)

    assert path == memory_dir / "MEMORY.md"
    assert [finding.category for finding in findings] == [
        "dpgen-iteration",
        "queue-counts",
        "transient-error",
    ]
    assert all("Do not store" not in finding.text for finding in findings)


def test_memory_audit_report_is_read_only_and_handles_clean_memory(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    memory_file = memory_dir / "MEMORY.md"
    memory_file.write_text(
        "- Use MCP status tools before reporting active DP-GEN state.\n",
        encoding="utf-8",
    )

    report = format_memory_audit_report(tmp_path)

    assert "Memory audit" in report
    assert "No likely stale runtime facts found." in report
    assert memory_file.read_text(encoding="utf-8") == (
        "- Use MCP status tools before reporting active DP-GEN state.\n"
    )


def test_memory_audit_report_handles_missing_memory_file(tmp_path) -> None:
    report = format_memory_audit_report(tmp_path)

    assert "No memory file found." in report
