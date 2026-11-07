#!/usr/bin/env python3
"""저장소의 현재 버전 전용 스킬 및 산출물 계약을 검증한다.

JSON 매니페스트는 버전 번호, 주요 벤치마크 산출물, 개요 절의 유일한 구조화 목록이다.
이 모듈은 기존 경로/레거시 검사도 유지하되, 셸 grep 호출의 연결 대신 범위를 제한한 파일 순회와
조치 가능한 진단으로 구현한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple


SUPPORTED_MANIFEST_VERSION = 1
EXPECTED_MANIFEST_KEYS = {
    "manifest_version",
    "setup_skill_version",
    "agents_version",
    "topic_decision_phase",
    "progress_schema_version",
    "primary_benchmark_artifacts",
    "required_outline_sections",
}
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
ARTIFACT_PATH_RE = re.compile(r"(?:[^/\s]+/)+[^/\s]+\.md")


@dataclass(frozen=True)
class ContractManifest:
    manifest_version: int
    setup_skill_version: str
    agents_version: int
    topic_decision_phase: int
    progress_schema_version: int
    primary_benchmark_artifacts: Tuple[str, ...]
    required_outline_sections: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    path: Optional[Path] = None
    line: Optional[int] = None
    excerpt: Optional[str] = None

    def detail(self, repo_root: Path) -> str:
        location = ""
        if self.path is not None:
            try:
                shown = self.path.resolve().relative_to(repo_root.resolve())
            except ValueError:
                shown = self.path
            location = str(shown)
            if self.line is not None:
                location += ":{}".format(self.line)
            location += ": "
        suffix = ""
        if self.excerpt:
            suffix = " [{}]".format(self.excerpt.strip())
        return "{}{}{}".format(location, self.message, suffix)


@dataclass(frozen=True)
class AbsentRule:
    code: str
    label: str
    pattern: str
    relative_roots: Tuple[str, ...]
    # ‘조용한 대체만 금지’ 예외: 일치한 줄의 주변에 명시적 허용 표식(不阻塞 / [待补充] / 回退 /
    # 只核对 / 记录 등)이 있으면 기록된 기존 형식 허용으로 보고 통과시킨다. 기존 형식 개요 허용에만 적용한다.
    # (keep C). 벤치마크 대체(drop A/B) 규칙은 예외 없이 명시적·암묵적 대체를 모두 금지한다.
    exempt_when: Optional[str] = None


LEGACY_RULES = (
    AbsentRule(
        "legacy-progress-branch",
        "no legacy deconstruction/progress branches",
        r"legacy_deconstruction|contract_version[^\n]*legacy|pre-v12|schema v1|lazy migration|schema_migration",
        ("skills",),
    ),
    AbsentRule(
        "old-artifact-prose",
        "no silent old artifact-format downgrade",
        r"旧拆文库|旧版细纲|旧式薄细纲|旧版内部降级标记|早期拆文库格式|兼容旧结构",
        ("skills",),
        # keep C: 기존 형식 개요/상세 개요 허용은 명시적으로 기록한다(일일 집필을 막지 않음, 기존 필드로 대체 읽기, 알 수 없는 값은
        # [待补充]로 표시, 추적에 기록). 이러한 표식은 허용하고 표식 없는 조용한 호환 처리만 차단한다.
        exempt_when=r"不阻塞|\[待补充\]|回退|只核对|记录|保留或映射|仍可续写|仍可用|仍要保留",
    ),
    AbsentRule(
        "removed-hook-alias",
        "removed hook alias stays removed",
        r"discover_book_dir\s*\(",
        ("skills/story-setup/references/templates/hooks",),
    ),
    AbsentRule(
        "obsolete-short-benchmark-path",
        "short writing uses only current benchmark paths",
        r"\{短篇标题\}/작품분석실/\{书名\}",
        ("skills/story-short-write",),
    ),
    AbsentRule(
        "dotted-demo-workflow-label",
        "shipped demos do not preserve dotted workflow labels",
        r"(?:Step|Phase|Stage)\s*[0-9]+\.[0-9]+",
        ("demo",),
    ),
    AbsentRule(
        "obsolete-topic-decision-acceptance",
        "long analyze does not silently accept obsolete topic-decision contracts",
        r"旧模板或文件坏了|直接跳过，不提示",
        ("skills/story-long-analyze",),
    ),
    AbsentRule(
        "duplicate-adapter-reference-fallback",
        "story-setup deploys one canonical reference path per adapter",
        r"同步复制到\s*`skills/[^`]+`\s*作为 fallback",
        # 진입점에는 공통 흐름만 남기고 호스트별 복사 절차는 references/deploy-*.md에 둔다. 두 위치를 모두 검사한다.
        ("skills/story-setup/SKILL.md", "skills/story-setup/references"),
    ),
    AbsentRule(
        "opencode-old-reference-prefix",
        "OpenCode agents use the deployed skills/ reference path only",
        r"\.opencode/skills/story-setup/references/agent-references/",
        ("skills/story-setup/references/opencode/agents",),
    ),
    AbsentRule(
        "codex-old-reference-prefix",
        "Codex agents use the deployed .codex/skills reference path only",
        r"\.(?:claude|opencode)/skills/story-setup/references/agent-references/|\{项目根\}/skills/story-setup/references/agent-references/",
        ("skills/story-setup/references/codex/agents",),
    ),
    AbsentRule(
        "story-import-self-main-benchmark",
        "story-import never registers the imported work itself as a benchmark",
        r"导入当前书时至少登记自身|主对标书:\s*\{书名\}",
        ("skills/story-import",),
    ),
    AbsentRule(
        "story-import-self-benchmark-copy",
        "story-import keeps imported-work analysis out of benchmark views",
        r"\{项目\}/비교작품/\{书名\}|\{标题\}/비교작품/\{书名\}|비교작품/\{书名\}/플롯",
        ("skills/story-import",),
    ),
    AbsentRule(
        "story-import-import-title-benchmark-target",
        "story-import never copies imported-work analysis into a benchmark target",
        r"작품분석실/\{导入书名\}[^\n]{0,160}(?:复制|同步|迁移)[^\n]{0,120}(?:对标|비교작품)|비교작품/\{导入书名\}",
        ("skills/story-import",),
        exempt_when=r"不得|禁止|严禁|未被|不复制|不属于|不是对标",
    ),
    AbsentRule(
        "story-import-self-benchmark-summary",
        "story-import does not label the imported work's own analysis as a benchmark summary",
        r"对标摘要：\{原书名\}",
        ("skills/story-import",),
    ),
    AbsentRule(
        "story-import-self-benchmark-fields",
        "story-import does not map self-benchmark fields into the imported project's settings",
        r"작품분석보고서\.md`?\s*的故事核/题材/对标字段",
        ("skills/story-import",),
    ),
    AbsentRule(
        "benchmark-primary-nonblocking-wording",
        "missing benchmark primary artifacts never use a nonblocking fallback",
        r"缺失按原流程，不阻塞",
        ("skills/story-long-write",),
    ),
    AbsentRule(
        "no-benchmark-skips-genre-card",
        "no-benchmark writing still generates the project genre prose card",
        r"无对标[^\n]{0,160}跳过[^\n]{0,80}对标模块/节奏/题材卡/文风召回",
        ("skills/story-long-write",),
    ),
    AbsentRule(
        "style-profile-all-inputs-required",
        "Stage 6 prerequisites follow the explicit degradation matrix",
        r"前置依赖：[^\n]*齐全",
        ("skills/story-long-analyze/references/style-profile-generator.md",),
    ),
    AbsentRule(
        "context-missing-skips-all",
        "single-chapter context follows item-specific missing-file decisions",
        r"按需加载，缺失则跳过",
        ("skills/story-long-write/SKILL.md",),
    ),
    AbsentRule(
        "static-long-word-floor",
        "long-form release uses the outline target and one 90-percent tolerance",
        r"默认最低字数[^\n]*3000\s*字/章|"
        r"长篇写作以章为验证粒度[^\n]*(?:2000|3000)\s*字|"
        r"(?:高速推进|正常节奏|舒缓铺垫|高潮爆发)\s*\|\s*≥\s*(?:2000|3000)\s*字/章",
        (
            "skills/story-long-write/SKILL.md",
            "skills/story-setup/references/templates/agents/narrative-writer.md",
            "skills/story-setup/references/opencode/agents/narrative-writer.md",
            "skills/story-setup/references/codex/agents/narrative-writer.toml",
        ),
    ),
    AbsentRule(
        "broad-chrome-cleanup-doc",
        "browser cleanup docs must not bypass consent with executable-name kills",
        r"pkill[^\n]*(?:Google Chrome|google-chrome|chrome)|"
        r"taskkill[^\n]*/IM\s+chrome\.exe",
        ("skills/browser-cdp/SKILL.md",),
    ),
    AbsentRule(
        "analyze-posix-tmp-sample-path",
        "style sampling stays on a project-relative path Windows python can open",
        r"/tmp/style-sample",
        ("skills/story-long-analyze",),
    ),
    # 문체.md를 책 디렉터리 존재 여부를 확인하는 탐침으로 겸용하면 문체 파일이 없는 책을 책 자체가 없는 것으로 판단한다. explorer는
    # 3단계에서 benchmark_book_missing을 조기 반환하고 6단계의 profile_missing은 도달 불가능해진다.
    # 그러면 호출자의 profile_missing + custom_style 대체 집필 분기 전체가 사라진다. 디렉터리 존재 여부는
    # 그 안의 임의 파일로 확인하고, 문체 파일 누락은 별도로 profile_missing으로 분류해야 한다.
    AbsentRule(
        "style-profile-as-book-existence-probe",
        "benchmark book existence is probed by any file under the book dir, never by 문체.md",
        r"(?:优先探|回退探)[^\n]{0,60}\{书名\}/문체\.md|"
        r"Glob\s*`?(?:对标|拆文库|비교작품|작품분석실)/\*/문체\.md",
        (
            "skills/story-setup/references/agent-references/benchmark-style-load.md",
            "skills/story-setup/references/templates/agents/story-explorer.md",
            "skills/story-setup/references/opencode/agents/story-explorer.md",
            "skills/story-setup/references/codex/agents/story-explorer.toml",
        ),
    ),
    # 현재 글자 수 기준은 의미상 사건점을 고정 분량으로 환산하지 않는다. 이전 합계/Σ 계약은 분량을 채우려고 사건을 자동 추가하도록 유도한다.
    AbsentRule(
        "forbidden-outline-numeric-capacity",
        "outline beats never use numeric totals or sigma bands to predict prose capacity",
        r"预算合计|目标字数合计|Σ∈\[章目标",
        (
            "skills/story-long-write/references/workflow-volume.md",
            "skills/story-long-write/references/workflow-outline.md",
            "skills/story-long-write/references/artifact-protocols.md",
            "skills/story-setup/references/templates/rules/story-outline.md",
            "skills/story-setup/references/templates/agents/story-architect.md",
            "skills/story-setup/references/opencode/agents/story-architect.md",
            "skills/story-setup/references/codex/agents/story-architect.toml",
        ),
        exempt_when=r"不得|禁止|已废弃|旧字段|旧口径",
    ),
)


SPAWN_CAPABLE_SKILLS = (
    "skills/story/SKILL.md",
    "skills/story-deslop/SKILL.md",
    "skills/story-import/SKILL.md",
    "skills/story-long-analyze/SKILL.md",
    "skills/story-long-write/SKILL.md",
    "skills/story-review/SKILL.md",
    "skills/story-short-write/SKILL.md",
)


# 상세 개요 구조 분량의 기준 사본과 소비자: 각 지점에는 의미상 의무만 쓰고 숫자 할당량은 기입하지 않는다.
OUTLINE_SEMANTIC_CAPACITY_CONSUMERS = (
    "skills/story-long-write/references/workflow-outline.md",
    "skills/story-setup/references/templates/rules/story-outline.md",
)


PRIMARY_GAP_TERMS = (
    "module_missing",
    "rhythm_missing",
    "missing_primary_contract",
    "主产物",
    "权威文件",
    "主文件",
)
MISSING_STATE_RE = r"(?:缺失|不存在|未找到|找不到|为\s*(?:true|真)|:\s*true)"
SUBSTITUTE_SOURCE_RE = re.compile(
    r"章节(?:/\*|/第[^\s`，。；;]*)?_?摘要(?:\.md)?|第[^\s`，。；;]*章_요약(?:\.md)?|"
    r"(?:拆文报告|작품분석보고서)(?:\.md)?|(?:故事线|이야기선)(?:\.md)?|장별분석/[^`，。；;]*_요약\.md",
    re.IGNORECASE,
)
SUBSTITUTE_ACTION_RE = re.compile(
    r"回退|fallback|改读|转读|读取|使用|采用|改用|替代|代替|顶替|补足|补齐|拼出|兜底|"
    r"substitut(?:e|ion)",
    re.IGNORECASE,
)
PROHIBITION_RE = re.compile(
    r"不得|禁止|严禁|不允许|不可|不要|不能|不应|must\s+not|do\s+not|never",
    re.IGNORECASE,
)


def primary_term_pattern(primary_artifacts: Sequence[str]) -> str:
    """흔히 쓰는 로컬 약칭을 포함해 매니페스트에서 산출물 용어를 구성한다."""

    terms = set(PRIMARY_GAP_TERMS)
    for artifact in primary_artifacts:
        normalized = artifact.replace("\\", "/")
        basename = normalized.rsplit("/", 1)[-1]
        for value in (normalized, basename):
            terms.add(value)
            if value.endswith(".md"):
                terms.add(value[:-3])
    return "(?:{})".format(
        "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_manifest(path: Path) -> Tuple[Optional[ContractManifest], List[Finding]]:
    findings: List[Finding] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [Finding("manifest-missing", "current contract manifest is missing", path)]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [Finding("manifest-invalid-json", "cannot parse manifest: {}".format(exc), path)]

    if not isinstance(raw, dict):
        return None, [Finding("manifest-type", "manifest root must be a JSON object", path)]

    keys = set(raw)
    for missing in sorted(EXPECTED_MANIFEST_KEYS - keys):
        findings.append(Finding("manifest-key-missing", "missing manifest key: {}".format(missing), path))
    for unknown in sorted(keys - EXPECTED_MANIFEST_KEYS):
        findings.append(Finding("manifest-key-unknown", "unknown manifest key: {}".format(unknown), path))

    if "manifest_version" in raw:
        if not _is_int(raw["manifest_version"]):
            findings.append(Finding("manifest-value-type", "manifest_version has the wrong type", path))
        elif raw["manifest_version"] != SUPPORTED_MANIFEST_VERSION:
            findings.append(
                Finding(
                    "manifest-version-unsupported",
                    "manifest_version must be {}, got {}".format(
                        SUPPORTED_MANIFEST_VERSION, raw["manifest_version"]
                    ),
                    path,
                )
            )

    setup_version = raw.get("setup_skill_version")
    if not isinstance(setup_version, str):
        if "setup_skill_version" in raw:
            findings.append(Finding("manifest-value-type", "setup_skill_version has the wrong type", path))
    elif not SEMVER_RE.fullmatch(setup_version):
        findings.append(Finding("manifest-value-format", "setup_skill_version must be x.y.z", path))

    for key in (
        "agents_version",
        "topic_decision_phase",
        "progress_schema_version",
    ):
        if key not in raw:
            continue
        if not _is_int(raw[key]):
            findings.append(Finding("manifest-value-type", "{} has the wrong type".format(key), path))
        elif raw[key] < 1:
            findings.append(Finding("manifest-value-range", "{} must be a positive integer".format(key), path))

    artifacts = raw.get("primary_benchmark_artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, str) for item in artifacts):
        findings.append(Finding("manifest-artifact-type", "primary_benchmark_artifacts must be a string array", path))
    elif not artifacts:
        findings.append(Finding("manifest-artifact-empty", "primary_benchmark_artifacts must not be empty", path))
    elif len(set(artifacts)) != len(artifacts):
        findings.append(Finding("manifest-artifact-duplicate", "primary_benchmark_artifacts must be unique", path))
    elif any(ARTIFACT_PATH_RE.fullmatch(item) is None for item in artifacts):
        findings.append(
            Finding(
                "manifest-artifact-format",
                "primary benchmark artifacts must be relative Markdown paths",
                path,
            )
        )

    sections = raw.get("required_outline_sections")
    valid_sections = isinstance(sections, list) and bool(sections) and all(
        isinstance(item, dict)
        and set(item) == {"rule", "demo"}
        and isinstance(item.get("rule"), str) and bool(item["rule"].strip())
        and isinstance(item.get("demo"), str) and bool(item["demo"].strip())
        for item in sections or []
    )
    if not valid_sections:
        findings.append(
            Finding(
                "manifest-outline-type",
                "required_outline_sections must be an array of exact {rule, demo} string objects",
                path,
            )
        )
    elif (
        len({item["rule"] for item in sections}) != len(sections)
        or len({item["demo"] for item in sections}) != len(sections)
    ):
        findings.append(
            Finding(
                "manifest-outline-duplicate",
                "required_outline_sections must use unique rule and demo names",
                path,
            )
        )

    if findings:
        return None, findings

    assert isinstance(artifacts, list)
    assert isinstance(sections, list)
    manifest = ContractManifest(
        manifest_version=raw["manifest_version"],
        setup_skill_version=raw["setup_skill_version"],
        agents_version=raw["agents_version"],
        topic_decision_phase=raw["topic_decision_phase"],
        progress_schema_version=raw["progress_schema_version"],
        primary_benchmark_artifacts=tuple(artifacts),
        required_outline_sections=tuple((item["rule"], item["demo"]) for item in sections),
    )
    return manifest, []


def iter_files(root: Path) -> Iterator[Path]:
    if root.is_file():
        if root.name not in {"UPGRADING.md", "CHANGELOG.md"}:
            yield root
        return
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"UPGRADING.md", "CHANGELOG.md"}:
            continue
        if any(part in {".git", ".omx"} for part in path.parts):
            continue
        yield path


def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


# 바이너리 자산(데모 표지, __pycache__ 바이트코드)을 텍스트로 읽을 수 없는 것은 정상이며 건너뛴다. 나머지 파일은
# 모두 UTF-8 텍스트로 취급한다. GBK/cp936 Markdown은 모든 내용 규칙을 무력화한다. regex_hits가
# None을 받으면 ‘일치 없음’으로 보고 [PASS]를 출력하기 때문이다. 따라서 텍스트 디코딩 실패는 건너뛰지 말고 명명된 오류로 보고해야 한다.
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".mp3",
        ".mp4",
        ".pyc",
        ".pyo",
        ".so",
        ".dylib",
    }
)

TEXT_SUFFIXES = frozenset(
    {
        ".cmd",
        ".css",
        ".csv",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".patch",
        ".py",
        ".sh",
        ".svg",
        ".tmpl",
        ".toml",
        ".ts",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


def is_binary_asset(path: Path) -> bool:
    """바이너리 자산(표지 이미지, 바이트코드, .DS_Store 등)을 텍스트로 읽을 수 없는 것은 정상이다.

    확장자 허용 목록에 없으면 NUL 바이트 여부도 확인한다. 그러면 .DS_Store나 확장자 없는 바이너리는
    오탐하지 않고, NUL이 없는 GBK/cp936 Markdown은 수정해야 하는 텍스트 파일로 분류한다. 바이트를
    읽지 못하면 텍스트로 취급한다. 조용히 허용하기보다 오류를 보고한다.
    """
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    # UTF-16 텍스트에도 NUL이 많이 들어 있다. 알려진 텍스트 확장자는 먼저 계약 텍스트로 처리해 UTF-8 디코딩 실패를
    # 명명된 오류로 만든다. NUL 탐지는 .DS_Store나 알 수 없는 바이너리 확장자에만 적용하며 파일 형식 판단을 덮어쓰지 않는다.
    if path.suffix.lower() in TEXT_SUFFIXES:
        return False
    try:
        return b"\x00" in path.read_bytes()[:8192]
    except OSError:
        return False


def undecodable_source_findings(roots: Sequence[Path]) -> List[Finding]:
    """내용 규칙으로 검사하는 텍스트는 UTF-8로 읽을 수 있어야 한다. 그렇지 않으면 규칙 전체가 조용히 통과한다."""
    findings: List[Finding] = []
    seen: set[str] = set()
    for root in roots:
        for path in iter_files(root):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            if read_text(path) is not None:
                continue
            if is_binary_asset(path):
                continue
            findings.append(
                Finding(
                    "unreadable-source-file",
                    "contract guards need UTF-8 text; this file cannot be read as UTF-8",
                    path,
                )
            )
    return findings


def regex_hits(path: Path, pattern: re.Pattern[str]) -> Iterator[Finding]:
    text = read_text(path)
    if text is None:
        return
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        excerpt = text.splitlines()[line - 1] if text.splitlines() else ""
        yield Finding("", "", path, line, excerpt)


def check_absent_rule(repo_root: Path, rule: AbsentRule) -> List[Finding]:
    compiled = re.compile(rule.pattern)
    exempt = re.compile(rule.exempt_when) if rule.exempt_when else None
    findings: List[Finding] = []
    for relative_root in rule.relative_roots:
        root = repo_root / relative_root
        for path in iter_files(root):
            for hit in regex_hits(path, compiled):
                if exempt is not None:
                    # 일치한 줄 자체만 본다. 명시적 허용 표식이 기존 형식 표현과 같은 줄에 있어야 근거가 있는 것으로 인정한다.
                    # 인접한 조용한 대체 처리가 앞줄 표식을 빌려 검사를 통과하지 못하게 한다.
                    if exempt.search(hit.excerpt):
                        continue
                findings.append(
                    Finding(rule.code, rule.label, hit.path, hit.line, hit.excerpt)
                )
    return findings


# 목록 항목과 표 행은 각각 독립된 기록이다. 조건과 동작이 같은 기록(또는 그 상위)에 있어야 하나의 규칙으로 본다.
BLOCK_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]\s+|[0-9]+[.)]\s+|\|)")


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _block_item_indent(line: str) -> Optional[int]:
    """목록 항목/표 행은 들여쓰기를, 일반 본문 줄은 None을 반환한다."""
    match = BLOCK_ITEM_RE.match(line)
    if match is None:
        return None
    return len(match.group(1).expandtabs(4))


def logical_bullet_context(lines: Sequence[str], index: int) -> str:
    """일치한 줄과 실제로 해당 줄을 지배하는 분기를 반환한다.

    하나의 논리 항목은 일치 줄, 그 항목의 이어지는 줄, 더 얕게 들여쓴 상위 항목 또는 목록/표 도입 문장이다.
    조건은 상위에 자주 있으므로 읽어야 한다(`任一主产物缺失时：` 뒤의 들여쓴 하위 항목이나 표 행 등).
    하지만 같은 단계의 형제 항목은 독립 계약이다. 인접한 즉시 실패 항목의 ‘주요 산출물 누락’ 조건을
    이 줄에 빌려주면 안 된다. 그러면 ‘두 주요 산출물이 모두 있을 때 `작품분석보고서.md`를 읽는다’ 같은 올바른
    문서를 조용한 대체로 오판한다. 빈 줄과 제목을 넘어가지 않는다.
    """
    parts = [lines[index]]
    own_item_indent = _block_item_indent(lines[index])
    threshold = (
        own_item_indent if own_item_indent is not None else _indent_width(lines[index])
    )
    cursor = index - 1
    while cursor >= 0:
        candidate = lines[cursor]
        if not candidate.strip() or candidate.lstrip().startswith("#"):
            break
        item_indent = _block_item_indent(candidate)
        indent = item_indent if item_indent is not None else _indent_width(candidate)
        # 상위 항목(더 얕은 들여쓰기) 또는 같은 단계의 도입 문장/이어지는 줄: 조건이 전체 하위 트리에 적용되므로 문맥에 포함한다.
        # 나머지는 같은 단계나 더 깊은 형제 항목과 그 연속 줄이다. 일치 줄과 무관하므로 건너뛰되 상위 항목 탐색은 계속한다.
        if indent < threshold or (item_indent is None and indent <= threshold):
            parts.insert(0, candidate)
            threshold = indent
        cursor -= 1
    return "\n".join(parts)


def semantic_primary_fallback_findings(
    text: str,
    path: Path,
    primary_artifacts: Sequence[str],
) -> List[Finding]:
    """주요 벤치마크 산출물이 없을 때의 긍정형 대체 분기를 찾는다.

    탐지는 의도적으로 가까운 문맥으로 제한한다. 대체 출처/동작은 같은 줄에 있어야 하고 주요 산출물
    누락 조건은 그 줄 또는 해당 줄을 지배하는 목록 분기(자체 연속 줄과 더 얕은 상위 항목)에 있어야 한다.
    형제 항목은 독립 계약이므로 조건을 공유하지 않는다. ‘不得以拆文报告代替’ 같은 명시적 금지절은 허용한다.
    """
    findings: List[Finding] = []
    lines = text.splitlines()
    primary_terms = primary_term_pattern(primary_artifacts)
    primary_missing = re.compile(
        primary_terms + r".{0,50}" + MISSING_STATE_RE,
        re.IGNORECASE,
    )
    primary_missing_reversed = re.compile(
        MISSING_STATE_RE + r".{0,50}" + primary_terms,
        re.IGNORECASE,
    )
    primary_artifact = re.compile(primary_terms, re.IGNORECASE)
    for index, line in enumerate(lines):
        # 자연어 절 하나 안에서 동작과 그 출처를 연결한다.
        # 한 줄에서 장 요약을 읽은 뒤 심층 분석에서
        # 다른 심층 분석으로 대체하는 것은 유효할 수 있다. 줄 전체의 동시 출현만 보면
        # 이를 주요 산출물 대체로 잘못 분류하게 된다.
        substitute_clauses = [
            clause
            for clause in re.split(r"\）、|[，,；;。！？!?]", line)
            if SUBSTITUTE_SOURCE_RE.search(clause)
            and SUBSTITUTE_ACTION_RE.search(clause)
            and not PROHIBITION_RE.search(clause)
        ]
        if not substitute_clauses:
            continue
        context = logical_bullet_context(lines, index)
        has_missing = bool(
            primary_missing.search(context) or primary_missing_reversed.search(context)
        )
        has_primary = bool(primary_artifact.search(context))
        if not has_missing or not has_primary:
            continue
        findings.append(
            Finding(
                "silent-primary-artifact-fallback",
                "missing primary benchmark artifacts must fail fast; do not substitute summaries, 拆文报告, or 故事线",
                path,
                index + 1,
                substitute_clauses[0].strip() or line,
            )
        )
    return findings


def require_pattern(path: Path, pattern: str, code: str, message: str) -> List[Finding]:
    text = read_text(path)
    if text is None:
        return [Finding(code, "cannot read required file", path)]
    if re.search(pattern, text, re.MULTILINE):
        return []
    return [Finding(code, message, path)]


# 작가용 분석 템플릿(대화 응답, 빠른 미리 보기, 분석 보고서)에 개발 내부 표현을 넣지 않는다. 작가는
# 필드명, 배치 번호, 스크립트명, 내부 지표를 알 수 없고 실제 실행에서는 모델이 이를 보고서에 그대로 복사한다.
AUTHOR_FACING_FORBIDDEN = (
    (r"\b(?:classification|recommended_path|stage_repairs|final_state|direct_use|current_complete|legacy_complete|batches)\b",
     "runtime field or status name"),
    (r"[A-Za-z]+_[A-Za-z0-9_]+", "snake_case identifier"),
    (r"(?:RAW|REUSE)-(?:\d|\{)", "batch id"),
    (r"\.py\b|(?<![\w-])--[a-z]", "script name or command flag"),
    (r"\b(?:Stage|Phase)\s*\d", "internal stage number"),
    (r"置信度|覆盖率|重叠率|三维", "internal metric wording"),
    (r"(?<![A-Za-z])[ABC]\s*级", "evidence grade letter"),
    (r"(?<![（(A-Za-z0-9])(?:EM|REL|EV|RV|AX)-(?:\d|\*|x|\{)", "internal id without a human label"),
    (r"_progress|_analysis_cache|sha256|\bhash\b|(?i:json)", "internal file or data format"),
)
FENCE_RE = re.compile(r"^(`{3,})[^\n]*\n(.*?)^\1\s*$", re.MULTILINE | re.DOTALL)


# 분석 자료는 시점별로 로드한다. 진입점의 시점별 읽기 표가 각 시점에 읽을 파일을 정하는 유일한 경로다. 단계 파일이 표에서
# 빠지면 해당 시점에는 모델이 예전의 큰 파일을 추측해서 통째로 읽어야 하므로 시점별 35K 상한이 무효화된다.
ANALYZE_MOMENT_ROUTES = (
    (
        "skills/story-long-analyze/SKILL.md",
        "## 按时刻读",
        (
            "stage1-golden-chapters.md", "index-rebuild.md", "pipeline-ops.md", "stage2-extraction.md",
            "synthesis-inputs.md", "stage3-plot-rhythm.md", "stage4-characters-settings.md",
            "stage5-report.md", "style-profile-generator.md", "final-checks.md",
        ),
    ),
    (
        "skills/story-short-analyze/SKILL.md",
        "### 按时刻读",
        (
            "output-contract.md", "analysis-method.md", "stage2-3-structure-emotion.md",
            "stage4-6-reversal-summary.md", "quality-checklist.md", "analysis-report-style.md",
        ),
    ),
)


def analyze_moment_routing_findings(repo_root: Path) -> List[Finding]:
    findings: List[Finding] = []
    for relative, heading, files in ANALYZE_MOMENT_ROUTES:
        path = repo_root / relative
        text = read_text(path)
        if text is None or heading not in text:
            findings.append(Finding("analyze-moment-routing", "missing moment routing table {!r}".format(heading), path))
            continue
        level = heading.split(" ", 1)[0]
        section = text.split(heading, 1)[1]
        section = re.split(r"^#{{1,{}}} ".format(len(level)), section, maxsplit=1, flags=re.MULTILINE)[0]
        for name in files:
            if "(references/{})".format(name) not in section:
                findings.append(Finding(
                    "analyze-moment-routing",
                    "moment routing table must link references/{}".format(name),
                    path,
                ))
    return findings


def analyze_dispatch_default_findings(path: Path) -> List[Finding]:
    """첫 세 장을 분석한 뒤 멈춰 물을 때, 배정 방식은 미리 정해 두고 기술적 선택을 작가에게 넘기지 않는다."""
    text = read_text(path)
    if text is None:
        return [Finding("analyze-dispatch-default", "cannot read author-facing templates", path)]
    match = re.search(r"^### (?:开头三章拆完、停下来问|첫 세 장 분석 후 멈추고 확인)\n(.*?)(?=^### )", text, re.MULTILINE | re.DOTALL)
    if match is None:
        return [Finding("analyze-dispatch-default", "missing the stop-after-opening template", path)]
    if re.search(r"想怎么拆|어떤 방식으로 분석|^\d+\.\s", match.group(1), re.MULTILINE):
        return [Finding(
            "analyze-dispatch-default",
            "stop-after-opening must default the dispatch mode instead of asking the author to pick one",
            path,
        )]
    return []


def author_facing_findings(path: Path) -> List[Finding]:
    """작가용 참조 자료의 모든 코드 블록은 작가가 그대로 읽는 텍스트다."""
    text = read_text(path)
    if text is None:
        return [Finding("author-facing-template-missing", "cannot read author-facing templates", path)]
    findings: List[Finding] = []
    blocks = list(FENCE_RE.finditer(text))
    if not blocks:
        return [Finding("author-facing-template-missing", "author-facing reference has no template blocks", path)]
    for block in blocks:
        start_line = text.count("\n", 0, block.start(2)) + 1
        for offset, line in enumerate(block.group(2).splitlines()):
            for pattern, label in AUTHOR_FACING_FORBIDDEN:
                match = re.search(pattern, line)
                if match:
                    findings.append(Finding(
                        "author-facing-engineering-token",
                        "author-facing template contains {}: {!r}".format(label, match.group(0)),
                        path, start_line + offset, line.strip(),
                    ))
    return findings


def spawn_preflight_findings(
    text: str, manifest: ContractManifest, path: Path
) -> List[Finding]:
    """에이전트를 실행할 수 있는 모든 스킬은 오래되거나 미래 버전인 에이전트 묶음을 알려야 한다.

    버전 불일치는 알리기만 하고 차단하지 않는다. 다른 배포 산출물이 바뀌어 버전이 올라가도 에이전트
    템플릿은 그대로인 경우가 많다(v23은 story-explorer만 변경). 강제 차단하면 모든 사용자가 무관한
    변경 때문에 병렬 처리 비용을 치른다. 실제 대체 처리 신호는 현재 호스트에 역할이 없거나 런타임이
    호출 기능을 노출하지 않는 경우다. 플러그인 역할에는 프로젝트 파일이 필요하지 않다.
    """

    current = str(manifest.agents_version)
    fallback_pattern = r"只有当前宿主角色缺失或不暴露调用能力时才降级 solo/direct"
    if path.as_posix().endswith("skills/story-review/SKILL.md"):
        fallback_pattern = (
            r"版本提示本身不触发降级；文件缺失或异常、工具不可用、递归限制或调用失败按 Phase 0 处理"
        )
    required = (
        (r"`agents_version:\s*{}`".format(current), "pin the current agents_version"),
        (
            r"照常按当前宿主角色来源检查并 spawn",
            "state that a version mismatch does not block spawn",
        ),
        (
            r"Notice: agents bundle 版本不匹配",
            "surface the version mismatch notice",
        ),
        (
            r"大于 {} 时额外提示先更新 oh-story-claudecode".format(current),
            "tell future deployments to update the package first",
        ),
        (
            fallback_pattern,
            "describe operational fallbacks without treating version mismatch as a failure",
        ),
    )
    missing = [label for pattern, label in required if re.search(pattern, text) is None]
    if not missing:
        return []
    return [
        Finding(
            "spawn-agents-version-preflight",
            "spawn-capable Skill must use the shared agents_version preflight: {}".format(
                "; ".join(missing)
            ),
            path,
        )
    ]


# 작가에게 보이는 텍스트는 평이하게 쓴다. 이 스킬들의 대체 처리와 버전 알림 원문은 보고 마지막 ‘技术备注：’ 줄에만 넣는다.
# ‘보고 `Fallback: …`’, ‘함께 보고 `Notice: …`’처럼 모델이 원문을 작가에게 그대로 읽도록 쓰지 않는다(v0.8.2).
AUTHOR_NOTE_PREFLIGHT_SKILLS = (
    "skills/story-long-write/SKILL.md",
    "skills/story-short-write/SKILL.md",
    "skills/story-deslop/SKILL.md",
    "skills/story-review/SKILL.md",
    "skills/story-import/SKILL.md",
    "skills/story/SKILL.md",
)
BARE_ENGINE_REPORT_RE = re.compile(r"报告\s*`(?:Fallback|Notice):")
ENGINE_LINE_RE = re.compile(r"(?:Fallback|Notice):")
SENTENCE_SPLIT_RE = re.compile(r"[。；！？\n]")


def author_note_preflight_findings(text: str, path: Path) -> List[Finding]:
    """Fallback / Notice 원문은 기술 참고 줄로 보내고 작가에게는 평이한 한 문장을 보여 준다.

    같은 문장 안에서 기술 참고로 보낸다고 명시해야 한다. 동사만 바꿔 고정 문형을 피하는 경우도 차단한다."""

    problems = []
    if BARE_ENGINE_REPORT_RE.search(text):
        problems.append("Fallback/Notice must not be reported to the author verbatim")
    stray = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_RE.split(text)
        if ENGINE_LINE_RE.search(sentence) and "技术备注" not in sentence
    ]
    if stray:
        problems.append(
            "every Fallback:/Notice: mention must say in the same sentence that it goes into the 技术备注 line: "
            + " | ".join(item[:60] for item in stray)
        )
    if "技术备注" not in text:
        problems.append("route Fallback/Notice into the trailing 技术备注 line")
    if not problems:
        return []
    return [Finding("author-note-preflight", "; ".join(problems), path)]


def rubric_dimension_names(repo_root: Path) -> Tuple[List[str], List[str]]:
    """quality-rubric.md의 ‘核心维度’ 표와 SKILL.md 내장 대체 기준에서 평가 항목명을 추출한다."""

    table: List[str] = []
    rubric_text = read_text(repo_root / "skills/story-review/references/quality-rubric.md") or ""
    in_table = False
    for line in rubric_text.splitlines():
        if line.startswith("| 维度 |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cell = line.split("|")[1].strip()
        if cell and not set(cell) <= {"-", ":"}:
            table.append(cell)

    embedded: List[str] = []
    skill_text = read_text(repo_root / "skills/story-review/SKILL.md") or ""
    if "通用网文内容 rubric：" in skill_text:
        block = skill_text.split("通用网文内容 rubric：", 1)[1]
        for line in block.splitlines():
            if not line.startswith("- "):
                if embedded:
                    break
                continue
            embedded.append(line[2:].split("：", 1)[0].strip())
    return table, embedded


def rubric_parity_findings(repo_root: Path) -> List[Finding]:
    """내장 대체 평가 기준과 quality-rubric.md는 같은 평가 항목을 사용해야 한다.

    두 자료는 같은 기준의 사본이다. 파일을 읽을 수 있으면 파일을, 없으면 내장 기준을 쓴다. 과거에는
    파일에만 ‘任务卡点’, 내장 기준에만 ‘标点节奏’와 ‘具体字数表达校验’이 있어 경로 접근 가능성에 따라
    평가 기준이 달라졌다. 수동 정렬은 한 번만 해결하지만 이 검증은 이후에도 일치를 보장한다.
    """

    table, embedded = rubric_dimension_names(repo_root)
    path = repo_root / "skills/story-review/SKILL.md"
    if not table or not embedded:
        return [
            Finding(
                "rubric-parity-unreadable",
                "cannot read both generic rubrics to compare dimensions",
                path,
            )
        ]
    findings = []
    for missing, where in (
        (sorted(set(table) - set(embedded)), "内置 fallback rubric"),
        (sorted(set(embedded) - set(table)), "quality-rubric.md"),
    ):
        if missing:
            findings.append(
                Finding(
                    "rubric-dimension-drift",
                    "generic rubric dimensions drifted: {} missing from {}".format(
                        "、".join(missing), where
                    ),
                    path,
                )
            )
    return findings


def parse_frontmatter_version(path: Path) -> Optional[str]:
    text = read_text(path)
    if text is None:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.fullmatch(r"version:\s*([^\s]+)\s*", line)
        if match:
            return match.group(1)
    return None


def extract_current_version_fields(text: str) -> dict[str, str]:
    """`## 当前版本` 절에서만 버전 목록 항목을 파싱한다."""
    lines = text.splitlines()
    start: Optional[int] = None
    for index, line in enumerate(lines):
        if re.fullmatch(r"##\s+当前版本\s*", line):
            start = index + 1
            break
    if start is None:
        return {}

    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^#{1,2}\s+", lines[index]):
            end = index
            break

    fields: dict[str, str] = {}
    for line in lines[start:end]:
        match = re.fullmatch(
            r"\s*-\s+`(setup_skill_version|agents_version):\s*([^`]+)`\s*",
            line,
        )
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def upgrading_version_findings(
    text: str, manifest: ContractManifest, path: Path
) -> List[Finding]:
    fields = extract_current_version_fields(text)
    expected = {
        "setup_skill_version": manifest.setup_skill_version,
        "agents_version": str(manifest.agents_version),
    }
    findings: List[Finding] = []
    for key, value in expected.items():
        actual = fields.get(key)
        if actual != value:
            findings.append(
                Finding(
                    "upgrading-current-version",
                    "UPGRADING current-version bullet {} must be {!r}, got {!r}".format(
                        key, value, actual
                    ),
                    path,
                )
            )
    # 업그레이드 절차에서 사용자에게 확인하도록 하는 버전은 실행 지침이며 버전 갱신 시 빠지기 쉽다(현재 버전 목록에도 없고
    # 배포 검사 TS10 앵커에도 포함되지 않는다). `agents_version: N` 형식의 모든 줄은 현재 값이어야 한다.
    for raw in text.splitlines():
        match = re.search(r"`agents_version:\s*(\d+)`", raw)
        if match and match.group(1) != str(manifest.agents_version):
            findings.append(
                Finding(
                    "upgrading-step-version",
                    "UPGRADING step line pins agents_version {!r}, must be {!r}: {}".format(
                        match.group(1), str(manifest.agents_version), raw.strip()
                    ),
                    path,
                )
            )
    return findings


def extract_sentinel_fields(text: str) -> Optional[dict[str, str]]:
    """해당 Step 절에서 생성된 `.story-deployed` YAML 예제를 파싱한다.

    주변 설명에 있는 버전 문자열은 의도적으로 무시한다. 배포 계약은 ‘创建部署标记’ 안의
    ‘写入以下字段’ 지침 다음에 오는 코드 블록이다.
    """
    lines = text.splitlines()
    section_start: Optional[int] = None
    heading_level = 0
    for index, line in enumerate(lines):
        match = re.match(r"^(#{2,6})\s+Step\s+[A-Za-z0-9]+[：:]\s*创建部署标记\s*$", line)
        if match:
            section_start = index + 1
            heading_level = len(match.group(1))
            break
    if section_start is None:
        return None

    section_end = len(lines)
    for index in range(section_start, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[index])
        if match and len(match.group(1)) <= heading_level:
            section_end = index
            break

    marker_index: Optional[int] = None
    for index in range(section_start, section_end):
        if "写入以下字段" in lines[index]:
            marker_index = index + 1
            break
    if marker_index is None:
        return None

    fence_start: Optional[int] = None
    for index in range(marker_index, section_end):
        if re.match(r"^\s*```(?:ya?ml)?\s*$", lines[index], re.IGNORECASE):
            fence_start = index + 1
            break
    if fence_start is None:
        return None

    fence_end: Optional[int] = None
    for index in range(fence_start, section_end):
        if re.match(r"^\s*```\s*$", lines[index]):
            fence_end = index
            break
    if fence_end is None:
        return None

    fields: dict[str, str] = {}
    for line in lines[fence_start:fence_end]:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$", line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def sentinel_contract_findings(
    text: str, manifest: ContractManifest, path: Path
) -> List[Finding]:
    fields = extract_sentinel_fields(text)
    if fields is None:
        return [
            Finding(
                "setup-sentinel-block",
                "cannot find the structured generated-sentinel fenced block",
                path,
            )
        ]

    required = {
        "deployed_at",
        "agents_version",
        "setup_skill_version",
        "target_cli",
        "resolver_strategy",
        "references_dir",
    }
    findings: List[Finding] = []
    missing = sorted(required - set(fields))
    if missing:
        findings.append(
            Finding(
                "setup-sentinel-fields",
                "generated sentinel is missing fields: {}".format(", ".join(missing)),
                path,
            )
        )

    expected = {
        "agents_version": str(manifest.agents_version),
        "setup_skill_version": manifest.setup_skill_version,
    }
    for key, value in expected.items():
        actual = fields.get(key)
        if actual != value:
            findings.append(
                Finding(
                    "setup-sentinel-field",
                    "generated sentinel {} must be {!r}, got {!r}".format(key, value, actual),
                    path,
                )
            )
    return findings


def _clean_markdown_label(label: str) -> str:
    return label.strip().strip("`*_ ")


def _normalize_rule_field(label: str) -> str:
    label = _clean_markdown_label(label)
    if label.startswith("本章"):
        label = label[2:]
    label = re.sub(r"[（(].*$", "", label).strip()
    return label


def extract_outline_rule_fields(text: str) -> set[str]:
    """Rules 2번 항목(细纲必填项)에서 구조화 필드 레이블을 반환한다."""
    lines = text.splitlines()
    start: Optional[int] = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*2\.\s+\*\*细纲必填项\*\*", line):
            start = index + 1
            break
    if start is None:
        return set()

    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^\s*[3-9][0-9]*\.\s+\*\*", lines[index]):
            end = index
            break

    fields: set[str] = set()
    for line in lines[start:end]:
        match = re.match(r"^\s*-\s+(.+?)[：:]", line)
        if match:
            fields.add(_normalize_rule_field(match.group(1)))
    return fields


def outline_rule_contract_findings(
    text: str, manifest: ContractManifest, path: Path
) -> List[Finding]:
    fields = extract_outline_rule_fields(text)
    required = {rule for rule, _ in manifest.required_outline_sections}
    missing = sorted(required - fields)
    if not missing:
        return []
    return [
        Finding(
            "outline-rule-section",
            "outline rule is missing structured blueprint fields: {}".format(", ".join(missing)),
            path,
        )
    ]


def extract_demo_outline_fields(text: str) -> set[str]:
    """제목 또는 `- field: value` 항목으로 선언된 레이블을 반환한다."""
    fields: set[str] = set()
    for line in text.splitlines():
        heading = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if heading:
            fields.add(_clean_markdown_label(heading.group(1)))
            continue
        bullet = re.match(r"^\s*-\s+(.+?)[：:]", line)
        if bullet:
            fields.add(_clean_markdown_label(bullet.group(1)))
    return fields


SCHEMA_VERSION_PIN_RE = re.compile(r"schema_version:\s*([0-9]+)")


def progress_schema_pin_findings(repo_root: Path, expected: int) -> List[Finding]:
    """모든 리터럴 `schema_version: N` 앵커는 현재 이어 실행하기 계약 버전이어야 한다.

    이 계약은 analyze의 쓰기/복구 절, import의 현재 분석 계약, UPGRADING 현재 계약 절, 데모 기준
    진행 파일에도 들어 있다. pipeline-ops.md만 검사하면 갱신 후 다른 파일이 이전 버전으로 남아
    스킬 묶음이 자기모순에 빠지고 자신이 쓴 `_progress.md`도 거부하지만 CI는 통과할 수 있다.
    `agents_version`과 같은 방식(upgrading_version_findings 참고)으로 `schema_version: N` 형식의
    모든 줄이 현재 값인지 확인한다. 루트 CHANGELOG.md는 과거 기록이므로 의도적으로 제외한다.
    버전 설명 표의 `| 2 | 当前契约… |`는 앵커 형식이 아니므로 이 규칙의 영향을 받지 않는다.
    """
    findings: List[Finding] = []
    paths: List[Path] = []
    for root in (repo_root / "skills", repo_root / "demo"):
        paths.extend(path for path in iter_files(root) if path.suffix.lower() == ".md")
    # iter_files는 UPGRADING.md를 이름으로 제외한다(과거 절은 현재 값으로 제한하면 안 됨). 다만 `## v21 当前契约`
    # 절의 이어 실행하기 계약 설명은 agents_version과 마찬가지로 버전 갱신 시 함께 바꿔야 한다.
    paths.append(repo_root / "skills/story-setup/UPGRADING.md")
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            for match in SCHEMA_VERSION_PIN_RE.finditer(line_text):
                if int(match.group(1)) == expected:
                    continue
                findings.append(
                    Finding(
                        "progress-schema-version",
                        "every pipeline schema_version must equal {} (found {})".format(
                            expected, match.group(1)
                        ),
                        path,
                        line_number,
                        line_text,
                    )
                )
    return findings


def validate_repository(repo_root: Path, manifest: ContractManifest) -> List[Finding]:
    findings: List[Finding] = []

    scan_roots = [repo_root / "skills", repo_root / "demo"]
    scan_roots.extend(
        repo_root / relative_root
        for rule in LEGACY_RULES
        for relative_root in rule.relative_roots
    )
    findings.extend(undecodable_source_findings(scan_roots))

    for rule in LEGACY_RULES:
        findings.extend(check_absent_rule(repo_root, rule))

    pipeline = repo_root / "skills/story-long-analyze/references/pipeline-ops.md"
    pipeline_text = read_text(pipeline) or ""
    if not SCHEMA_VERSION_PIN_RE.search(pipeline_text):
        findings.append(
            Finding(
                "progress-schema-version",
                "every pipeline schema_version must equal {} (found {})".format(
                    manifest.progress_schema_version, "none"
                ),
                pipeline,
            )
        )
    findings.extend(
        progress_schema_pin_findings(repo_root, manifest.progress_schema_version)
    )

    setup_skill = repo_root / "skills/story-setup/SKILL.md"
    actual_setup_version = parse_frontmatter_version(setup_skill)
    if actual_setup_version != manifest.setup_skill_version:
        findings.append(
            Finding(
                "setup-frontmatter-version",
                "story-setup frontmatter version must be {}, got {!r}".format(
                    manifest.setup_skill_version, actual_setup_version
                ),
                setup_skill,
            )
        )
    setup_text = read_text(setup_skill) or ""
    findings.extend(sentinel_contract_findings(setup_text, manifest, setup_skill))

    for relative in SPAWN_CAPABLE_SKILLS:
        spawn_skill = repo_root / relative
        findings.extend(
            spawn_preflight_findings(
                read_text(spawn_skill) or "", manifest, spawn_skill
            )
        )

    for relative in AUTHOR_NOTE_PREFLIGHT_SKILLS:
        note_skill = repo_root / relative
        findings.extend(author_note_preflight_findings(read_text(note_skill) or "", note_skill))

    upgrading = repo_root / "skills/story-setup/UPGRADING.md"
    upgrading_text = read_text(upgrading) or ""
    findings.extend(upgrading_version_findings(upgrading_text, manifest, upgrading))

    topic_file = repo_root / "skills/story-long-scan/references/topic-decision.md"
    topic_text = read_text(topic_file) or ""
    topic_match = re.search(r"Phase\s+([0-9]+)[^\n]*(?:产出\s*`소재선정\.md`|`소재선정\.md`를 만든다)", topic_text)
    if not topic_match or int(topic_match.group(1)) != manifest.topic_decision_phase:
        findings.append(
            Finding(
                "topic-decision-phase",
                "topic-decision output phase must be {}, got {}".format(
                    manifest.topic_decision_phase,
                    topic_match.group(1) if topic_match else "none",
                ),
                topic_file,
            )
        )
    scan_skill = repo_root / "skills/story-long-scan/SKILL.md"
    findings.extend(
        require_pattern(
            scan_skill,
            r"^#{{2,6}}\s+Phase\s+{}[：:]\s*选题决策\s*$".format(manifest.topic_decision_phase),
            "topic-decision-phase-heading",
            "story-long-scan must expose topic decision as Phase {}".format(manifest.topic_decision_phase),
        )
    )
    for path in iter_files(repo_root / "skills"):
        if path.suffix.lower() != ".md":
            continue
        text = read_text(path) or ""
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            if "选题决策" not in line_text and "소재선정" not in line_text:
                continue
            # 이 패키지에서는 스킬명을 백틱으로 감싼다(`story-long-scan` Phase 5). 일반 토큰 일치는
            # 백틱을 넘지 못해 참조 절반을 놓치므로 두 표기를 모두 검사해야 한다.
            for match in re.finditer(
                r"`?story-long-scan`?[\s`]*Phase\s+([0-9]+)", line_text
            ):
                value = int(match.group(1))
                if value == manifest.topic_decision_phase:
                    continue
                findings.append(
                    Finding(
                        "stale-topic-decision-phase-reference",
                        "story-long-scan topic-decision references must use Phase {}".format(
                            manifest.topic_decision_phase
                        ),
                        path,
                        line_number,
                        line_text,
                    )
                )

    findings.extend(rubric_parity_findings(repo_root))

    findings.extend(author_facing_findings(repo_root / "skills/story-long-analyze/references/author-facing.md"))
    findings.extend(analyze_dispatch_default_findings(repo_root / "skills/story-long-analyze/references/author-facing.md"))
    findings.extend(analyze_moment_routing_findings(repo_root))
    long_analyze = repo_root / "skills/story-long-analyze/SKILL.md"
    findings.extend(require_pattern(long_analyze, r"references/author-facing\.md", "author-facing-routed",
                                    "story-long-analyze must route every author-visible message through author-facing.md"))
    findings.extend(require_pattern(long_analyze, r"invalid_topic_decision_contract", "invalid-topic-contract", "invalid topic-decision artifacts must fail explicitly"))
    # 목차 블록 제거는 build_chapter_index.py가 수행하며 test-long-analyze-runtime-refactor.py에서 목차가 있는 원문으로 검증한다.
    # 장 번호 연속성 검사에는 아직 런타임 회귀 검사가 없으므로 Stage 0의 텍스트 앵커를 남긴다.
    findings.extend(require_pattern(long_analyze, r"落表前校验章号连续", "stage0-chapter-table-validation", "Stage 0 must validate chapter numbers before writing the boundary table"))
    # 벤치마크 회수 흐름은 story-explorer의 필요 시 참조 자료에 있다(query_type=benchmark_style_load일 때만 읽음).
    explorer = repo_root / "skills/story-setup/references/agent-references/benchmark-style-load.md"
    findings.extend(require_pattern(explorer, r"missing_primary_contract", "explorer-primary-failure", "story-explorer must fail closed on missing current benchmark artifacts"))
    findings.extend(require_pattern(explorer, r"repair_action", "explorer-repair-action", "story-explorer must return an explicit repair action"))

    # 주요 산출물 읽기와 누락 시 중단은 집필 전 회수 단계에서 정의한다(v0.8.2부터 SKILL.md에는 벤치마크 경로 조회 한 줄만 남김).
    long_write = repo_root / "skills/story-long-write/references/benchmark-recall.md"
    for artifact in manifest.primary_benchmark_artifacts:
        findings.extend(
            require_pattern(
                long_write,
                re.escape(artifact),
                "long-write-primary-artifact",
                "long writing must require {}".format(artifact),
            )
        )

    for relative in (
        "skills/story-import/SKILL.md",
        "skills/story-import/references/structure-mapping-long.md",
        "skills/story-import/references/structure-mapping-short.md",
    ):
        import_contract = repo_root / relative
        findings.extend(
            require_pattern(
                import_contract,
                r"\{导入书名\}",
                "story-import-import-title-boundary",
                "story-import must name the imported work independently",
            )
        )
        findings.extend(
            require_pattern(
                import_contract,
                r"\{对标书名\}",
                "story-import-benchmark-title-boundary",
                "story-import must name external benchmarks independently",
            )
        )

    # 장편의 벤치마크 탐색은 Phase 1-3과 함께 SKILL.md에서 workflow-setup.md로 이동했다(#269, 무조건 로드 축소).
    # 검증도 내용의 위치를 따른다. 단편 벤치마크 탐색은 별도의 benchmark-recall.md에 있다.
    for relative in (
        "skills/story-long-write/references/workflow-setup.md",
        "skills/story-short-write/references/benchmark-recall.md",
        "skills/story-long-write/references/cross-book-recall.md",
        "skills/story-short-write/references/cross-book-recall.md",
    ):
        benchmark_discovery = repo_root / relative
        findings.extend(
            require_pattern(
                benchmark_discovery,
                r"(?:排除[^\n]*当前[^\n]*(?:拆文库|作品|正文)|현재 작품을 식별하고[^\n]*현재 본문인[^\n]*제외|현재 작품을 식별한다[^\n]*현재 본문을 가리키는[^\n]*제외한다|같은 이름이거나 출처가 현재 (?:`본문\.md`|본문)[^\n]*가리키는[^\n]*`비교작품/\{当前书\}/`는 제외한다)",
                "benchmark-discovery-excludes-current-work",
                "benchmark discovery must exclude the current imported work",
            )
        )

    explorer_template = repo_root / "skills/story-setup/references/agent-references/benchmark-style-load.md"
    findings.extend(
        require_pattern(
            explorer_template,
            r"self_benchmark_ignored",
            "explorer-self-benchmark-gap",
            "story-explorer must report and ignore self-benchmark candidates",
        )
    )
    # 책은 있지만 문체가 없으면 반드시 profile_missing이어야 하며 benchmark_book_missing에 흡수되어서는 안 된다.
    # 전자는 호출자가 custom_style로 대체 집필할 수 있고 후자는 반드시 중단한다. 둘의 혼동은 표현 문제가 아닌 기능 회귀다.
    findings.extend(
        require_pattern(
            explorer_template,
            r"비교작품/\{书名\}/\*\*/\*",
            "explorer-book-dir-probe",
            "story-explorer must probe book-dir validity with any file under it, not 문체.md",
        )
    )
    findings.extend(
        require_pattern(
            explorer_template,
            r"(?:不得改填\s*`?benchmark_book_missing|`benchmark_book_missing`으로 바꾸지 않는다)",
            "explorer-profile-missing-distinct",
            "story-explorer must keep profile_missing distinct from benchmark_book_missing",
        )
    )
    findings.extend(
        require_pattern(
            repo_root / "skills/story-long-write/references/agent-calls.md",
            r"profile_missing[^\n]{0,60}custom_style[^\n]{0,40}(?:继续|계속)",
            "daily-profile-missing-custom-style",
            "the story-explorer recall gaps (agent-calls.md) must keep the profile_missing + custom_style continuation branch",
        )
    )

    # 3계층 영감 라이브러리 파이프라인: EM 카드 재사용, 레이블 없는 ID 참조, 선택 축이 진행을 막지 않음. 세 금지선마다 기계 검사 가능한 앵커가 있다.
    inspiration_library = repo_root / "skills/story-long-analyze/references/inspiration-library.md"
    for pattern, code, message in (
        (r"原子灵感|원자 영감", "inspiration-atom-layer", "inspiration library must define the atom layer"),
        (r"单小说灵感合并", "inspiration-novel-merge-layer", "inspiration library must define the single-novel merge layer"),
        (r"跨书灵感聚合", "inspiration-cross-book-layer", "inspiration library must define the cross-book aggregation layer"),
        (r"只是索引行，没有文件|색인 행만 있고 파일은 없다", "inspiration-atom-is-index-row", "inspiration atoms must stay index rows without card files"),
        (r"禁止在卡里堆路径链接|卡内无路径引用|카드 내 경로 참조 금지", "inspiration-no-path-in-card", "NM/CBA cards must reference sources by bare id, not paths"),
        (r"单书拆文不自动入库|개별 작품 분석 결과는 자동으로 등록하지 않는다", "inspiration-no-auto-ingest", "single-book analysis must not auto-ingest into the library"),
    ):
        findings.extend(require_pattern(inspiration_library, pattern, code, message))
    findings.extend(
        require_pattern(
            repo_root / "skills/story-long-analyze/SKILL.md",
            r"references/inspiration-library\.md",
            "inspiration-pipeline-routed",
            "story-long-analyze must route the optional inspiration pipeline",
        )
    )
    findings.extend(
        require_pattern(
            repo_root / "skills/story-long-write/references/cross-book-recall.md",
            r"layer=跨书灵感聚合[^\n]*status=active",
            "cross-book-active-cba-only",
            "inspiration recall must retrieve only active cross-book aggregation cards",
        )
    )
    findings.extend(
        require_pattern(
            repo_root / "skills/story-long-write/references/project-files.md",
            r"Top 3[–-]8[^\n]*CBA[^\n]*不传 IA/NM|CBA 상위 3[–-]8개[^\n]*IA/NM을 전달하지 않고",
            "long-write-cba-budget",
            "long writing must bound public inspiration retrieval to Top 3-8 CBA cards without IA/NM",
        )
    )
    # 새 작품 시작은 시점별 세 파일로 나뉜다(v0.8.2). 세 영감 회수 앵커는 각각 해당 시점 파일에 있다.
    references_dir = repo_root / "skills/story-long-write/references"
    for filename, pattern, code, message in (
        ("workflow-setup.md", r"适用阶段=设定", "inspiration-hook-setup", "book setup must offer optional inspiration recall"),
        ("workflow-volume.md", r"适用阶段=卷纲", "inspiration-hook-volume", "volume outlining must offer optional inspiration recall"),
        ("workflow-outline.md", r"适用阶段=细纲", "inspiration-hook-outline", "chapter outlining must offer optional inspiration recall"),
    ):
        findings.extend(require_pattern(references_dir / filename, pattern, code, message))
    findings.extend(
        require_pattern(
            repo_root / "skills/story-long-write/references/cross-book-recall.md",
            r"独立于[^\n]*多对标触发条件|다중 벤치마크 조건과 독립적이다",
            "inspiration-decoupled-from-multi-benchmark",
            "inspiration channel must not depend on the >=2 benchmark trigger",
        )
    )

    # 세 소비자 모두 지점별 글자 수를 명시적으로 폐지해야 이전 Σ 계약이 배포 경로를 통해 되돌아오지 않는다.
    for relative in OUTLINE_SEMANTIC_CAPACITY_CONSUMERS:
        findings.extend(
            require_pattern(
                repo_root / relative,
                r"(?:不(?:填写|含)逐点字数|항목별 글자 수를 쓰지 않으며)",
                "outline-semantic-capacity-parity",
                "outline beats must remain semantic and must not carry per-beat word quotas",
            )
        )

    outline_rule = repo_root / "skills/story-setup/references/templates/rules/story-outline.md"
    outline_rule_text = read_text(outline_rule) or ""
    findings.extend(
        outline_rule_contract_findings(outline_rule_text, manifest, outline_rule)
    )

    demo_root = repo_root / "demo/拆文库/盘龙"
    for artifact in manifest.primary_benchmark_artifacts:
        artifact_path = demo_root / artifact.replace("플롯/", "剧情/").replace("감정모듈.md", "情绪模块.md").replace("리듬.md", "节奏.md")
        try:
            has_content = artifact_path.is_file() and artifact_path.stat().st_size > 0
        except OSError:
            has_content = False
        if not has_content:
            findings.append(
                Finding("demo-primary-artifact", "demo deconstruction is missing non-empty {}".format(artifact), artifact_path)
            )

    outline_dir = repo_root / "demo/长篇/让你管账号，你高燃混剪炸全网/大纲"
    outlines = sorted(outline_dir.glob("细纲_第*.md"))
    if not outlines:
        # 디렉터리 이름을 바꾸거나 비우면 아래 장별 검사가 빈 상태로 통과하므로 상세 개요가 최소 하나 있어야 한다.
        findings.append(Finding("demo-outline-section", "no demo chapter outlines found", outline_dir))
    for outline in outlines:
        text = read_text(outline) or ""
        declared_fields = extract_demo_outline_fields(text)
        missing = [
            demo
            for _, demo in manifest.required_outline_sections
            if demo not in declared_fields
        ]
        if missing:
            findings.append(
                Finding(
                    "demo-outline-section",
                    "demo outline is missing current blueprint sections: {}".format(", ".join(missing)),
                    outline,
                )
            )

    for path in iter_files(repo_root / "skills"):
        if path.suffix.lower() != ".md":
            continue
        text = read_text(path)
        if text is not None:
            findings.extend(
                semantic_primary_fallback_findings(
                    text,
                    path,
                    manifest.primary_benchmark_artifacts,
                )
            )

    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().with_name("current-contract.json"),
        help="current contract manifest",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest, manifest_findings = load_manifest(args.manifest.resolve())

    print("Current Skill Contract Check")
    print("============================")
    if manifest_findings:
        for finding in manifest_findings:
            print("  [FAIL] {}: {}".format(finding.code, finding.detail(repo_root)))
        print("\nResult: {} failure(s)".format(len(manifest_findings)))
        return 1

    assert manifest is not None
    print("  [PASS] manifest schema and declared release values")
    findings = validate_repository(repo_root, manifest)
    if findings:
        for finding in findings:
            print("  [FAIL] {}: {}".format(finding.code, finding.detail(repo_root)))
        print("\nResult: {} failure(s)".format(len(findings)))
        return 1

    print("  [PASS] legacy/path guards")
    print("  [PASS] version, phase, progress, and artifact contracts")
    print("  [PASS] primary-artifact fallback semantics")
    print("  [PASS] demo primary artifacts and outlines")
    print("\nResult: all current-contract checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
