#!/usr/bin/env python3
"""v17에서 현재 Codex 훅 등록으로 업그레이드하는 동작의 회귀 검사."""

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MERGER_PATH = ROOT / "skills/story-setup/scripts/merge-codex-hooks.py"
TEMPLATE_PATH = ROOT / "skills/story-setup/references/codex/hooks/hooks.json"


def load_merger():
    spec = importlib.util.spec_from_file_location("story_codex_hook_merge", MERGER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load {MERGER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_commands(document: dict[str, object]):
    hooks = document.get("hooks", {})
    assert isinstance(hooks, dict)
    for blocks in hooks.values():
        assert isinstance(blocks, list)
        for block in blocks:
            assert isinstance(block, dict)
            commands = block.get("hooks", [])
            assert isinstance(commands, list)
            yield from commands


def legacy_document(template: dict[str, object]) -> dict[str, object]:
    legacy = copy.deepcopy(template)
    for index, hook in enumerate(all_commands(legacy)):
        assert isinstance(hook, dict)
        hook["command"] = (
            'PROJECT_ROOT="$PWD"; HOOK="$PROJECT_ROOT/.codex/hooks/story_codex_hook.py"; '
            f'python3 "$HOOK" legacy-{index}'
        )
        hook["commandWindows"] = (
            "if exist .codex\\hooks\\story_codex_hook.py "
            f"python .codex\\hooks\\story_codex_hook.py legacy-{index}"
        )
    legacy["approval_policy"] = "on-request"
    first_block = legacy["hooks"]["PreToolUse"][0]
    first_block["hooks"].append(
        {"type": "command", "command": "./user-check.sh", "timeout": 3}
    )
    legacy["hooks"]["UserEvent"] = [
        {"matcher": "custom", "hooks": [{"type": "command", "command": "./custom.sh"}]}
    ]
    return legacy


def main() -> None:
    merger = load_merger()
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    legacy = legacy_document(template)

    merged = merger.merge_documents(legacy, template)
    commands = list(all_commands(merged))
    rendered = json.dumps(merged, ensure_ascii=False)
    assert "story_codex_hook.py" not in rendered
    assert sum(merger.is_story_setup_hook(command) for command in commands) == 6
    assert sum(command.get("command") == "./user-check.sh" for command in commands) == 1
    assert sum(command.get("command") == "./custom.sh" for command in commands) == 1
    assert merged["approval_policy"] == "on-request"
    assert merger.merge_documents(merged, template) == merged, "merge must be idempotent"

    with tempfile.TemporaryDirectory(prefix="codex-hook-merge-") as tmp:
        root = Path(tmp)
        existing_path = root / "hooks.json"
        output_path = root / "result.json"
        existing_path.write_text(json.dumps(legacy), encoding="utf-8")
        merger.atomic_write_json(output_path, merged)
        assert json.loads(output_path.read_text(encoding="utf-8")) == merged

    try:
        merger.merge_documents({}, {"hooks": []})
    except merger.MergeError:
        pass
    else:
        raise AssertionError("malformed template hooks must fail")

    # 사용자가 수동 변경한 배열 아닌 이벤트 값이 템플릿 이벤트명과 충돌하면 MergeError/exit 2로 진단해야 한다.
    # .extend()의 AttributeError traceback을 내면 안 된다.
    for bad in ({"matcher": "Bash", "hooks": []}, "nope", 5, None, True):
        try:
            merger.merge_documents({"hooks": {"PreToolUse": bad}}, template)
        except merger.MergeError as exc:
            assert "existing.hooks.PreToolUse must be an array" in str(exc), exc
        else:
            raise AssertionError(f"malformed existing event value must fail: {bad!r}")

    # 템플릿과 이름이 충돌하지 않는 배열 아닌 이벤트 값은 그대로 보존한다. 위 검사로 사용자 기존 설정 보존 계약을 좁히면 안 된다.
    preserved = merger.merge_documents({"hooks": {"UserEvent": {"a": 1}}}, template)
    assert preserved["hooks"]["UserEvent"] == {"a": 1}, preserved

    print("OK: Codex hook merge replaces v17 registrations and preserves user hooks")


if __name__ == "__main__":
    main()
