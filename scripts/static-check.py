#!/usr/bin/env python3
"""외부 의존성 없이 저장소 스킬 Markdown을 구조적으로 검증한다."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote


ATX_HEADING_RE = re.compile(r"^[ ]{0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+[ \t]*)?$")
OPEN_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
# 강조 기호가 스킬 내부 경로 전체를 감싼 형태만 복원한다. 시작/종료 표식의 길이가 같아야 하고
# 양옆에 ASCII 경로 문자가 붙어 있으면 안 된다. 그래야 CJK 문자가 붙은 references/*.md与references/*.json에서
# 두 glob 별표를 서로 다른 구간의 강조 기호 한 쌍으로 묶지 않는다.
EMPHASIS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<marker>\*{1,2})"
    r"(?P<path>(?:[a-z0-9_-]+/)?(?:references|scripts|assets)/[^\s*]+)"
    r"(?P=marker)(?![A-Za-z0-9_./-])"
)
SKILL_PATH_PREFIX = r"(?:[a-z0-9_-]+/)?(?:references|scripts|assets)/"
# 중국어 설명은 여러 경로를 `references/*.md与assets/*.json`처럼 붙여 쓰곤 한다. 반복 부분은 ‘연결어 +
# 다음 경로 접두사’ 앞에서 멈춰야 한다. 그렇지 않으면 첫 일치가 전체 문자열을 삼키고 normalize_path_token이 첫
# `*`에서 references/로 잘라 뒤의 누락 경로는 독립적으로 검증되지 않는다.
SKILL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<path>"
    + SKILL_PATH_PREFIX
    + r"(?:(?!(?:与|和|及|、)"
    + SKILL_PATH_PREFIX
    + r")[^\s`\"')\]><「（，。；：、])+)"
)
ASCII_MD_RE = re.compile(r"^[a-z0-9_-]+\.md$")
INLINE_MD_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9._-]+/)*[a-z0-9_-]+\.md)(?=$|[^A-Za-z0-9_.-])"
)
AGENT_REF_RES = (
    re.compile(r"subagent_type\s*:\s*\"([a-z][a-z0-9_-]*)\""),
    re.compile(r"subagent_type\s*=\s*\"([a-z][a-z0-9_-]*)\""),
    # 괄호 형식은 전각/반각 괄호와 콜론을 모두 허용한다(본문 표기에는 ‘（subagent_type: x）’가 흔하다).
    # 따옴표는 선택 사항이다. 괄호 종료 앵커를 유지한다. 호환성 설명에는 일반 `subagent_type` 용어가 많아
    # 괄호/따옴표 앵커 없이 인식하면 참조가 아닌 문맥도 에이전트 참조로 오인한다.
    re.compile(r"[（(]subagent_type\s*[:：]\s*\"?([a-z][a-z0-9_-]*)\"?\s*[)）]"),
)
# ‘SKILL.md + 절 이름 참고’는 링크로 검증할 수 없는 추측성 텍스트다. SKILL.md 제목을 바꾸면 참조가 조용히 끊어진다.
# 구분자 양쪽은 모두 \s*를 쓴다. 중국어 본문에서 흔한 ‘详见SKILL.md的阶段二流程’에는 공백이 없으므로
# `\s+`만 인정하면 이런 표기 전체가 규칙을 우회한다.
# 절 이름 첫 문자에서 괄호/따옴표/세로줄/해시를 제외한다. `见 SKILL.md「输出目录结构」`, `见 SKILL.md（…）`,
# 표의 `见 SKILL.md）|`는 제목을 그대로 참조하거나 문장을 끝내는 형태이며 이 규칙이 제거할 모호한 추측이 아니다.
UNLINKED_SECTION_RE = re.compile(
    r"(?:见|参考|参见|详见)\s*SKILL\.md\s*"
    r"[^\s，。；;、（）()「」『』【】《》〈〉\[\]{}<>#|\"'“”‘’]"
    r"[^，。；;\n]*"
)
EXTERNAL_SCHEMES = ("http://", "https://", "ftp://", "mailto:", "data:", "tel:")
DEPLOYED_RUNTIME_PREFIXES = (".claude/", ".codex/", ".opencode/", ".agents/")
# browser-cdp는 저장소에서 명시적으로 지정한 기반 스킬이다. 업무용
# 스킬은 그 실행기를 참조할 수 있지만 나머지 모든 스킬 간 파일 경로는
# 금지하여 각 도메인 워크플로가 자체 완결성을 유지하게 한다.
FOUNDATION_SKILL_REFERENCES = frozenset({"browser-cdp"})
# 변경 기록은 과거 상태를 기록하므로 인라인 경로는 당시의 참조다(삭제/이동/스킬 간 이전 파일 포함).
# 현재 런타임 의존성이 아니므로 스킬 간 참조/끊어진 링크 검사를 하지 않는다(check-current-skill-contracts.py와 동일한 제외 규칙).
CHANGELOG_DOCS = frozenset({"UPGRADING.md", "CHANGELOG.md"})
EXTERNAL_URL_RE = re.compile(
    r"(?i)\b(?:https?|ftp)://[^\s<>\"'`]+"
)
# 쉼표가 있는 중괄호 열거는 각각 이름을 지정하므로 구체적인 경로로 확장할 수 있다. `{题材}` 같은 단일 자리표시자는 열거가 아니다.
BRACE_LIST_RE = re.compile(r"\{([^{}/]*,[^{}/]*)\}")
# 스킬 간 검사는 모든 텍스트 자산을 다룬다. 템플릿(*.md.tmpl / *.json.patch)과 프런트엔드 자산도
# story-setup이 작가 프로젝트에 배포하므로 검사에서 빠지면 배포 영역의 ‘스킬 자체 완결성’ 원칙이 무력화된다.
SKILL_TEXT_SUFFIXES = {
    ".cmd",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".patch",
    ".py",
    ".sh",
    ".tmpl",
    ".toml",
    ".ts",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class SourceRef:
    line: int
    raw: str
    kind: str


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: Path
    line: int
    message: str


@dataclass
class Document:
    path: Path
    anchors: set[str] = field(default_factory=set)
    refs: list[SourceRef] = field(default_factory=list)
    agent_refs: list[tuple[int, str]] = field(default_factory=list)
    unlinked_sections: list[tuple[int, str]] = field(default_factory=list)


def display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def skill_owner(path: Path, root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to((root / "skills").resolve())
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else None


def markdown_slug(title: str) -> str:
    """이 저장소의 제목에 사용하는 GitHub 방식 부분집합을 반환한다."""

    result: list[str] = []
    for char in title.strip().lower():
        category = unicodedata.category(char)
        if char.isspace():
            result.append("-")
        elif char in "-_" or category[0] in {"L", "M", "N"}:
            result.append(char)
    return "".join(result)


def strip_link_title(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    match = re.match(r"^(.*?)(?:\s+[\"'].*[\"'])?$", target)
    return (match.group(1) if match else target).strip()


def is_external_ref(raw: str) -> bool:
    return raw.strip().lower().startswith(EXTERNAL_SCHEMES)


def strip_inline_markup(line: str) -> str:
    line = LINK_RE.sub("", line)
    return INLINE_CODE_RE.sub("", line)


def path_alternatives(raw: str) -> list[str]:
    """이름을 지정한 `{a,b,c}` 열거를 개별 경로로 확장한다.

    `{story_codex_hook.py,run-story-hook.sh,run-story-hook.cmd}`는 파일을 하나씩 지정한 것으로
    참조 세 개를 각각 쓰는 것과 같다. 확장 후 각각 존재 여부와 도달 가능성을 검증한다.
    `{题材}` 같은 단일 자리표시자는 열거가 아니므로 그대로 normalize_path_token에 넘겨
    와일드카드로 처리한다.
    """

    match = BRACE_LIST_RE.search(raw)
    if not match:
        return [raw]
    head, tail = raw[: match.start()], raw[match.end() :]
    parts = [part.strip() for part in match.group(1).split(",")]
    return [f"{head}{part}{tail}" for part in parts if part]


def normalize_path_token(raw: str) -> tuple[str, bool]:
    token = raw.rstrip(".,;:!?，。；：！？|）】」』")
    dynamic = any(char in token for char in "*?{[")
    if dynamic:
        cut = min((token.find(char) for char in "*?{[" if char in token), default=len(token))
        token = token[:cut]
        if token and not token.endswith("/"):
            token = token.rsplit("/", 1)[0] + "/"
    return token, dynamic


def parse_document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    document = Document(path=path)
    fence_char: str | None = None
    fence_size = 0
    slug_counts: dict[str, int] = {}

    for line_number, line in enumerate(text.splitlines(), start=1):
        if fence_char is not None:
            closing_fence = re.fullmatch(
                r"[ ]{0,3}"
                + re.escape(fence_char)
                + r"{"
                + str(fence_size)
                + r",}[ \t]*",
                line,
            )
            if closing_fence:
                fence_char = None
                fence_size = 0
            continue

        opening_fence = OPEN_FENCE_RE.match(line)
        if opening_fence:
            marker, info = opening_fence.groups()
            if marker[0] == "`" and "`" in info:
                opening_fence = None
            else:
                fence_char = marker[0]
                fence_size = len(marker)
                continue

        for pattern in AGENT_REF_RES:
            document.agent_refs.extend(
                (line_number, match.group(1)) for match in pattern.finditer(line)
            )

        heading = ATX_HEADING_RE.match(line)
        if heading:
            base = markdown_slug(heading.group(1))
            suffix = slug_counts.get(base, 0)
            slug_counts[base] = suffix + 1
            document.anchors.add(base if suffix == 0 else f"{base}-{suffix}")

        for match in LINK_RE.finditer(line):
            document.refs.append(
                SourceRef(line=line_number, raw=strip_link_title(match.group(1)), kind="link")
            )

        # 외부 URL은 원격 자원을 가리키며 저장소 내부 스킬 경로가 아니다(cross_skill_path_issues와 같은 규약).
        # 두 검사 경로 모두 먼저 URL을 제거해야 URL 끝부분(.../references/x.md)을 로컬 경로로 오탐하지 않는다.
        # 본문에서 굵게/기울임으로 감싼 경우도 복원한다. `**references/x.md**`의 `*`가 문자 클래스에 포함되면
        # 와일드카드로 오인해 상위 디렉터리에서 잘라 존재 검사를 건너뛴다. 인라인 코드 안에서는 강조를 복원하지 않는다.
        # 백틱 안의 `*`는 리터럴 와일드카드다.
        prose_without_code = EMPHASIS_PATH_RE.sub(
            r"\g<path>", EXTERNAL_URL_RE.sub("", LINK_RE.sub("", INLINE_CODE_RE.sub("", line)))
        )
        for match in SKILL_PATH_RE.finditer(prose_without_code):
            document.refs.extend(
                SourceRef(line=line_number, raw=alternative, kind="skill-path")
                for alternative in path_alternatives(match.group("path"))
            )

        for match in INLINE_CODE_RE.finditer(line):
            code = EXTERNAL_URL_RE.sub("", match.group(1)).strip()
            for path_match in SKILL_PATH_RE.finditer(code):
                document.refs.extend(
                    SourceRef(line=line_number, raw=alternative, kind="skill-path")
                    for alternative in path_alternatives(path_match.group("path"))
                )
            for path_match in INLINE_MD_PATH_RE.finditer(code):
                raw = path_match.group("path")
                base = Path(raw).name
                if ASCII_MD_RE.fullmatch(base) and not base.startswith("_"):
                    document.refs.append(SourceRef(line=line_number, raw=raw, kind="inline-md"))

        prose = strip_inline_markup(line)
        document.unlinked_sections.extend(
            (line_number, match.group(0).strip())
            for match in UNLINKED_SECTION_RE.finditer(prose)
        )

    return document


def parse_frontmatter(path: Path) -> tuple[dict[str, str], int | None]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, None
    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing is None:
        return {}, None
    values: dict[str, str] = {}
    for line in lines[1:closing]:
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip("\"'")
    return values, closing + 1


def resolve_ref(
    ref: SourceRef,
    document: Document,
    skill_dir: Path,
    root: Path,
    documents: dict[Path, Document],
) -> tuple[Path | None, str, bool, bool]:
    """(대상, 앵커, 로컬 참조 여부, 와일드카드 참조 여부)를 반환한다."""

    raw = ref.raw.strip()
    if not raw or is_external_ref(raw):
        return None, "", False, False

    path_part, separator, fragment = raw.partition("#")
    fragment = unquote(fragment).lower() if separator else ""
    dynamic = False
    candidates: list[Path]
    if ref.kind == "skill-path":
        path_part, dynamic = normalize_path_token(path_part)
        decoded = unquote(path_part)
        candidates = [skill_dir / decoded, root / decoded, root / "skills" / decoded]
    elif not path_part:
        candidates = [document.path]
    else:
        path_part, dynamic = normalize_path_token(path_part)
        decoded = unquote(path_part)
        if ref.kind == "link" and decoded.startswith("/"):
            candidates = [root / decoded.lstrip("/")]
        elif ref.kind == "link":
            # Markdown 링크 대상은 문서가 있는 위치를 기준으로 정확히 해석한다.
            # 더 넓은 대체 경로를 허용하면 같은 스킬의 다른 위치에 동명 파일이 있을 때
            # 끊어진 링크가 가려진다.
            candidates = [document.path.parent / decoded]
        elif ref.kind == "inline-md" and "/" not in decoded:
            candidates = [
                document.path.parent / decoded,
                skill_dir / decoded,
                skill_dir / "references" / decoded,
                skill_dir / "references/agent-references" / decoded,
                root / decoded,
                root / "skills" / decoded,
            ]
        else:
            candidates = [
                document.path.parent / decoded,
                skill_dir / decoded,
                root / decoded,
                root / "skills" / decoded,
            ]

    unique_candidates = list(dict.fromkeys(candidate.resolve() for candidate in candidates))
    local_candidates = [candidate for candidate in unique_candidates if inside_root(candidate, root)]
    selectable = local_candidates or unique_candidates
    target = next((candidate for candidate in selectable if candidate.exists()), selectable[0])

    if target.suffix.lower() == ".md" and target.is_file() and target not in documents:
        documents[target] = parse_document(target)
    return target, fragment, True, dynamic


def is_deployed_runtime_ref(
    ref: SourceRef,
    document: Document,
    skill_dir: Path,
    agent_names: set[str],
) -> bool:
    normalized = ref.raw.strip().replace("\\", "/")
    if normalized.startswith(DEPLOYED_RUNTIME_PREFIXES):
        return True
    if ref.kind == "inline-md" and "/" not in normalized and Path(normalized).stem in agent_names:
        return True
    try:
        relative = document.path.resolve().relative_to(skill_dir.resolve()).as_posix()
    except ValueError:
        return False
    return (
        normalized.startswith("scripts/")
        and ("/agents/" in f"/{relative}" or relative.startswith("references/templates/agents/"))
    )


def cross_skill_path_issues(skill_dir: Path, root: Path) -> list[Issue]:
    """다른 저장소 스킬로 향하는 명시적 파일 경로를 거부한다.

    각 런타임 스킬은 자체 완결성을 유지한다. Markdown 링크뿐 아니라 모든 텍스트 자산을 검사해
    주석, 생성된 에이전트 TOML, 실행 파일 도움말이 스킬 간 의존성을 조용히 다시 도입하지 못하게 한다.
    """

    skills_dir = root / "skills"
    skill_names = sorted(
        (
            path.name
            for path in skills_dir.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ),
        key=len,
        reverse=True,
    )
    if len(skill_names) < 2:
        return []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_-])(?P<skill>"
        + "|".join(re.escape(name) for name in skill_names)
        + r")[\\/]+(?P<asset>SKILL\.md|(?:references|scripts|assets)(?:[\\/]+|\b))"
    )
    issues: list[Issue] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SKILL_TEXT_SUFFIXES:
            continue
        if path.name in CHANGELOG_DOCS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            # URL 경로는 원격 자원 이름이며 저장소 스킬 가져오기 경로가 아니다.
            # 로컬 POSIX, Windows, 혼합 구분자 경로 토큰을 보존한다.
            local_text = EXTERNAL_URL_RE.sub("", line)
            for match in pattern.finditer(local_text):
                target_skill = match.group("skill")
                if (
                    target_skill == skill_dir.name
                    or target_skill in FOUNDATION_SKILL_REFERENCES
                ):
                    continue
                issues.append(
                    Issue(
                        "error",
                        "cross-skill-reference",
                        path,
                        line_number,
                        (
                            f"path enters skill {target_skill!r}; runtime skills must "
                            "carry their own files instead of reading another skill"
                        ),
                    )
                )
    return issues


def validate_skill(
    skill_dir: Path,
    root: Path,
    agent_names: set[str],
) -> list[Issue]:
    skill_file = skill_dir / "SKILL.md"
    issues: list[Issue] = []
    frontmatter, closing_line = parse_frontmatter(skill_file)
    if closing_line is None:
        issues.append(Issue("error", "frontmatter-block", skill_file, 1, "missing closed frontmatter block"))
    if not frontmatter.get("name"):
        issues.append(Issue("error", "frontmatter-name", skill_file, 1, "frontmatter requires a non-empty name"))
    elif frontmatter["name"] != skill_dir.name:
        issues.append(
            Issue(
                "error",
                "frontmatter-name",
                skill_file,
                2,
                f"frontmatter name must equal directory name {skill_dir.name!r}",
            )
        )
    if not frontmatter.get("description"):
        issues.append(
            Issue("error", "frontmatter-description", skill_file, 1, "frontmatter requires a non-empty description")
        )

    issues.extend(cross_skill_path_issues(skill_dir, root))

    markdown_paths = sorted(path for path in skill_dir.rglob("*.md") if path.is_file())
    documents = {path.resolve(): parse_document(path) for path in markdown_paths}
    resolved_by_document: dict[Path, set[Path]] = {path.resolve(): set() for path in markdown_paths}

    for document in list(documents.values()):
        # 변경 기록의 과거 인라인 경로는 끊어진 링크/스킬 간 검사에서 제외한다(다른 파일의 링크 대상은 될 수 있음).
        if document.path.name in CHANGELOG_DOCS:
            continue
        seen_refs: set[tuple[int, str, str]] = set()
        for ref in document.refs:
            key = (ref.line, ref.raw, ref.kind)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            if is_deployed_runtime_ref(ref, document, skill_dir, agent_names):
                continue
            target, fragment, local, dynamic = resolve_ref(
                ref, document, skill_dir, root, documents
            )
            if not local or target is None:
                continue
            if not inside_root(target, root):
                issues.append(
                    Issue(
                        "error",
                        "local-path-outside-root",
                        document.path,
                        ref.line,
                        f"local reference {ref.raw!r} escapes repository root",
                    )
                )
                continue
            target_owner = skill_owner(target, root)
            if (
                target_owner is not None
                and target_owner != skill_dir.name
                and target_owner not in FOUNDATION_SKILL_REFERENCES
            ):
                issues.append(
                    Issue(
                        "error",
                        "cross-skill-reference",
                        document.path,
                        ref.line,
                        (
                            f"{ref.raw!r} resolves into skill {target_owner!r}; "
                            "copy the required contract into this skill or use a runtime artifact"
                        ),
                    )
                )
                continue
            if not target.exists():
                issues.append(
                    Issue(
                        "error",
                        "broken-link-path" if ref.kind == "link" else "broken-inline-path",
                        document.path,
                        ref.line,
                        f"{ref.raw!r} resolves to missing {display(target, root)}",
                    )
                )
                continue
            # 와일드카드 참조는 범위만 선언한다(`references/*`는 이 스킬의 참조 디렉터리를 뜻함). 특정 파일을 지정하지
            # 않으므로 그 디렉터리를 도달 가능성의 시작점으로 쓰면 하위 트리 전체가 ‘참조됨’으로 표시되어
            # 해당 스킬의 dead-reference 검사가 영구히 무효화된다. 이름을 지정한 열거는 path_alternatives에서 이미 확장했다.
            if not (dynamic and target.is_dir()):
                resolved_by_document.setdefault(document.path.resolve(), set()).add(target)
            if fragment:
                target_document = documents.get(target)
                if target_document is None or fragment not in target_document.anchors:
                    issues.append(
                        Issue(
                            "error",
                            "broken-link-anchor",
                            document.path,
                            ref.line,
                            f"anchor #{fragment} does not exist in {display(target, root)}",
                        )
                    )

        for line, agent_name in sorted(set(document.agent_refs)):
            if agent_name not in agent_names:
                issues.append(
                    Issue(
                        "error",
                        "unknown-agent",
                        document.path,
                        line,
                        f"unknown subagent_type {agent_name!r}",
                    )
                )

        if document.path != skill_file:
            for line, phrase in document.unlinked_sections:
                issues.append(
                    Issue(
                        "error",
                        "unlinked-skill-section",
                        document.path,
                        line,
                        f"replace textual section guess {phrase!r} with a Markdown link to ../SKILL.md#anchor",
                    )
                )

    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        reached: set[Path] = set()
        queue: list[Path] = []

        def is_reference_content(candidate: Path) -> bool:
            # .gitkeep는 자리표시자이고 __pycache__는 .gitignore에 등록한 빌드 산출물이다. 둘 다 참조 내용이 아니다.
            return candidate.name != ".gitkeep" and "__pycache__" not in candidate.parts

        def add_target(target: Path) -> None:
            try:
                target.relative_to(references_dir.resolve())
            except ValueError:
                return
            candidates = [target] if target.is_file() else sorted(path for path in target.rglob("*") if path.is_file())
            for candidate in candidates:
                resolved = candidate.resolve()
                if not is_reference_content(candidate) or resolved in reached:
                    continue
                reached.add(resolved)
                if candidate.suffix.lower() == ".md":
                    queue.append(resolved)

        for target in resolved_by_document.get(skill_file.resolve(), set()):
            add_target(target)
        while queue:
            source = queue.pop()
            for target in resolved_by_document.get(source, set()):
                add_target(target)

        for candidate in sorted(path for path in references_dir.rglob("*") if path.is_file()):
            if not is_reference_content(candidate) or candidate.resolve() in reached:
                continue
            issues.append(
                Issue(
                    "warning",
                    "dead-reference",
                    candidate,
                    1,
                    "reference file is not reachable from SKILL.md through explicit paths or links",
                )
            )

    return sorted(
        issues,
        key=lambda issue: (display(issue.path, root), issue.line, issue.severity, issue.code),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        print(f"ERROR: skills/ not found at {skills_dir}", file=sys.stderr)
        return 2

    agent_dir = skills_dir / "story-setup/references/templates/agents"
    agent_names = {path.stem for path in agent_dir.glob("*.md")} if agent_dir.is_dir() else set()
    skill_dirs = sorted(path for path in skills_dir.iterdir() if (path / "SKILL.md").is_file())
    if not skill_dirs:
        print("ERROR: no skill entrypoints found", file=sys.stderr)
        return 2

    print("Skill Static Check")
    print("==================")
    print(f"Repo: {root}")

    passed = 0
    failed = 0
    warned = 0
    for skill_dir in skill_dirs:
        print(f"\n--- {skill_dir.name} ---")
        try:
            issues = validate_skill(skill_dir, root, agent_names)
        except (OSError, UnicodeError) as exc:
            issues = [Issue("error", "read-error", skill_dir / "SKILL.md", 1, str(exc))]
        errors = [issue for issue in issues if issue.severity == "error"]
        warnings = [issue for issue in issues if issue.severity == "warning"]
        if not issues:
            print("  [PASS] structured frontmatter, links, anchors, agents, and references")
        for issue in issues:
            label = "FAIL" if issue.severity == "error" else "WARN"
            print(
                f"  [{label}] [{issue.code}] {display(issue.path, root)}:{issue.line}: {issue.message}"
            )
        if errors:
            failed += 1
            print(f"  Result: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
        else:
            passed += 1
            if warnings:
                warned += 1
                print(f"  Result: PASS ({len(warnings)} warnings)")
            else:
                print("  Result: PASS")

    print("\n==================")
    print(f"Total: {len(skill_dirs)} | Pass: {passed} | Fail: {failed} | Warn: {warned}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
