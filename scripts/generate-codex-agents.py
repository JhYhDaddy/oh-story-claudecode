#!/usr/bin/env python3
"""Claude 에이전트 Markdown에서 Codex 사용자 지정 에이전트 TOML 템플릿을 생성한다.

역할 텍스트의 기준 원본은 Claude/OpenCode 에이전트 Markdown이다.
Codex는 최소한 name, description, `developer_instructions`를 포함한 독립 TOML 파일을 요구한다.
이 스크립트는 결정론적으로 변환한다.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MUTATING_TOOLS = frozenset({"Write", "Edit", "Bash", "NotebookEdit", "PowerShell"})
SUPPORTED_TOOLS = MUTATING_TOOLS | {"Read", "Glob", "Grep"}
CAPABILITY_FIELDS = frozenset({"tools", "disallowedTools"})
CAPABILITY_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
NICKNAMES = {
    "chapter-extractor": ["Chapter Extractor", "Scene Splitter"],
    "character-designer": ["Character Designer", "Voice Crafter"],
    "consistency-checker": ["Consistency Checker", "Continuity Guard"],
    "narrative-writer": ["Narrative Writer", "Prose Crafter"],
    "story-architect": ["Story Architect", "Plot Architect"],
    "story-explorer": ["Story Explorer", "Lore Scout"],
    "story-researcher": ["Story Researcher", "Source Scout"],
}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unterminated frontmatter")
    raw = text[4:end]
    body = text[end + len("\n---\n") :].lstrip()
    data: dict[str, str] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), (m.group(2) or "").rstrip()
        if value == "|":
            block: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt and not nxt.startswith((" ", "\t")):
                    break
                block.append(nxt[2:] if nxt.startswith("  ") else nxt.lstrip())
                i += 1
            data[key] = "\n".join(block).strip()
            continue
        normalized = value.strip()
        data[key] = (
            normalized
            if key in CAPABILITY_FIELDS
            else normalized.strip('"').strip("'")
        )
        i += 1
    return data, body


def toml_basic_string(value: str) -> str:
    # 지침과 Markdown의 가독성을 유지하기 위해 여러 줄 기본 문자열을 사용한다.
    escaped = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""\n{escaped.rstrip()}\n"""'


def toml_list(values: list[str]) -> str:
    return "[" + ", ".join(repr(v).replace("'", '"') for v in values) + "]"


def parse_tool_list(value: str, field: str) -> set[str]:
    """지원하는 인라인 기능 목록 부분집합을 파싱하고 나머지는 거부한다."""
    if not value:
        raise ValueError(
            f"{field}: empty or block-style capability declarations are unsupported"
        )
    match = re.fullmatch(r"\[\s*(.*?)\s*\]", value)
    if not match:
        raise ValueError(f"{field}: expected an inline list like [Read, Glob]")
    inner = match.group(1)
    if not inner.strip():
        return set()
    parsed: set[str] = set()
    for raw_item in inner.split(","):
        item = raw_item.strip()
        if not item:
            raise ValueError(f"{field}: empty capability-list item")
        if item[0] in {'"', "'"}:
            quote = item[0]
            if len(item) < 2 or item[-1] != quote or quote in item[1:-1]:
                raise ValueError(f"{field}: malformed quoted capability {item!r}")
            item = item[1:-1]
        elif '"' in item or "'" in item:
            raise ValueError(f"{field}: malformed quoted capability {item!r}")
        if CAPABILITY_NAME_RE.fullmatch(item) is None:
            raise ValueError(f"{field}: invalid capability name {item!r}")
        if item not in SUPPORTED_TOOLS:
            raise ValueError(f"{field}: unsupported Codex capability {item!r}")
        parsed.add(item)
    return parsed


def is_read_only(meta: dict[str, str]) -> bool:
    """유효한 기준 기능 집합에서 파일 시스템 제한 범위를 도출한다."""
    declared = (
        parse_tool_list(meta["tools"], "tools") if "tools" in meta else set()
    )
    denied = (
        parse_tool_list(meta["disallowedTools"], "disallowedTools")
        if "disallowedTools" in meta
        else set()
    )
    if "tools" not in meta:
        # 상속된 도구에는 여기에 나열되지 않은 MCP 및 기타 기능이 포함될 수 있다.
        return False
    effective = declared - denied
    if not effective:
        raise ValueError("tools: Codex sandbox_mode cannot represent zero effective tools")
    return effective.isdisjoint(MUTATING_TOOLS)


def adapt_body_for_codex(body: str, name: str) -> str:
    """Claude/OpenCode 호출자 용어를 Codex 사용자 지정 에이전트 표현으로 바꾼다."""
    adapted = body.replace("subagent_type", "agent_type")
    adapted = adapted.replace(
        ".claude/skills/story-setup/references/agent-references/",
        ".codex/skills/story-setup/references/agent-references/",
    )
    adapted = adapted.replace("当前 Claude 部署", "当前 Codex 部署")
    adapted = re.sub(
        r"(?<![A-Za-z0-9_])/(story(?:-[a-z0-9]+)*)",
        lambda match: "$" + match.group(1),
        adapted,
    )
    adapted = adapted.replace("Claude Code subagent", "Codex custom agent")
    return (
        adapted.rstrip()
        + "\n\n---\n\n"
        + "Codex 어댑터 참고 사항:\n"
        + f'- 현재 런타임이 프로젝트별 사용자 정의 에이전트를 제공하면 `agent_type: "{name}"`으로 이 에이전트를 요청합니다.\n'
        + "- Codex가 `unknown agent_type`을 반환하거나 사용자 정의 에이전트 등록부를 사용할 수 없으면, 상위 워크플로는 실패로 끝내지 않고 단독·직접 실행으로 전환하여 그 사실을 보고해야 합니다.\n"
        + "- 이 에이전트의 역할 범위를 지키고, 인접 역할의 작업은 상위 에이전트에 돌려보냅니다.\n"
        + "- 배포된 Codex 참조 경로 `.codex/skills/story-setup/references/agent-references/`만 사용합니다. 없으면 다른 CLI 디렉터리를 탐색하지 말고 배포 누락을 보고합니다.\n"
        + "- Claude 전용 도구 이름이나 프런트매터 필드가 Codex에도 있다고 가정하지 않습니다.\n"
    )


def render_file(src: Path) -> tuple[str, str]:
    """대상을 건드리지 않고 원본 하나를 검증하고 렌더링한다."""
    text = src.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    name = meta.get("name") or src.stem
    if name != src.stem or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) is None:
        raise ValueError(
            f"{src}: agent name {name!r} must match its safe filename stem {src.stem!r}"
        )
    description = meta.get("description", "").strip()
    if not description:
        raise ValueError(f"{src}: missing description")
    instructions = adapt_body_for_codex(body, name)
    out = [
        f'name = "{name}"',
        f"description = {toml_basic_string(description)}",
        f"nickname_candidates = {toml_list(NICKNAMES.get(name, [name]))}",
    ]
    if is_read_only(meta):
        out.append('sandbox_mode = "read-only"')
    out.append(f"developer_instructions = {toml_basic_string(instructions)}")
    return f"{name}.toml", "\n".join(out) + "\n"


def publish_rendered(
    rendered: dict[str, str], dst_dir: Path, *, pattern: str = "*.toml"
) -> list[Path]:
    """디렉터리를 유지한 채 롤백을 지원하며 생성 파일을 반영한다."""
    if dst_dir.is_symlink():
        raise ValueError(f"destination directory must not be a symlink: {dst_dir}")
    if dst_dir.exists() and not dst_dir.is_dir():
        raise ValueError(f"destination is not a directory: {dst_dir}")

    dst_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{dst_dir.name}.staging-", dir=dst_dir.parent)
    )
    backup = Path(
        tempfile.mkdtemp(prefix=f".{dst_dir.name}.backup-", dir=dst_dir.parent)
    )
    try:
        for filename, output in rendered.items():
            with (staging / filename).open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(output)

        existing = sorted(dst_dir.glob(pattern))
        for path in existing:
            if path.is_dir() and not path.is_symlink():
                raise IsADirectoryError(f"generated target is a directory: {path}")
            if path.is_symlink():
                (backup / path.name).symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, backup / path.name)

        try:
            for filename in rendered:
                os.replace(staging / filename, dst_dir / filename)
            for stale in existing:
                if stale.name not in rendered:
                    stale.unlink()
        except BaseException:
            # 가능한 범위에서 롤백한다. 삭제할 수 없는 파일 하나(불변 플래그,
            # 잠금, 읽기 전용 마운트) 때문에 복구를 중단해
            # 일부만 반영된 상태를 남기지 않는다. 백업에 있는 파일은 제자리에서 덮어쓰고
            # 반영 전에 없었던 출력 파일만 삭제한다.
            restore_names = {path.name for path in backup.iterdir()}
            for current in list(dst_dir.glob(pattern)):
                if current.is_dir() and not current.is_symlink():
                    continue
                if current.name in restore_names:
                    continue
                try:
                    current.unlink()
                except OSError:
                    pass
            for original in backup.iterdir():
                target = dst_dir / original.name
                try:
                    if original.is_symlink():
                        if target.is_symlink() or target.exists():
                            target.unlink()
                        target.symlink_to(os.readlink(original))
                    else:
                        # 대상이 일반 파일임을 보장한다(반영은 준비된 일반 파일을
                        # os.replace로 교체하기만 함). 따라서 copy2로
                        # 제자리에서 안전하게 덮어쓸 수 있다.
                        shutil.copy2(original, target)
                except OSError:
                    pass
            raise
        return [dst_dir / filename for filename in rendered]
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT / "skills/story-setup/references/templates/agents",
        help="Claude agent template directory",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=REPO_ROOT / "skills/story-setup/references/codex/agents",
        help="Codex TOML output directory",
    )
    args = parser.parse_args()
    src_dir = args.source
    dst_dir = args.dest
    if not src_dir.is_dir():
        parser.error(f"source directory does not exist: {src_dir}")
    sources = sorted(src_dir.glob("*.md"))
    if not sources:
        parser.error(f"source directory contains no agent markdown files: {src_dir}")
    # 첫 대상에 쓰기 전에 모든 원본을 렌더링한다. 뒤에 나오는 잘못된
    # 템플릿 때문에 생성 디렉터리가 반만 갱신된 상태로 남으면 안 된다.
    rendered: dict[str, str] = {}
    for path in sources:
        filename, output = render_file(path)
        if filename in rendered:
            raise ValueError(f"duplicate generated agent filename: {filename}")
        rendered[filename] = output

    generated = publish_rendered(rendered, dst_dir)
    print(f"Generated {len(generated)} Codex agent files in {dst_dir}")
    for path in generated:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
