#!/usr/bin/env python3
"""오래된 등록을 남기지 않고 현재 story-setup Codex 훅을 병합한다.

기존 프로젝트 훅 설정은 사용자 소유다. story-setup의 알려진 Python 훅이나
공유 실행기를 호출하는 명령 훅만 교체한다. 관련 없는 훅과 최상위 설정은
원문 그대로 보존한다.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


MANAGED_COMMAND_MARKERS = (
    ".codex/hooks/story_codex_hook.py",
    ".codex/hooks/run-story-hook.sh",
    ".codex/hooks/run-story-hook.cmd",
)


class MergeError(ValueError):
    pass


def normalized_command(value: object) -> str:
    return value.lower().replace("\\", "/") if isinstance(value, str) else ""


def is_story_setup_hook(hook: object) -> bool:
    if not isinstance(hook, dict):
        return False
    commands = (
        normalized_command(hook.get("command")),
        normalized_command(hook.get("commandWindows")),
    )
    return any(marker in command for marker in MANAGED_COMMAND_MARKERS for command in commands)


def require_hooks(document: object, label: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise MergeError(f"{label} root must be a JSON object")
    hooks = document.get("hooks", {})
    if not isinstance(hooks, dict):
        raise MergeError(f"{label}.hooks must be a JSON object")
    return hooks


def strip_managed_registrations(hooks: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for event, raw_blocks in hooks.items():
        if not isinstance(raw_blocks, list):
            cleaned[event] = copy.deepcopy(raw_blocks)
            continue

        blocks: list[Any] = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict) or not isinstance(raw_block.get("hooks"), list):
                blocks.append(copy.deepcopy(raw_block))
                continue
            kept_hooks = [
                copy.deepcopy(hook)
                for hook in raw_block["hooks"]
                if not is_story_setup_hook(hook)
            ]
            if not kept_hooks:
                continue
            block = copy.deepcopy(raw_block)
            block["hooks"] = kept_hooks
            blocks.append(block)
        if blocks:
            cleaned[event] = blocks
    return cleaned


def merge_documents(existing: object, template: object) -> dict[str, Any]:
    existing_hooks = require_hooks(existing, "existing")
    template_hooks = require_hooks(template, "template")
    for event, blocks in template_hooks.items():
        if not isinstance(blocks, list):
            raise MergeError(f"template.hooks.{event} must be an array")

    result = copy.deepcopy(existing)
    assert isinstance(result, dict)  # require_hooks에서 타입 범위를 좁힘
    merged_hooks = strip_managed_registrations(existing_hooks)
    for event, blocks in template_hooks.items():
        # 템플릿 이벤트와 이름이 겹칠 때만 사용자 값이 배열인지 요구한다. 알 수 없는 이벤트의 비배열 값은
        # strip_managed_registrations가 그대로 보존한다(기존 사용자 설정 보존 계약).
        # 이름이 겹치지만 extend할 수 없다면 AttributeError 추적 대신 MergeError 진단을 제공한다.
        if event in merged_hooks and not isinstance(merged_hooks[event], list):
            raise MergeError(f"existing.hooks.{event} must be an array")
        merged_hooks.setdefault(event, []).extend(copy.deepcopy(blocks))
    result["hooks"] = merged_hooks
    return result


def read_json(path: Path, *, missing_ok: bool = False) -> object:
    if missing_ok and not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError(f"unable to read {path}: {exc}") from exc


def atomic_write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, previous_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        existing = read_json(args.existing, missing_ok=True)
        template = read_json(args.template)
        atomic_write_json(args.output, merge_documents(existing, template))
    except MergeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
