#!/usr/bin/env python3
"""기능 집합에서 도출한 여러 CLI의 에이전트 권한을 동작 테스트로 검증한다."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_GENERATOR = REPO_ROOT / "scripts/generate-codex-agents.py"
OPENCODE_GENERATOR = REPO_ROOT / "scripts/sync-opencode.py"
ANTIGRAVITY_GENERATOR = (
    REPO_ROOT / "skills/story-setup/scripts/generate-antigravity-agents.mjs"
)
TEMPLATES = REPO_ROOT / "skills/story-setup/references/templates"
OPENCODE_BASELINE = REPO_ROOT / "skills/story-setup/references/opencode"


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def write_agent(
    directory: Path,
    name: str,
    tools: list[str],
    disallowed: list[str] | None = None,
) -> None:
    disallowed_line = (
        f"disallowedTools: [{', '.join(disallowed)}]\n" if disallowed else ""
    )
    write_raw_agent(
        directory, name, f"tools: [{', '.join(tools)}]\n{disallowed_line}"
    )


def write_raw_agent(directory: Path, name: str, capability_lines: str) -> None:
    text = (
        "---\n"
        f"name: {name}\n"
        f"description: {name} fixture\n"
        f"{capability_lines.rstrip()}\n"
        "maxTurns: 3\n"
        "---\n"
        f"# {name}\n\nCapability fixture.\n"
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(text, encoding="utf-8")


def codex_documents(directory: Path) -> dict[str, dict[str, object]]:
    return {
        path.stem: tomllib.loads(path.read_text(encoding="utf-8"))
        for path in directory.glob("*.toml")
    }


def opencode_permissions(path: Path) -> dict[str, str]:
    """생성된 2.x `permissions:` 규칙 목록을 규칙 순서대로 {action: effect}로 읽는다."""
    permissions: dict[str, str] = {}
    in_permissions = False
    action = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "permissions:":
            in_permissions = True
            continue
        if in_permissions and line.startswith("  "):
            key, _, value = line.strip().removeprefix("- ").partition(":")
            value = value.strip().strip('"')
            if key == "action":
                action = value
            elif key == "resource":
                assert value == "*", (path, line)
            elif key == "effect":
                permissions[action] = value
            continue
        if in_permissions:
            break
    return permissions


def antigravity_tools(path: Path) -> list[str]:
    tools: list[str] = []
    in_tools = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "tools:":
            in_tools = True
            continue
        if in_tools and line.startswith("  - "):
            tools.append(line.removeprefix("  - "))
            continue
        if in_tools:
            break
    return tools


def prepare_opencode_root(root: Path, source_agents: Path) -> Path:
    result = run_opencode_fixture(root, source_agents)
    assert result.returncode == 0, result.stdout + result.stderr
    return root / "skills/story-setup/references/opencode"


def run_opencode_fixture(root: Path, source_agents: Path) -> subprocess.CompletedProcess[str]:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(OPENCODE_GENERATOR, scripts / OPENCODE_GENERATOR.name)
    template_root = root / "skills/story-setup/references/templates"
    shutil.copytree(source_agents, template_root / "agents")
    (template_root / "CLAUDE.md.tmpl").write_text(
        "# Fixture instructions\n", encoding="utf-8"
    )
    return run(str(scripts / OPENCODE_GENERATOR.name), cwd=root)


def assert_invalid_capabilities_fail_before_publish(capability_lines: str) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-capability-invalid-") as tmp:
        root = Path(tmp)
        source = root / "sources"
        write_raw_agent(source, "invalid-capabilities", capability_lines)

        codex_dest = root / "codex"
        codex_dest.mkdir()
        codex_sentinel = codex_dest / "existing.toml"
        codex_sentinel.write_text("existing codex output\n", encoding="utf-8")
        result = run(
            str(CODEX_GENERATOR),
            "--source",
            str(source),
            "--dest",
            str(codex_dest),
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert codex_sentinel.read_text(encoding="utf-8") == "existing codex output\n"
        assert not (codex_dest / "invalid-capabilities.toml").exists()

        opencode_root = root / "opencode-fixture"
        opencode_dest = opencode_root / "skills/story-setup/references/opencode"
        (opencode_dest / "agents").mkdir(parents=True)
        opencode_sentinel = opencode_dest / "agents/existing.md"
        opencode_sentinel.write_text("existing opencode output\n", encoding="utf-8")
        result = run_opencode_fixture(opencode_root, source)
        assert result.returncode != 0, result.stdout + result.stderr
        assert (
            opencode_sentinel.read_text(encoding="utf-8")
            == "existing opencode output\n"
        )
        assert not (opencode_dest / "agents/invalid-capabilities.md").exists()

        antigravity_dest = root / "antigravity"
        antigravity_dest.mkdir()
        antigravity_sentinel = antigravity_dest / "existing.txt"
        antigravity_sentinel.write_text(
            "existing antigravity output\n", encoding="utf-8"
        )
        result = subprocess.run(
            [
                "node",
                str(ANTIGRAVITY_GENERATOR),
                "--source",
                str(source),
                "--dest",
                str(antigravity_dest),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert (
            antigravity_sentinel.read_text(encoding="utf-8")
            == "existing antigravity output\n"
        )
        assert not (antigravity_dest / "invalid-capabilities").exists()


def test_permissions_follow_capabilities_not_names() -> None:
    cases = {
        "renamed-reader": "tools: [Read, Glob, Grep]\ndisallowedTools: [Write, Edit, Bash]",
        "implicit-reader": "tools: [Read]",
        "renamed-writer": "tools: [Read, Write, Edit]",
        "write-without-edit": "tools: [Read, Write]\ndisallowedTools: [Edit]",
        "edit-without-write": "tools: [Read, Edit]\ndisallowedTools: [Write]",
        "shell-reader": "tools: [Read, Bash]",
        "denials-win": "tools: [Read, Write, Edit, Bash]\ndisallowedTools: [Write, Edit, Bash]",
        "story-researcher": "tools: [Read]\ndisallowedTools: [Write, Edit, Bash]",
        "mixed-read-like": "tools: [Read, Glob, Grep]\ndisallowedTools: [Read, Grep]",
    }
    with tempfile.TemporaryDirectory(prefix="agent-permissions-fixture-") as tmp:
        root = Path(tmp)
        source = root / "sources"
        for name, declaration in cases.items():
            write_raw_agent(source, name, declaration)
        result = run(str(CODEX_GENERATOR), "--source", str(source), "--dest", str(root / "codex"))
        assert result.returncode == 0, result.stdout + result.stderr
        codex = codex_documents(root / "codex")
        for name in ("renamed-reader", "implicit-reader", "denials-win", "story-researcher", "mixed-read-like"):
            assert codex[name].get("sandbox_mode") == "read-only", name
        for name in ("renamed-writer", "write-without-edit", "edit-without-write", "shell-reader"):
            assert "sandbox_mode" not in codex[name], name

        generated = prepare_opencode_root(root / "opencode", source)
        permissions = {
            path.stem: opencode_permissions(path)
            for path in (generated / "agents").glob("*.md")
        }
        reader = {"*": "deny", "read": "allow", "glob": "allow", "grep": "allow", "edit": "deny", "shell": "deny"}
        assert permissions["renamed-reader"] == reader
        only_read = {**reader, "glob": "deny", "grep": "deny"}
        for name in ("implicit-reader", "denials-win", "story-researcher"):
            assert permissions[name] == only_read, name
        assert permissions["mixed-read-like"] == {**reader, "read": "deny", "grep": "deny"}
        for name in ("renamed-writer", "write-without-edit", "edit-without-write"):
            assert permissions[name] == {**only_read, "edit": "allow"}, name
        assert permissions["shell-reader"] == {**only_read, "shell": "allow"}

        result = subprocess.run(
            ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(source), "--dest", str(root / "agy")],
            text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert antigravity_tools(root / "agy/denials-win/agent.md") == ["view_file"]
        assert antigravity_tools(root / "agy/mixed-read-like/agent.md") == ["find_by_name"]
        assert antigravity_tools(root / "agy/write-without-edit/agent.md") == ["view_file", "write_to_file"]
        assert antigravity_tools(root / "agy/edit-without-write/agent.md") == ["view_file", "replace_file_content", "multi_replace_file_content"]


def test_empty_and_inherited_tools_are_distinct() -> None:
    cases = {
        "empty": "tools: []",
        "all-denied": "tools: [Read, Glob, Grep]\ndisallowedTools: [Read, Glob, Grep]",
        "inherit": "",
        "inherit-minus-glob": "disallowedTools: [Glob, Write, Edit, Bash]",
    }
    with tempfile.TemporaryDirectory(prefix="agent-permissions-inheritance-") as tmp:
        root = Path(tmp)
        for name, declaration in cases.items():
            source = root / name / "sources"
            write_raw_agent(source, name, declaration)
            result = run(str(CODEX_GENERATOR), "--source", str(source), "--dest", str(root / name / "codex"))
            if name in {"empty", "all-denied"}:
                assert result.returncode != 0 and "zero effective tools" in result.stderr, result.stderr
                assert not (root / name / "codex").exists()
            else:
                assert result.returncode == 0, result.stderr
                assert "sandbox_mode" not in codex_documents(root / name / "codex")[name]
            generated = prepare_opencode_root(root / name / "opencode", source)
            permissions = opencode_permissions(generated / f"agents/{name}.md")
            if name in {"empty", "all-denied"}:
                assert permissions == {"*": "deny", "read": "deny", "glob": "deny", "grep": "deny", "edit": "deny", "shell": "deny"}
            elif name == "inherit":
                assert permissions == {}
            else:
                assert permissions == {"glob": "deny", "edit": "deny", "shell": "deny"}
            result = subprocess.run(
                ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(source), "--dest", str(root / name / "agy")],
                text=True, capture_output=True,
            )
            assert result.returncode != 0, name
            assert not (root / name / "agy").exists()


def test_codex_recognizes_other_mutating_tools() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-mutating-tools-") as tmp:
        root = Path(tmp)
        for tool in ("NotebookEdit", "PowerShell"):
            write_agent(root / "sources", tool, ["Read", tool])
            write_agent(root / "sources", f"denied-{tool}", ["Read", tool], [tool])
        result = run(str(CODEX_GENERATOR), "--source", str(root / "sources"), "--dest", str(root / "codex"))
        assert result.returncode == 0, result.stderr
        docs = codex_documents(root / "codex")
        for tool in ("NotebookEdit", "PowerShell"):
            assert "sandbox_mode" not in docs[tool]
            assert docs[f"denied-{tool}"]["sandbox_mode"] == "read-only"
        result = run_opencode_fixture(root / "opencode", root / "sources")
        assert result.returncode != 0 and "unsupported OpenCode capability" in result.stderr
        result = subprocess.run(
            ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(root / "sources"), "--dest", str(root / "agy")],
            text=True, capture_output=True,
        )
        assert result.returncode != 0 and "unsupported Antigravity capability" in result.stderr


def test_invalid_capability_declarations_fail_closed() -> None:
    cases = [
        "tools: [Read, NotARealTool]",
        "tools: [Read]\ndisallowedTools: [NotARealTool]",
        "tools: Read, Write",
        "tools: [Read, Write]\ndisallowedTools: [Write",
        "tools: []\ndisallowedTools: Write, Edit",
        'tools: ["Read", "Write"]junk',
        "tools:\n  - Read\n  - Write",
    ]
    for capability_lines in cases:
        assert_invalid_capabilities_fail_before_publish(capability_lines)


def test_opencode_runtime(cli: str) -> None:
    """`opencode run --agent`로 실제 OpenCode 2.x 도구 레지스트리를 시험한다.

    OpenCode 2.x는 마지막 일치 규칙이 전면 deny인 도구를 모델에 보내는 목록에서 제거하므로 모의 모델이
    받은 도구명이 런타임의 판단 결과다. 단, 2.2부터 skill과 Code Mode 도구는 직접 호출해 확인한다(아래 참고).
    몇 가지 지정된 도구 호출로 허용된 도구는 실제 실행되고 거부된 도구는 실행되지 않음을 입증한다.
    """
    with tempfile.TemporaryDirectory(prefix="opencode-agent-permissions-") as tmp:
        root = Path(tmp).resolve()
        source = root / "sources"
        for name, declaration in {
            "reader": "tools: [Read]",
            "glob-only": "tools: [Read, Glob, Grep]\ndisallowedTools: [Read, Grep]",
            "inherit-minus-glob": "disallowedTools: [Glob, Write, Edit, Bash]",
            "writer": "tools: [Read, Write]\ndisallowedTools: [Edit, Bash]",
            "shell": "tools: [Read, Bash]",
            "empty": "tools: []",
        }.items():
            write_raw_agent(source, name, declaration)
        generated = prepare_opencode_root(root / "generator", source)
        project = root / "project"
        shutil.copytree(generated / "agents", project / ".opencode/agents")
        shutil.copytree(OPENCODE_BASELINE / "agents", project / ".opencode/agents", dirs_exist_ok=True)
        (project / "canary.txt").write_text("PERMISSION_CANARY\n", encoding="utf-8")
        probe_skill = project / ".opencode/skills/probe/SKILL.md"
        probe_skill.parent.mkdir(parents=True)
        probe_skill.write_text("---\nname: probe\ndescription: Permission probe.\n---\n\nSKILL_CANARY\n", encoding="utf-8")
        # OpenCode는 현재 디렉터리부터 Git 저장소로 정의된 프로젝트 루트까지 올라가며 .opencode/를 찾는다.
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        home = root / "home"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENCODE_", "ANTHROPIC_", "OPENAI_", "XDG_"))}
        env["HOME"] = str(home)
        for kind in ("CONFIG", "DATA", "CACHE", "STATE"):
            env[f"XDG_{kind}_HOME"] = str(home / kind.lower())
        # `opencode run`은 $PWD를 세션 디렉터리로 쓴다. subprocess의 cwd=는 상속된 PWD를 바꾸지 않으므로 명시하지 않으면 호출자 디렉터리에서 실행된다.
        env["PWD"] = str(project)
        mock_log = root / "mock-requests.jsonl"
        mock_script = root / "mock-script.json"
        mock = subprocess.Popen(
            ["node", str(REPO_ROOT / "scripts/opencode-mock-llm.mjs")],
            env={**env, "MOCK_LOG": str(mock_log), "MOCK_SCRIPT": str(mock_script)},
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            port = int(mock.stdout.readline())
            config_dir = home / "config/opencode"
            config_dir.mkdir(parents=True)
            (config_dir / "opencode.json").write_text(json.dumps({
                "providers": {"mock": {
                    "name": "Mock",
                    "package": "@opencode/ai/providers/openai-compatible",
                    "settings": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "fixture"},
                    "models": {"probe": {"name": "probe"}},
                }},
            }), encoding="utf-8")

            # 백그라운드 서비스의 기본 고정 포트는 개발 머신의 기존 OpenCode 서비스와 충돌할 수 있으므로 격리된 HOME에 빈 포트를 지정한다.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                service_port = probe.getsockname()[1]
            subprocess.run([cli, "service", "set", "port", str(service_port)], env=env, check=True,
                           capture_output=True, timeout=60)
            # location의 에이전트는 비동기로 로드되므로 처음 시작한 서비스에서 `run --agent`가 로드보다 먼저 실행되어 Agent not found가 날 수 있다.
            # 모든 에이전트를 나열할 수 있을 때까지 백그라운드 서비스를 준비한 뒤 각 run에서 재사용한다.
            expected_agents = {path.stem for path in (project / ".opencode/agents").glob("*.md")}
            for _ in range(60):
                listed = subprocess.run(
                    [cli, "debug", "agents"], cwd=project, env=env, text=True, capture_output=True, timeout=60,
                )
                try:
                    if expected_agents <= {item.get("id") for item in json.loads(listed.stdout)}:
                        break
                except json.JSONDecodeError:
                    pass
                time.sleep(1)
            else:
                raise AssertionError(f"OpenCode never listed the fixture agents: {listed.stdout}{listed.stderr}")

            def run_agent(name: str, calls: list[dict[str, object]] | None = None) -> tuple[set[str], str]:
                mock_script.write_text(json.dumps(calls or []), encoding="utf-8")
                mock_log.write_text("", encoding="utf-8")
                result = subprocess.run(
                    [cli, "run", "--agent", name, "--model", "mock/probe", "go"],
                    cwd=project, env=env, text=True, capture_output=True, timeout=120,
                    stdin=subprocess.DEVNULL,  # run은 TTY가 아닌 stdin을 메시지로 읽으므로 파이프를 상속하면 EOF를 계속 기다린다.
                )
                assert result.returncode == 0, (name, result.stdout + result.stderr)
                rows = [json.loads(line) for line in mock_log.read_text(encoding="utf-8").splitlines() if line]
                tools = {tool["function"]["name"] for row in rows for tool in row["body"].get("tools") or []}
                results = [
                    content if isinstance(content := message.get("content"), str) else json.dumps(content, ensure_ascii=False)
                    for row in rows
                    for message in row["body"].get("messages", [])
                    if message.get("role") == "tool"
                ]
                return tools, "\n".join(results)

            # 2.2부터 두 유형의 도구는 목록만으로 판단할 수 없어 실제 호출로 확인한다.
            # - skill은 로드할 스킬마다 권한을 판단한다. 2.2는 각 에이전트에 브라우저 스킬 규칙을 추가하므로
            #   skill의 마지막 일치 규칙은 전역 deny가 아니다. 목록에 항상 표시되지만 호출 시에는 여전히 "*" deny가 차단한다.
            # - execute가 거부되면 Code Mode 도구가 직접 노출된다(OpenCode #59315). opencode_worktree_remove는
            #   edit 권한을 사용하므로 에이전트에 어떤 edit allow라도 있으면 표시된다.
            def visible(name: str, tools: set[str]) -> set[str]:
                if "opencode_worktree_remove" in tools:
                    assert "edit" in tools, (name, tools)
                return tools - {"skill", "opencode_worktree_remove"}

            def assert_skill_denied(name: str) -> None:
                _, results = run_agent(name, [{"name": "skill", "arguments": {"id": "probe"}}])
                assert "SKILL_CANARY" not in results, (name, results)

            read_like = {"read", "glob", "grep"}
            for name in ("chapter-extractor", "character-designer", "consistency-checker",
                         "narrative-writer", "story-architect", "story-explorer", "story-researcher"):
                raw, _ = run_agent(name)
                tools = visible(name, raw)
                assert read_like <= tools, (name, tools)
                assert ("shell" in tools) == (name in {"narrative-writer", "story-researcher"}), (name, tools)
                assert not tools & {"subagent", "webfetch", "websearch", "skill", "execute"}, (name, tools)
                if "skill" in raw:
                    assert_skill_denied(name)
                print(f"  OpenCode {name}: {', '.join(sorted(raw))}")

            tools, results = run_agent("reader", [
                {"name": "write", "arguments": {"path": "reader-write.txt", "content": "DENIED"}},
            ])
            tools = visible("reader", tools)
            assert tools == {"read"}, tools
            assert not (project / "reader-write.txt").exists()
            assert re.search(r'No tool named \\?"write\\?"', results), results
            tools = visible("glob-only", run_agent("glob-only")[0])
            assert tools == {"glob"}, tools
            raw, _ = run_agent("inherit-minus-glob")
            if "skill" in raw:  # 모든 도구를 상속하는 대조군이 실제로 probe를 로드해 위의 거부가 스킬을 찾지 못해서가 아님을 입증한다.
                _, results = run_agent("inherit-minus-glob", [{"name": "skill", "arguments": {"id": "probe"}}])
                assert "SKILL_CANARY" in results, results
            tools = visible("inherit-minus-glob", raw)
            assert {"read", "grep"} <= tools and not tools & {"glob", "write", "edit", "patch", "shell"}, tools
            tools, _ = run_agent("writer", [
                {"name": "write", "arguments": {"path": "created.txt", "content": "CREATED"}},
            ])
            tools = visible("writer", tools)
            assert {"read", "write", "edit"} <= tools <= {"read", "write", "edit", "patch"}, tools
            assert (project / "created.txt").read_text(encoding="utf-8") == "CREATED"
            tools, results = run_agent("shell", [
                {"name": "shell", "arguments": {"command": "printf SHELL_OK", "description": "Fixture shell control"}},
            ])
            tools = visible("shell", tools)
            assert tools == {"read", "shell"}, tools
            assert "SHELL_OK" in results, results
            tools = visible("empty", run_agent("empty")[0])
            assert tools == set(), tools
            print("  OpenCode fixtures: reader/glob-only/inherit-minus-glob/writer/shell/empty match capabilities")
            assert (project / "canary.txt").read_text(encoding="utf-8") == "PERMISSION_CANARY\n"
        finally:
            subprocess.run([cli, "service", "stop"], env=env, capture_output=True, timeout=60)
            mock.terminate()
            mock.wait(timeout=10)


def test_antigravity_publish_recovers_from_rename_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="agy-publish-fault-") as tmp:
        root = Path(tmp)
        source = root / "source"
        write_agent(source, "reader", ["Read"])
        preload = root / "rename-fault.cjs"
        preload.write_text("""
const fs = require('fs');
const path = require('path');
const rename = fs.renameSync;
let failed = false;
fs.renameSync = function (source, destination) {
  const stage = path.basename(source).includes('.staging-');
  const restore = path.basename(source).includes('.backup-');
  if ((stage && !failed) || (restore && process.env.FAIL_RESTORE === '1')) {
    failed = true;
    const error = new Error('injected rename failure');
    error.code = process.env.RENAME_ERROR;
    throw error;
  }
  return rename.call(fs, source, destination);
};
""", encoding="utf-8")
        cases = [("EIO", False), ("EIO", True)]
        if os.name == "nt":
            cases.append(("EPERM", False))
        for index, (error, fail_restore) in enumerate(cases):
            dest = root / f"agents-{index}"
            dest.mkdir()
            (dest / "custom.txt").write_bytes(b"user content")
            result = subprocess.run(
                ["node", "--require", str(preload), str(ANTIGRAVITY_GENERATOR),
                 "--source", str(source), "--dest", str(dest)],
                env={**os.environ, "RENAME_ERROR": error, "FAIL_RESTORE": str(int(fail_restore))},
                text=True, capture_output=True,
            )
            if error == "EPERM":
                assert result.returncode == 0, result.stderr
                assert (dest / "reader/agent.md").is_file()
            else:
                assert result.returncode != 0
                assert not (dest / "reader/agent.md").exists()
            if fail_restore:
                backups = list(root.glob(f"agents-{index}.backup-*"))
                assert len(backups) == 1 and (backups[0] / "custom.txt").read_bytes() == b"user content"
            else:
                assert (dest / "custom.txt").read_bytes() == b"user content"
                assert not list(root.glob(f"agents-{index}.backup-*"))
            assert not list(root.glob(f".agents-{index}.staging-*"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode", help="OpenCode 2.x executable for real tool permission checks")
    args = parser.parse_args()
    test_antigravity_publish_recovers_from_rename_failure()
    test_permissions_follow_capabilities_not_names()
    test_empty_and_inherited_tools_are_distinct()
    test_codex_recognizes_other_mutating_tools()
    test_invalid_capability_declarations_fail_closed()
    if args.opencode:
        test_opencode_runtime(str(Path(args.opencode).resolve()))
    print("PASS: agent permissions derive from canonical capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
