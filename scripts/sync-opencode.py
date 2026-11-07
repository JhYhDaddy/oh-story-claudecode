#!/usr/bin/env python
"""Claude Code 에이전트 템플릿을 OpenCode 형식으로 동기화한다.

templates/agents/*.md를 검색하고 frontmatter를 OpenCode 2.x 형식(기본 `permissions:` 규칙 목록)으로
변환해 opencode/agents/에 쓴다. CLAUDE.md.tmpl도 AGENTS.md.tmpl로 동기화한다.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 에이전트 본문에서 셸 단계는 ‘执行 / 运行 / 跑 `<명령>`’으로 표현한다. ‘执行’만 인식하면 누락된다.
# #283의 읽기 전용 에이전트 권한 초과 지침은 ‘运行 `tracking_commit.py check`’였으며 두 검사 계층 모두 차단하지 못했다.
# 읽기 전용 에이전트에 이런 지침이 있으면 생성을 즉시 실패시킨다. OpenCode shell.ts는 command의 직접 부모만 검사하므로
# ‘완전한 명령 리터럴’ 허용 목록도 `( command ) > 본문.md`처럼 서브셸 바깥에서 리디렉션하면 우회된다.
BODY_COMMAND_RE = re.compile(r"(?:执行|运行|跑) `([^`]+)`")
# 다른 실행자에게 위임하는 지침은 이 에이전트의 셸 단계가 아니다(‘주 세션이 X 재실행을 안내’, ‘호출자가 주 세션에서 X 실행하도록 안내’ 등).
# 같은 줄에 위임 주체가 있을 때만 예외 처리한다. 직접 실행 지침을 위임 문장처럼 써서 검사를 우회하지 못하게 한다.
BODY_DELEGATION_RE = re.compile(r"(调用方|父流程|主会话|用户|由.{0,6}提示)")
CAPABILITY_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
# OpenCode 2.x 권한 action → 해당 권한을 부여하는 Claude 도구. edit 하나가 write/edit/patch를 모두 관리한다.
TOOL_PERMISSIONS = {
    "read": {"Read"},
    "glob": {"Glob"},
    "grep": {"Grep"},
    "edit": {"Write", "Edit"},
    "shell": {"Bash"},
}
SUPPORTED_TOOLS = set().union(*TOOL_PERMISSIONS.values())
# Claude 템플릿은 frontmatter 인라인 훅에서 story_hook_cli.js 쓰기 검사를 호출해 쓰기 경로를 제한한다. OpenCode에는
# 에이전트별 인라인 훅이 없으므로 2.x 기본 edit 경로 규칙으로 같은 파일 집합에 한정한다. resource는 세션 디렉터리 기준
# 상대 경로(프로젝트 밖은 절대 경로)이며 *는 디렉터리를 넘어 일치한다(core/src/file-access.ts resolve, util/wildcard.ts).
# 검사기 이름이 등록되지 않았는데 에이전트가 쓸 수 있으면 생성을 실패시킨다. 작업 공간 전체를 조용히 허용하지 않는다.
# `..`로는 우회할 수 없다. 2.x의 write/edit/patch(patch 이동 대상 포함)는 먼저 FileAccess.resolve를 거친다.
# path.resolve로 어휘적 정규화를 한 뒤 path.relative를 resource로 사용한다(core/src/file-access.ts resolvePath/
# resolve, 2.0.18 소스 확인). 규칙은 정규화된 경로에 적용되므로 `x/_analysis_cache/输入-RAW-1/../../본문/제1장.md`는
# 일치 검사 시 이미 `x/본문/제1장.md`이며 deny에 해당한다.
WRITE_GUARD_RE = re.compile(r"story_hook_cli\.js\s+([a-z][a-z0-9-]*-guard)\b")
WRITE_GUARD_EDIT_RESOURCES = {
    "analysis-input-guard": tuple(
        prefix + "_analysis_cache/输入-" + kind + "-*.md"
        for kind in ("RAW", "REUSE")
        for prefix in ("", "*/")
    ),
}


def body_bash_commands(body: str) -> list[str]:
    """에이전트 본문에서 명시적으로 실행을 요구한 명령을 추출한다(출현 순서대로 중복 제거).

    에이전트 이름을 하드코딩한 집합은 의도적으로 사용하지 않는다. 이전 감사에서 generate-codex-agents.py의
    문제로 지적한 방식이기 때문이다. 목록과 본문이 따로 변하면 명령이 추가된 에이전트는 권한을 얻지 못하고
    명령이 삭제된 에이전트는 불필요한 권한을 유지한다. 본문만을 기준으로 삼으며 읽기 전용 에이전트에서
    명령이 하나라도 추출되면 변환 단계에서 중단한다.
    """
    commands: list[str] = []
    for line in body.splitlines():
        if BODY_DELEGATION_RE.search(line):
            continue
        for match in BODY_COMMAND_RE.finditer(line):
            command = match.group(1).strip()
            if command and command not in commands:
                commands.append(command)
    return commands


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Markdown 내용에서 YAML 형태의 frontmatter와 본문을 추출한다."""
    # 종료 구분자는 한 줄을 단독으로 차지하는 `---`여야 한다(‘\n---\n’에 고정). content.split("---", 2)를 쓰면 안 된다.
    # 그러면 frontmatter 값 안의 세 하이픈(설명이나 주석 속 `---`)을 종료 표식으로 오인해
    # permissions/steps를 포함한 나머지 키를 본문으로 잘라 넣고도 조용히 exit 0으로 끝난다.
    # 같은 원본을 쓰는 generate-codex-agents.py와 파싱 기준을 일치시킨다.
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---\n", len("---"))
    if end < 0:
        return {}, content
    fm_text = content[len("---") : end].strip()
    body = content[end + len("\n---") :]
    fm = {}
    lines = fm_text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if val == "|":
                continuation = []
                i += 1
                while i < len(lines):
                    cont_line = lines[i]
                    if cont_line.startswith((" ", "\t")) and cont_line.strip():
                        continuation.append(cont_line.strip())
                        i += 1
                    elif not cont_line.strip():
                        continuation.append("")
                        i += 1
                    else:
                        break
                fm[key] = "\n".join(continuation).strip()
                continue
            else:
                fm[key] = val

        i += 1

    return fm, body


WRITE_HOOK_MATCHER_RE = re.compile(r"^\s*-?\s*matcher:\s*[\"']?([^\"'\n]*)", re.M)


def frontmatter_write_guard(content: str) -> str | None:
    """에이전트 frontmatter에 연결된 쓰기 검사기 이름이 있으면 반환한다.

    Write/Edit의 PreToolUse 훅이 있는데 검사기 이름을 인식하지 못하면(명령 형식 변경 등) 오류를 낸다.
    검사기가 없는 것으로 처리하면 작업 공간 전체의 edit 권한을 조용히 허용하게 된다. CRLF 템플릿은
    먼저 정규화한다. matcher가 `*`이거나 비어 있거나 전체가 생략되어도 쓰기 도구를 포함한 것으로 본다.
    """
    content = content.replace("\r\n", "\n")
    end = content.find("\n---\n", len("---"))
    frontmatter = content[:end] if content.startswith("---\n") and end > 0 else ""
    match = WRITE_GUARD_RE.search(frontmatter)
    if match:
        return match.group(1)
    matchers = WRITE_HOOK_MATCHER_RE.findall(frontmatter)
    write_hooked = "PreToolUse" in frontmatter and (not matchers or any(
        {"Write", "Edit", "MultiEdit", "*", ".*", ""} & {tool.strip() for tool in matcher.split("|")}
        for matcher in matchers
    ))
    if write_hooked:
        raise ValueError(
            "frontmatter 挂了 Write/Edit 的 PreToolUse hook，但没认出 story_hook_cli.js 的守卫名；"
            "更新 WRITE_GUARD_RE 与 WRITE_GUARD_EDIT_RESOURCES，不能按未挂守卫放开 edit"
        )
    return None


def convert_claude_to_opencode(fm: dict, body: str, write_guard: str | None = None) -> dict:
    """Claude Code 에이전트 frontmatter를 OpenCode 형식으로 변환한다.

    `body`는 필수다. bash 허용 목록은 본문이 해당 명령 실행을 실제로 요구하는지에 따라 에이전트별로
    권한을 부여한다. 본문 하나라도 빠지면 근거 없이 권한을 줄이거나 넓히므로 호출자가 반드시 전달해야 한다.
    `write_guard`는 frontmatter에 연결된 쓰기 검사기 이름이며 쓰기 가능한 에이전트의 edit를
    해당 검사기가 허용한 경로로 제한한다.
    """
    result = {}
    name = fm.get("name", "")

    if "description" in fm:
        result["description"] = fm["description"]

    result["mode"] = "subagent"

    tools = _parse_list(fm["tools"], "tools") if "tools" in fm else []
    disallowed = (
        _parse_list(fm["disallowedTools"], "disallowedTools")
        if "disallowedTools" in fm
        else []
    )
    denied_tools = set(disallowed)
    explicit_tools = "tools" in fm
    effective_tools = (set(tools) if explicit_tools else SUPPORTED_TOOLS) - denied_tools

    # OpenCode 기본값은 허용이다. 목록을 선언하면 목록 밖의 도구도 닫아야 한다.
    # 하위 에이전트와 MCP도 포함한다. OpenCode는 마지막 일치 규칙을 선택하므로 와일드카드를 맨 앞에 두고
    # 뒤의 규칙이 이를 덮어쓰게 한다.
    perm = {"*": "deny"} if explicit_tools else {}
    # edit는 write/edit/patch를 통합한다. 원본 도구 중 하나라도 있으면 변경 권한을 부여한다.
    for action, source_tools in TOOL_PERMISSIONS.items():
        if explicit_tools:
            perm[action] = "allow" if effective_tools & source_tools else "deny"
        elif source_tools <= denied_tools:
            perm[action] = "deny"
    mentioned_bash = body_bash_commands(body)
    if "Bash" not in effective_tools and mentioned_bash:
        raise ValueError(
            f"{name or '<unnamed>'}: agent 未获授权使用 Bash，但正文要求执行 "
            + "、".join(f"`{command}`" for command in mentioned_bash)
            + "；改写正文以使用宿主已提供的工作区和 Read/Glob/Grep，不得开放 shell 例外。"
        )
    if write_guard and perm.get("edit") == "allow":
        resources = WRITE_GUARD_EDIT_RESOURCES.get(write_guard)
        if not resources:
            raise ValueError(
                f"{name or '<unnamed>'}: 写入守卫 {write_guard} 没有登记 OpenCode edit 路径规则"
            )
        # 먼저 전체를 deny한 뒤 개별 허용한다. OpenCode는 마지막 일치 규칙을 사용하며 마지막 resource가 *가 아니어도 도구는 표시된다.
        perm["edit"] = "deny"
        for resource in resources:
            perm[("edit", resource)] = "allow"
    if perm:
        result["permissions"] = perm

    if "maxTurns" in fm:
        try:
            result["steps"] = int(fm["maxTurns"])
        except ValueError:
            pass

    return result


def _parse_list(val: str, field: str) -> list[str]:
    """지원하는 인라인 기능 목록 부분집합을 파싱하고 나머지는 거부한다."""
    if not val:
        raise ValueError(
            f"{field}: empty or block-style capability declarations are unsupported"
        )
    match = re.fullmatch(r"\[\s*(.*?)\s*\]", val)
    if not match:
        raise ValueError(f"{field}: expected an inline list like [Read, Glob]")
    inner = match.group(1)
    if not inner.strip():
        return []
    parsed: list[str] = []
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
            raise ValueError(f"{field}: unsupported OpenCode capability {item!r}")
        parsed.append(item)
    return parsed


def format_frontmatter(fm: dict) -> str:
    """frontmatter 딕셔너리를 YAML 형태의 문자열로 포맷한다."""
    lines = ["---"]
    for key, value in fm.items():
        if key == "permissions":
            # 2.x 기본 규칙 목록: 각 항목에 action/resource/effect 세 키가 모두 있어야 한다. 정렬 금지. OpenCode는
            # 마지막 일치 규칙을 선택하므로 목록 순서가 우선순위이며 dict 삽입 순서 그대로 출력해야 한다.
            # YAML에서 따옴표 없는 `*`는 별칭 표식이므로 반드시 따옴표로 감싼다.
            lines.append("permissions:")
            # 키는 action(resource는 *) 또는 (action, resource) 쌍이다.
            for key, effect in value.items():
                action, resource = key if isinstance(key, tuple) else (key, "*")
                action_text = '"*"' if action == "*" else action
                lines.append(f"  - action: {action_text}")
                lines.append(f'    resource: "{resource}"')
                lines.append(f"    effect: {effect}")
        elif key == "description" and "\n" in value:
            lines.append("description: |")
            for desc_line in value.split("\n"):
                lines.append(f"  {desc_line}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def replace_claude_paths(body: str) -> str:
    """.claude/ 경로 참조를 대응하는 .opencode/ 경로로 바꾼다.

    경로 규칙 절은 fix_path_rules_section()이 멱등적으로 처리하므로 수동 수정이 필요 없다.
    """
    replacements = [
        (".claude/skills/", ".opencode/skills/"),
        (".claude/agents/", ".opencode/agents/"),
        (".claude/hooks/", ".opencode/hooks/"),
        ("~/.claude/", "~/.config/opencode/"),
        ("$HOME/.claude/", "$HOME/.config/opencode/"),
        ("CLAUDE.md", "AGENTS.md"),
    ]
    for old, new in replacements:
        if old in body:
            body = body.replace(old, new)
    return body


def fix_path_rules_section(body: str) -> str:
    """참조 파일 경로 규칙 절을 올바른 opencode 경로로 바꾼다.

    ‘参考文件路径规则’ 절을 찾아 story-setup이 OpenCode용으로 배포하는 단일 기준 경로로 교체한다.
    멱등적이므로 여러 번 실행해도 결과가 같다.
    """
    # 일부 에이전트는 참조 파일을 읽지 않아 의도적으로 이 절이 없다.
    # 절 표식이 있는데 형식이 달라진 경우에만 경고한다.
    if "参考文件路径规则" not in body:
        return body

    pattern = r"(## 参考文件路径规则\s*\*\*确定项目根目录：\*\*.*?\s*)读取参考文件时.*?(?=\s*禁止只读|\r?\n## )"

    replacement = (
        r"\1"
        r"读取参考文件时 — 참조 파일을 읽을 때는 현재 OpenCode 배포의 기준 경로를 직접 Read하며, 먼저 Glob/Grep으로 검색해서는 안 됩니다:\n"
        r"1. `{项目根}/skills/story-setup/references/agent-references/{文件名}`\n"
        r"\n"
        r"파일이 없으면 누락 사실을 반환하고 주 세션에서 `/story-setup` 재실행을 안내합니다. 다른 CLI 디렉터리를 탐색하지 않습니다."
    )

    new_body, count = re.subn(pattern, replacement, body, flags=re.DOTALL)
    if count == 0:
        print(
            "  [WARN] fix_path_rules_section: 未检测到路径规则段，可能源模板格式已变更",
            file=sys.stderr,
        )
    return new_body


def file_status(dst: Path, output: str) -> tuple[str, bool]:
    """대상을 변경하지 않고 생성 파일 하나를 비교한다."""
    if not os.path.lexists(dst):
        return "missing", True
    if dst.is_symlink() or not dst.is_file():
        return "stale", True
    old_content = dst.read_text(encoding="utf-8")
    if old_content == output:
        return "unchanged", False
    return "stale", True


def render_agents() -> dict[str, str]:
    """대상에 쓰기 전에 모든 OpenCode 에이전트를 검증하고 렌더링한다."""
    src_dir = ROOT / "skills/story-setup/references/templates/agents"
    sources = sorted(src_dir.glob("*.md"))
    if not sources:
        raise RuntimeError(f"no agent markdown files found in {src_dir}")
    rendered: dict[str, str] = {}
    for md_file in sources:
        content = md_file.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        name = str(fm.get("name", "")).strip()
        description = str(fm.get("description", "")).strip()
        if not name:
            raise ValueError(f"{md_file}: missing agent name")
        if name != md_file.stem:
            raise ValueError(
                f"{md_file}: agent name {name!r} must match filename {md_file.stem!r}"
            )
        if not description:
            raise ValueError(f"{md_file}: missing agent description")
        # .claude→.opencode 경로 치환 전인 **원본 템플릿 본문**에서 bash 허용 목록을 도출한다.
        # 권한 부여 근거는 생성 산출물 표현이 아니라 원본 정의에 해당 명령이 있는지다.
        new_fm = convert_claude_to_opencode(fm, body, frontmatter_write_guard(content))
        new_body = replace_claude_paths(body)
        new_body = fix_path_rules_section(new_body)  # 경로 규칙 절의 잘못된 치환을 덮어쓴다.
        output = format_frontmatter(new_fm) + new_body
        output = output.rstrip("\n") + "\n"  # 끝부분을 줄바꿈 하나로 정규화해 EOF 빈 줄을 방지한다.
        if md_file.name in rendered:
            raise ValueError(f"duplicate generated agent filename: {md_file.name}")
        rendered[md_file.name] = output
    return rendered


def agent_statuses(
    rendered: dict[str, str], dst_dir: Path, check: bool
) -> tuple[list[str], bool]:
    """생성된 에이전트 영역의 결정론적 상태 줄을 반환한다."""
    results: list[str] = []
    changed = False
    for filename, output in rendered.items():
        dst_file = dst_dir / filename
        raw_status, file_changed = file_status(dst_file, output)
        if check:
            status = raw_status
        else:
            status = (
                "created"
                if raw_status == "missing"
                else "updated"
                if raw_status == "stale"
                else raw_status
            )
        changed = changed or file_changed
        results.append(f"  [{status}] {dst_file.name}")

    for stale in sorted(dst_dir.glob("*.md")):
        if stale.name in rendered:
            continue
        changed = True
        results.append(f"  [{'extra' if check else 'deleted'}] {stale.name}")

    return results, changed


def render_agents_md() -> str:
    """OpenCode용 CLAUDE.md.tmpl을 검증하고 렌더링한다."""
    src = ROOT / "skills/story-setup/references/templates/CLAUDE.md.tmpl"
    if not src.is_file():
        raise RuntimeError(f"source template not found: {src}")

    content = src.read_text(encoding="utf-8")
    new_content = replace_claude_paths(content)
    # auto memory는 Claude Code 내장 기억 기능의 명칭이므로 OpenCode 버전에서는 일반 표현만 남긴다.
    new_content = new_content.replace("自带的记忆（如 auto memory）", "自带的记忆")
    return new_content.rstrip("\n") + "\n"  # 끝부분을 줄바꿈 하나로 정규화해 EOF 빈 줄을 방지한다.


def publish_tree(rendered: dict[str, str], agents_md: str, dst_root: Path) -> None:
    """수동 자산을 보존하며 롤백을 지원해 생성 OpenCode 파일을 반영한다."""
    if dst_root.is_symlink():
        raise ValueError(f"destination directory must not be a symlink: {dst_root}")
    if dst_root.exists() and not dst_root.is_dir():
        raise ValueError(f"destination is not a directory: {dst_root}")
    existing_agents = dst_root / "agents"
    if existing_agents.is_symlink():
        raise ValueError(
            f"generated agents directory must not be a symlink: {existing_agents}"
        )
    if existing_agents.exists() and not existing_agents.is_dir():
        raise ValueError(
            f"generated agents path is not a directory: {existing_agents}"
        )

    dst_root.mkdir(parents=True, exist_ok=True)
    existing_agents.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{dst_root.name}.staging-", dir=dst_root.parent)
    )
    backup = Path(
        tempfile.mkdtemp(prefix=f".{dst_root.name}.backup-", dir=dst_root.parent)
    )
    try:
        agents_dir = staging / "agents"
        backup_agents = backup / "agents"
        agents_dir.mkdir()
        backup_agents.mkdir()
        for filename, output in rendered.items():
            with (agents_dir / filename).open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(output)

        staged_agents_md = staging / "AGENTS.md.tmpl"
        with staged_agents_md.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(agents_md)

        existing_md = sorted(existing_agents.glob("*.md"))
        for path in existing_md:
            if path.is_dir() and not path.is_symlink():
                raise IsADirectoryError(f"generated target is a directory: {path}")
            if path.is_symlink():
                (backup_agents / path.name).symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, backup_agents / path.name)

        target_agents_md = dst_root / "AGENTS.md.tmpl"
        had_agents_md = os.path.lexists(target_agents_md)
        if target_agents_md.is_dir() and not target_agents_md.is_symlink():
            raise IsADirectoryError(
                f"generated target is a directory: {target_agents_md}"
            )
        if had_agents_md:
            if target_agents_md.is_symlink():
                (backup / "AGENTS.md.tmpl").symlink_to(
                    os.readlink(target_agents_md)
                )
            else:
                shutil.copy2(target_agents_md, backup / "AGENTS.md.tmpl")

        try:
            for filename in rendered:
                os.replace(agents_dir / filename, existing_agents / filename)
            os.replace(staged_agents_md, target_agents_md)
            for stale in existing_md:
                if stale.name not in rendered:
                    stale.unlink()
        except BaseException:
            # 가능한 범위에서 롤백한다. 삭제할 수 없는 파일 하나 때문에
            # 복구가 중단되어 부분 반영 상태가 남으면 안 된다. 백업된 파일은
            # 제자리에서 덮어쓰고 반영 전에 없던 출력 파일만 삭제한다.
            restore_names = {path.name for path in backup_agents.iterdir()}
            for current in list(existing_agents.glob("*.md")):
                if current.is_dir() and not current.is_symlink():
                    continue
                if current.name in restore_names:
                    continue
                try:
                    current.unlink()
                except OSError:
                    pass
            for original in backup_agents.iterdir():
                target = existing_agents / original.name
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
            original_agents_md = backup / "AGENTS.md.tmpl"
            try:
                if had_agents_md:
                    if original_agents_md.is_symlink():
                        if target_agents_md.is_symlink() or target_agents_md.exists():
                            target_agents_md.unlink()
                        target_agents_md.symlink_to(os.readlink(original_agents_md))
                    else:
                        shutil.copy2(original_agents_md, target_agents_md)
                elif os.path.lexists(target_agents_md) and (
                    not target_agents_md.is_dir() or target_agents_md.is_symlink()
                ):
                    target_agents_md.unlink()
            except OSError:
                pass
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated files without modifying the working tree",
    )
    args = parser.parse_args()

    # 에이전트와 최상위 지침이 하나의 생성 어댑터를 이룬다. 어느 쪽을 검사하거나 반영하기 전에
    # 두 단계 모두 렌더링하고 검증한다.
    rendered = render_agents()
    agents_md = render_agents_md()
    dst_root = ROOT / "skills/story-setup/references/opencode"
    agent_results, agents_changed = agent_statuses(
        rendered, dst_root / "agents", args.check
    )
    raw_md_status, agents_md_changed = file_status(
        dst_root / "AGENTS.md.tmpl", agents_md
    )
    if args.check:
        md_status = raw_md_status
    else:
        md_status = (
            "created"
            if raw_md_status == "missing"
            else "updated"
            if raw_md_status == "stale"
            else raw_md_status
        )

    print("=== opencode sync script ===\n")
    print("1. Syncing agents...")
    for r in agent_results:
        print(r)

    print("\n2. Syncing AGENTS.md.tmpl...")
    print(f"  [{md_status}] AGENTS.md.tmpl")

    if args.check:
        if agents_changed or agents_md_changed:
            print(
                "\nERROR: generated OpenCode templates are out of sync.",
                file=sys.stderr,
            )
            return 1
        print("\nOK: generated OpenCode templates are in sync.")
        return 0

    publish_tree(rendered, agents_md, dst_root)

    print("\n3. Manual maintenance required:")
    print("  - skills/story-setup/references/opencode/plugin.ts (hooks logic)")
    print("  - skills/story-setup/references/opencode/commands/ (slash commands)")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
