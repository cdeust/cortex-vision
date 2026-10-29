"""Synthetic adapter fixtures exercise Python contracts, never physical capture."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastmcp import Client

from cortex_vision.__main__ import mcp
from cortex_vision.vision import helper, intent

ERROR = helper.VisionHelperError

@pytest.mark.parametrize("text, expected", [
    ("", "remember"), ("Remember the release?", "remember"),
    ("please save this fact", "remember"), ("What changed?", "recall"),
    ("please look up the release", "recall"), ("who owns the release", "recall"),
    ("The release ships today", "remember"),
])
def test_classification(text, expected):
    assert intent.classify(text) == expected


def test_tags():
    assert intent.suggest_tags("Remember the release release alpha beta", limit=2) == ["release", "alpha"]
    assert intent.suggest_tags("the and or") == []


def test_plugin_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    assert helper._plugin_root() == Path(helper.__file__).resolve().parents[2]
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert helper._plugin_root() == tmp_path
    assert helper._bin_dir() == tmp_path / "deps" / "bin"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    assert helper._bin_dir() == tmp_path / "data" / "bin"


@pytest.mark.parametrize("result", [SimpleNamespace(returncode=0, stdout="/usr/bin/swiftc"), SimpleNamespace(returncode=1, stdout="")])
def test_compiler_selection(monkeypatch, result):
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: result)
    assert helper._swiftc_cmd() == (["xcrun", "swiftc"] if result.returncode == 0 else ["swiftc"])


def test_compiler_absent(monkeypatch):
    def missing(*a, **kw):
        raise FileNotFoundError
    monkeypatch.setattr(helper.subprocess, "run", missing)
    assert helper._swiftc_cmd() == ["swiftc"]


def test_platform_rejection(monkeypatch):
    monkeypatch.setattr(helper.sys, "platform", "linux")
    with pytest.raises(ERROR, match="requires macOS"):
        helper.ensure_binary()


def test_build_and_cached_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(helper.sys, "platform", "darwin")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    with pytest.raises(ERROR, match="source missing"):
        helper.ensure_binary()
    src = tmp_path / "scripts" / "viscap.swift"
    src.parent.mkdir()
    src.write_text("// synthetic compiler fixture")
    monkeypatch.setattr(helper, "_swiftc_cmd", lambda: ["swiftc"])
    calls = []
    def compile_or_sign(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "swiftc":
            Path(cmd[cmd.index("-o") + 1]).write_text("synthetic executable")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(helper.subprocess, "run", compile_or_sign)
    binary = helper.ensure_binary()
    assert binary.name == "viscap"
    assert "Vision" in calls[0]
    assert calls[1] == ["codesign", "--force", "--sign", "-", str(binary)]
    assert helper.ensure_binary() == binary
    assert len(calls) == 2
    binary.unlink()
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="fixture compile error", stdout=""))
    with pytest.raises(ERROR, match="fixture compile error"):
        helper.ensure_binary()


@pytest.mark.parametrize("stdout, stderr, message", [
    ("", "fixture stderr", "no output"), ("not-json", "", "non-JSON"),
    ('{"error":"permission denied"}', "", "permission denied"),
])
def test_helper_output_errors(monkeypatch, stdout, stderr, message):
    monkeypatch.setattr(helper, "ensure_binary", lambda: Path("viscap"))
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=stdout, stderr=stderr))
    with pytest.raises(ERROR, match=message):
        helper._run(["--check-auth"], 90)


def test_helper_timeout(monkeypatch):
    monkeypatch.setattr(helper, "ensure_binary", lambda: Path("viscap"))
    def expired(*a, **kw):
        raise subprocess.TimeoutExpired("fixture", 90)
    monkeypatch.setattr(helper.subprocess, "run", expired)
    with pytest.raises(ERROR, match="timed out"):
        helper.check_auth()


def test_helper_last_json_line(monkeypatch):
    monkeypatch.setattr(helper, "ensure_binary", lambda: Path("viscap"))
    run = Mock(return_value=SimpleNamespace(stdout='diagnostic\n{"authorized":true}\n'))
    monkeypatch.setattr(helper.subprocess, "run", run)
    assert helper.check_auth() == {"authorized": True}
    assert run.call_args.args[0] == ["viscap", "--check-auth"]


@pytest.mark.parametrize("stage", ["compile", "auth"])
def test_setup_errors(monkeypatch, stage):
    def failed():
        raise ERROR("fixture failure")
    monkeypatch.setattr(helper, "ensure_binary", failed if stage == "compile" else lambda: Path("viscap"))
    monkeypatch.setattr(helper, "check_auth", failed)
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("check_vision_setup", {})).data
            assert result["ok"] is False
            assert result["error"] == "fixture failure"
            assert ("binary" in result) == (stage == "auth")
    import asyncio
    asyncio.run(exercise())


@pytest.mark.parametrize("authorized", [True, False])
def test_setup_status(monkeypatch, authorized):
    monkeypatch.setattr(helper, "ensure_binary", lambda: Path("viscap"))
    status = "authorized" if authorized else "denied"
    monkeypatch.setattr(helper, "check_auth", lambda: {"camera_auth": status, "screen_recording": status})
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("check_vision_setup", {})).data
            assert result["ok"] == authorized
            assert bool(result["hint"]) != authorized
    import asyncio
    asyncio.run(exercise())


def test_entrypoint(monkeypatch):
    from cortex_vision import __main__ as entry
    signal = Mock()
    run = Mock()
    monkeypatch.setattr(entry.signal, "signal", signal)
    monkeypatch.setattr(entry.mcp, "run", run)
    entry.main()
    assert signal.call_count == 2
    run.assert_called_once_with(transport="stdio")
    with pytest.raises(SystemExit) as exc:
        entry._shutdown()
    assert exc.value.code == 0

@pytest.mark.parametrize("mode, text, expected", [
    ("auto", "What changed?", "recall"), ("auto", "Release ready", "remember"),
    ("recall", "Release ready", "recall"), ("remember", "What changed?", "remember"),
    ("invalid", "Release ready", "remember"),
])
def test_routing(monkeypatch, mode, text, expected):
    capture = Mock(return_value={"text":text, "on_device":True})
    monkeypatch.setattr(helper, "capture", capture)
    monkeypatch.setenv("VISION_DEFAULT_MODE", "invalid")
    async def exercise():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools} == {"look", "check_vision_setup"}
            result = (await client.call_tool("look", {"mode": mode})).data
            assert result["ok"] is True
            assert result["text"] == text
            assert result["intent"] == expected
            assert f"Cortex MCP {expected} tool" in result["next_action"]
            assert result["suggested_tags"]
    import asyncio
    asyncio.run(exercise())
    assert capture.call_count == 1


@pytest.mark.parametrize("failure", ["empty", "permission"])
def test_capture_failures(monkeypatch, failure):
    capture = Mock(return_value={})
    if failure == "permission":
        capture.side_effect = ERROR("fixture denied")
    monkeypatch.setattr(helper, "capture", capture)
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("look", {})).data
            assert result["ok"] is False
            assert result["error"] == ("no text, labels, or barcodes detected" if failure == "empty" else "fixture denied")
            if failure == "permission":
                assert "check_vision_setup" in result["hint"]
    import asyncio
    asyncio.run(exercise())

def test_capture_arguments(monkeypatch):
    run = Mock(return_value={"text": "fixture"})
    monkeypatch.setattr(helper, "_run", run)
    assert helper.capture("file", "ocr", "/fixture.png", "1,2,3,4", 7) == {"text": "fixture"}
    assert run.call_args.args[0] == ["--capture", "--source", "file", "--task", "ocr", "--max-results", "7", "--path", "/fixture.png", "--region", "1,2,3,4"]
    helper.capture("camera", "scene")
    assert run.call_args.kwargs["timeout"] == 45.0


@pytest.mark.parametrize("task, payload", [("scene", {"labels": [{"label": "forest"}]}), ("barcode", {"barcodes": [{"payload": "fixture"}]})])
def test_nontext_routing(monkeypatch, task, payload):
    monkeypatch.setattr(helper, "capture", Mock(return_value=payload))
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("look", {"task": task})).data
            assert result["ok"] is True
            assert result["suggested_tags"] == ["forest" if task == "scene" else "fixture"]
    import asyncio
    asyncio.run(exercise())


def test_file_requires_path():
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("look", {"source": "file"})).data
            assert result["ok"] is False
            assert "requires a 'path'" in result["error"]
    import asyncio
    asyncio.run(exercise())


@pytest.mark.parametrize("env_source, env_task", [("camera", "barcode"), ("invalid", "invalid")])
def test_environment_defaults(monkeypatch, env_source, env_task):
    monkeypatch.setenv("VISION_DEFAULT_SOURCE", env_source)
    monkeypatch.setenv("VISION_DEFAULT_TASK", env_task)
    monkeypatch.setenv("VISION_DEFAULT_MODE", "recall")
    capture = Mock(return_value={"text": "release"})
    monkeypatch.setattr(helper, "capture", capture)
    async def exercise():
        async with Client(mcp) as client:
            result = (await client.call_tool("look", {"mode": "invalid"})).data
            assert result["intent"] == "recall"
    import asyncio
    asyncio.run(exercise())
    assert capture.call_args.args[:2] == (("camera", "barcode") if env_source == "camera" else ("screen", "ocr"))
