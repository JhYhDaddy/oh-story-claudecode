#!/usr/bin/env python3
"""근거 있는 작가 선호와 결정적 Markdown 뷰를 관리한다.
언어 모델이 간결한 의미 트랜잭션을 공급하면 메모리에서 검증·적용하고 모든 파생 뷰를 렌더링한 뒤 JSON state를 마지막 커밋 지점으로 쓴다.
작가 기억은 작업 공간의 프로젝트 store(global/genre/workflow, `AP` ID)와 작품 디렉터리의 작품 store(`BP` ID)로 나뉘어 작품과 함께 이동한다.
둘 다 이야기 연속성 추적과는 별개다. 작품 루트가 작업 공간이면 작품 store를 `书级/`로 옮겨 같은 파일을 공유하지 않게 한다.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INPUT_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
STATE_MAX_BYTES = 2 * 1024 * 1024
PROFILE_MAX_BYTES = 12288
PENDING_MAX_BYTES = 12288
JOURNAL_MAX_BYTES = 24576
QUERY_MAX_BYTES = 2048
ASSERTION_MAX_BYTES = 120  # 새 항목의 단정은 한 문장으로 제한하며 설명은 query 내용에 넣지 않는 reason에 쓴다.
LEGACY_ASSERTION_MAX_BYTES = 768  # 기존 항목의 읽기 상한. 기존 항목 강화에는 새 상한을 적용하지 않는다.

# query 출력 lines는 항목마다 ‘- 단정(번호)’ 한 행으로 실행 agent에 주입하는
# 내용이다. QUERY_MAX_BYTES는 프롬프트 주의력 예산이므로 늘리면 안 된다. 실행자가
# 실제 읽는 행만 재며 주 세션·스크립트용 번호·kind·scope의 JSON 외곽 구조는 제외한다.
# 작가는 불러온 줄 알지만 실제로는 조용히 밀려나는 일을 세 단계로 막는다. ① 새 단정은
# ASSERTION_MAX_BYTES로 원천 제한한다. 기존 강화에는 적용하지 않아 긴 단정을 다시 확인하지 못하고
# 중복 항목만 파생시키는 일을 피한다. ② 쓰기 측은 아래 작업 조합을
# 같은 패키지 버전의 references/author-memory-maintenance.md 매핑과 맞춰 최악의 조회를 추정한다.
# 전역 항목 + scope 차원별 가장 무거운 단일 구간이다. 조회마다 book/genre/workflow 하나씩만 있어
# 다른 작품 항목이 함께 나오지 않는다. 구간은 same_scope_value처럼 casefold로 합치며
# 무게는 실제 내용과 같은 렌더링 행 바이트로 잰다. 다 담지 못하면 warnings에
# 빠질 항목을 명시하고 작가 기억 정리를 안내한다. 쓰기 자체는 주입 예산 때문에 실패하지 않는다.
# ③ 조회는 중요도→현재 작품 예외→최근 갱신 순으로 채워 낮은 중요도부터 빠진다.
# 누락 ID 전체를 같은 우선순위로 omitted_ids에, 첫 문장을 omitted_summaries에 넣어
# 주 세션이 작가에게 어떤 항목이 빠졌는지 원문으로 알릴 수 있게 한다.
QUERY_COMBOS: dict[str, tuple[str, ...]] = {
    "正文初稿/续写": ("prose_style", "story_design"),
    "去AI味/改写": ("prose_style",),
    "설정/개요": ("story_design", "workflow", "interaction"),
    "审稿": ("delivery", "interaction", "prose_style"),
}

KINDS = ("prose_style", "story_design", "workflow", "delivery", "interaction")
KIND_TITLES = {
    "prose_style": "文风与表达",
    "story_design": "故事设计",
    "workflow": "创作流程",
    "delivery": "交付格式",
    "interaction": "协作方式",
}
SCOPE_LEVELS = ("global", "genre", "book", "workflow")
STATUSES = ("active", "pending", "conflict", "rejected", "superseded")
CONFIDENCE_LEVELS = ("low", "medium", "high")
IMPORTANCE_LEVELS = ("low", "medium", "high")
# 작가 기억은 명시적으로 표현한 선호만 기록한다. agent가 능동 추론해 쓰던 repeated_correction / inferred_pattern
# 경로는 제거했다(#436). 이들은 기억 품질을 높이는 대신 확인 대기 목록의 검토 부담만
# 쌓았다. 문서도 전체 메시지 훅을 설치하지 않는다고 명시하므로 암묵 수집의 완전성을 원래 보장할 수 없다.
# SOURCES에 두 값을 남기는 것은 기존 state의 검증과 decide/forget을 허용하기 위해서다.
# 새 쓰기는 모두 WRITE_SOURCES로 검증한다.
SOURCES = (
    "explicit_user",
    "accepted_suggestion",
    "repeated_correction",
    "inferred_pattern",
    "manual",
)
WRITE_SOURCES = ("explicit_user", "accepted_suggestion", "manual")
RANK = {"low": 0, "medium": 1, "high": 2}

# 2단계 store(#435): 프로젝트는 global/genre/workflow를 AP 접두사로 저장하며 위치는
# {작업공간}/.story/작가기억/이다. 작품은 해당 book 항목만 BP 접두사로 저장하고 위치는
# {작품}/.story/작가기억/로 보관·이동 시 작품을 따른다. ID 접두사가 라우팅 키다.
# decide/forget은 item_id 접두사, remember/replace는 scope.level을 보며 트랜잭션 하나는
# store 하나만 쓴다. 업그레이드 전 프로젝트 store의 book 항목은 조회·추정에서 제외하고
# migrate로 작품 디렉터리에 옮긴 뒤에야 포함한다. 이중 읽기는 영원히 이전하지 않게 만들므로 사용하지 않는다.
STORE_PREFIX = {"project": "AP", "book": "BP"}
ID_PREFIXES = tuple(STORE_PREFIX.values())
# 작품 루트가 작업 공간인 단일 작품 구조에서는 두 store 기본 위치가 같은 state 파일이므로
# 작품 store는 {작업공간}/.story/작가기억/书级/ 하위 디렉터리로 옮긴다.
SINGLE_ROOT_BOOK_DIR = "书级"


class AuthorMemoryError(ValueError):
    """예상 가능한 검증 또는 상태 오류."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorMemoryError(message)


def as_mapping(value: object, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def as_list(value: object, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label} must be a JSON array")
    return value


def as_int(value: object, label: str, *, minimum: int = 0) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    require(value >= minimum, f"{label} must be >= {minimum}")
    return value


def require_known_keys(mapping: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(mapping) - allowed
    require(not unknown, f"{label} contains unsupported fields: {', '.join(sorted(unknown))}")


def clean_text(value: object, label: str, *, max_bytes: int = 768) -> str:
    require(isinstance(value, str), f"{label} must be a string")
    cleaned = " ".join(value.replace("|", "｜").split())
    require(bool(cleaned), f"{label} must not be empty")
    require(len(cleaned.encode("utf-8")) <= max_bytes, f"{label} exceeds {max_bytes} bytes")
    return cleaned


def optional_text(value: object, label: str, *, max_bytes: int = 768) -> str | None:
    if value is None:
        return None
    return clean_text(value, label, max_bytes=max_bytes)


def choice(value: object, allowed: tuple[str, ...], label: str) -> str:
    require(isinstance(value, str) and value in allowed, f"{label} must be one of: {', '.join(allowed)}")
    return value


def is_item_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) >= 3
        and value[:2] in ID_PREFIXES
        and value[2:].isdecimal()
        and int(value[2:]) >= 1
    )


def id_number(item_id: str) -> int:
    return int(item_id[2:])


def id_store(item_id: str) -> str:
    return "book" if item_id.startswith(STORE_PREFIX["book"]) else "project"


def clean_id_list(value: object, label: str, *, maximum: int = 32) -> list[str]:
    raw = as_list(value, label)
    require(len(raw) <= maximum, f"{label} may contain at most {maximum} items")
    result: list[str] = []
    for index, item in enumerate(raw):
        item_id = clean_text(item, f"{label}[{index}]", max_bytes=32)
        require(is_item_id(item_id), f"{label}[{index}] is not an author-memory id")
        if item_id not in result:
            result.append(item_id)
    return result


def emit(document: object, *, error: bool = False) -> None:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True)
    stream = sys.stderr if error else sys.stdout
    stream.flush()
    stream.buffer.write((payload + "\n").encode("utf-8"))
    stream.buffer.flush()


def json_payload(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_json(path: Path) -> object:
    try:
        require(path.stat().st_size <= STATE_MAX_BYTES, f"{path} exceeds {STATE_MAX_BYTES} bytes")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorMemoryError(f"unable to read JSON {path}: {exc}") from exc


def atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_if_changed(path: Path, payload: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == payload:
            return
    except FileNotFoundError:
        pass
    atomic_write_text(path, payload)


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------


class Store:
    """state 파일 위치: 프로젝트(작업 공간) 또는 작품(작품 디렉터리)."""

    __slots__ = ("kind", "root", "book")

    def __init__(self, kind: str, root: Path, book: str | None) -> None:
        self.kind = kind
        self.root = root
        self.book = book

    @property
    def prefix(self) -> str:
        return STORE_PREFIX[self.kind]

    @property
    def state_path(self) -> Path:
        return self.root / "_author-memory-state.json"

    @property
    def label(self) -> str:
        return "项目级" if self.kind == "project" else f"书级（{self.book}）"


def project_store(workspace: Path) -> Store:
    return Store("project", workspace.resolve() / ".story" / "작가기억", None)


def peek_book_name(state_path: Path) -> str | None:
    """state 전체를 검증하지 않고 작품명만 얻는다. 작품 store를 만든 뒤에는 state의 작품명이 기준이므로 디렉터리 이름 변경의 영향을 받지 않는다."""
    if not state_path.exists():
        return None
    document = read_json(state_path)
    name = document.get("book") if isinstance(document, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def enclosing_workspace(workspace: Path) -> Path | None:
    """--workspace가 다중 작품 공간 안의 작품을 가리키면 실제 창작 작업 공간을 반환한다.
    세 단서 중 하나를 인정한다. ① 부모 이름이 장편/短篇이면 그 위를 반환(story-setup 규약). ② 상위에 .active-book 존재.
    ③ 상위에 book 없는 프로젝트 state 존재. 다만 현재 공간 자체에 프로젝트 store가 있으면 이것이 가장 가까우므로 ③은 적용하지 않는다.
    홈에 잘못 만든 store가 정상 단일 작품 공간을 방해하지 않게 한다. 읽지 못한 상위 state는 단서가 아니다."""
    resolved = workspace.resolve()
    if resolved.parent.name in {"장편", "단편"}:
        return resolved.parent.parent
    own = project_store(resolved).state_path
    owns_project_store = own.exists() and peek_book_name(own) is None
    for ancestor in resolved.parents:
        if (ancestor / ".active-book").exists():
            return ancestor
        if owns_project_store:
            continue
        state_path = project_store(ancestor).state_path
        try:
            document = read_json(state_path) if state_path.is_file() else None
        except AuthorMemoryError:
            document = None
        if isinstance(document, dict) and "book" not in document:
            return ancestor
    return None


def same_directory(first: Path, second: Path) -> bool:
    # samefile은 macOS APFS 기본처럼 대소문자를 구별하지 않는 파일시스템의 동일 디렉터리를 인식한다.
    if first.exists() and second.exists():
        return os.path.samefile(first, second)
    return first.resolve() == second.resolve()


def is_single_root(workspace: Path, book_root: Path | None) -> bool:
    """단일 작품 구조: 본문/, 개요/, 추적/이 작업 공간 루트에 있어 작품 루트가 작업 공간이다.
    다중 작품 공간의 작품을 실수로 --workspace로 넘겨도 같은 구조일 수 있다. 이때 단일 작품으로 처리하면 작품 state를 书级/로 옮기고
    원래 위치에 빈 프로젝트 state를 만들어 이후 정상 호출이 모두 실패하므로 오류를 내고 아무것도 쓰지 않는다."""
    if book_root is None or not same_directory(book_root, workspace):
        return False
    outer = enclosing_workspace(workspace)
    require(
        outer is None,
        f"{workspace} 是创作工作区 {outer} 里的一本书，不是单书工作区：--workspace 应传 {outer}，"
        f"这个目录放 --book-root",
    )
    return True


def book_memory_root(workspace: Path, book_root: Path) -> Path:
    root = book_root.resolve() / ".story" / "작가기억"
    # 단일 작품 구조에서 두 store 기본 위치가 같으면 작품 store를 하위 디렉터리로 옮긴다.
    # 두 state·파생 뷰·리비전 흐름은 여전히 독립적이다.
    return root / SINGLE_ROOT_BOOK_DIR if is_single_root(workspace, book_root) else root


def sole_legacy_book_name(project: Store) -> str | None:
    """프로젝트의 기존 book 항목이 한 작품만 가리키면 그 이름을 반환한다(단일 작품 업그레이드 기본값)."""
    if not project.state_path.exists():
        return None
    document = read_json(project.state_path)
    items = document.get("items") if isinstance(document, dict) else None
    names: dict[str, str] = {}
    for item in (items.values() if isinstance(items, dict) else ()):
        scope = item.get("scope") if isinstance(item, dict) else None
        if (
            isinstance(scope, dict) and scope.get("level") == "book"
            and isinstance(scope.get("value"), str) and scope["value"].strip()
            and item.get("status") in {"active", "pending", "conflict"}
        ):
            names.setdefault(scope["value"].casefold(), scope["value"])
    return next(iter(names.values())) if len(names) == 1 else None


def book_store(workspace: Path, book_root: Path, book: str | None) -> Store:
    require(book_root.exists() and book_root.is_dir(), f"book root does not exist: {book_root}")
    resolved = book_root.resolve()
    root = book_memory_root(workspace, book_root)
    name = optional_text(book, "book", max_bytes=180)
    stored = peek_book_name(root / "_author-memory-state.json")
    if name is None:
        name = stored
    elif stored is not None:
        require(
            name.casefold() == stored.casefold(),
            f"--book「{name}」与 {root} 里记录的书「{stored}」不一致",
        )
    if name is None and is_single_root(workspace, book_root):
        # 단일 작품 작업 공간의 디렉터리명은 작품명과 다를 때가 많다. 이전 작품 항목이 한 작품만 가리키면 그것을 기준으로 한다.
        # 그렇지 않으면 migrate가 디렉터리명으로 기존 항목을 못 찾아 0개를 조용히 이전한다.
        name = sole_legacy_book_name(project_store(workspace))
    if name is None:
        name = clean_text(resolved.name, "book root name", max_bytes=180)
    return Store("book", root, name)


def relocate_misplaced_book_state(workspace: Path, book_root: Path | None) -> None:
    """단일 작품 구조 자체 복구: 구형 버전이 state.book 있는 작품 state를 프로젝트 위치에 써서 프로젝트 읽기·쓰기가 모두 실패한 경우.
    --book-root {작업공간}으로 명령을 실행하면 작품 하위 디렉터리로 원자 이동하고 프로젝트 위치에 빈 state와 뷰를 만든다.
    기존 state 내용과 리비전은 바꾸지 않는다."""
    if not is_single_root(workspace, book_root):
        return
    project = project_store(workspace)
    misplaced = peek_book_name(project.state_path)
    if misplaced is None:
        return
    target = Store("book", book_memory_root(workspace, book_root), misplaced)
    require(
        not target.state_path.exists(),
        f"{project.state_path} 与 {target.state_path} 都是书级 state，无法自动归位；"
        f"保留修订较新的一份移到 {target.state_path}，另一份备份后移走再重跑",
    )
    state = validate_state(read_json(project.state_path), store=target)
    target.root.mkdir(parents=True, exist_ok=True)
    os.replace(project.state_path, target.state_path)
    write_snapshot(target, state)
    write_snapshot(project, empty_state())


def resolve_target_store(kind: str, workspace: Path, book_root: Path | None, book: str | None) -> Store:
    if kind == "project":
        return project_store(workspace)
    require(
        book_root is not None,
        "book 级条目须传 --book-root {书目录}——记忆随书存放在 {书}/.story/작가기억/，不再写进工作区的项目级 store",
    )
    return book_store(workspace, book_root, book)


def empty_state(book: str | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_revision": 0,
        "next_item_number": 1,
        "items": {},
        "journal": [],
        "applied_transactions": {},
    }
    if book is not None:
        state["book"] = book
    return state


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------


def normalize_scope(value: object, label: str) -> dict[str, str | None]:
    scope = as_mapping(value, label)
    require_known_keys(scope, {"level", "value"}, label)
    level = choice(scope.get("level"), SCOPE_LEVELS, f"{label}.level")
    raw_value = scope.get("value")
    if level == "global":
        require(raw_value is None, f"{label}.value must be null for global scope")
        normalized_value = None
    else:
        normalized_value = clean_text(raw_value, f"{label}.value", max_bytes=180)
    return {"level": level, "value": normalized_value}


def normalize_evidence(value: object, label: str) -> dict[str, str | None]:
    evidence = as_mapping(value, label)
    require_known_keys(evidence, {"quote", "source_ref"}, label)
    return {
        "quote": clean_text(evidence.get("quote"), f"{label}.quote", max_bytes=768),
        "source_ref": optional_text(evidence.get("source_ref"), f"{label}.source_ref", max_bytes=240),
    }


def normalize_item(value: object, label: str) -> dict[str, Any]:
    item = as_mapping(value, label)
    allowed = {
        "id", "kind", "scope", "assertion", "confidence", "importance", "status", "source",
        "reason", "conflicts_with", "confirmation_count", "evidence", "created_revision",
        "updated_revision", "superseded_by",
    }
    require_known_keys(item, allowed, label)
    item_id = clean_text(item.get("id"), f"{label}.id", max_bytes=32)
    require(is_item_id(item_id), f"{label}.id is invalid")
    evidence = [normalize_evidence(entry, f"{label}.evidence[{index}]") for index, entry in enumerate(as_list(item.get("evidence"), f"{label}.evidence"))]
    require(bool(evidence), f"{label}.evidence must not be empty")
    status = choice(item.get("status"), STATUSES, f"{label}.status")
    conflicts = clean_id_list(item.get("conflicts_with"), f"{label}.conflicts_with")
    superseded_by = optional_text(item.get("superseded_by"), f"{label}.superseded_by", max_bytes=32)
    if superseded_by is not None:
        require(is_item_id(superseded_by), f"{label}.superseded_by is invalid")
    return {
        "id": item_id,
        "kind": choice(item.get("kind"), KINDS, f"{label}.kind"),
        "scope": normalize_scope(item.get("scope"), f"{label}.scope"),
        "assertion": clean_text(item.get("assertion"), f"{label}.assertion", max_bytes=LEGACY_ASSERTION_MAX_BYTES),
        "confidence": choice(item.get("confidence"), CONFIDENCE_LEVELS, f"{label}.confidence"),
        "importance": choice(item.get("importance"), IMPORTANCE_LEVELS, f"{label}.importance"),
        "status": status,
        "source": choice(item.get("source"), SOURCES, f"{label}.source"),
        "reason": clean_text(item.get("reason"), f"{label}.reason", max_bytes=480),
        "conflicts_with": conflicts,
        "confirmation_count": as_int(item.get("confirmation_count"), f"{label}.confirmation_count", minimum=1),
        "evidence": evidence,
        "created_revision": as_int(item.get("created_revision"), f"{label}.created_revision", minimum=1),
        "updated_revision": as_int(item.get("updated_revision"), f"{label}.updated_revision", minimum=1),
        "superseded_by": superseded_by,
    }


def scope_fits_store(scope: dict[str, str | None], book: str | None) -> bool:
    if book is None:
        return True  # 프로젝트의 기존 book 항목은 구형 저장소 검증과 migrate 이동을 위해 여전히 유효하다.
    return scope["level"] == "book" and (scope["value"] or "").casefold() == book.casefold()


def validate_state(value: object, *, store: Store) -> dict[str, Any]:
    state = as_mapping(value, "state")
    allowed = {"schema_version", "state_revision", "next_item_number", "items", "journal", "applied_transactions", "book"}
    require_known_keys(state, allowed, "state")
    require(state.get("schema_version") == STATE_SCHEMA_VERSION, f"state.schema_version must be {STATE_SCHEMA_VERSION}")
    if store.kind == "book":
        book = clean_text(state.get("book"), "state.book", max_bytes=180)
        require(store.book is not None and book.casefold() == store.book.casefold(), f"state.book「{book}」与目标书「{store.book}」不一致")
    else:
        require(
            "book" not in state,
            "project-level state must not carry state.book：这份其实是书级 state。--workspace 指到了"
            "장편/、단편/ 下的书目录时，改传创作工作区根、书目录放 --book-root；只有书根就是工作区"
            "（单书布局）时，带 --book-root {工作区} 重跑任一命令即自动移进 .story/작가기억/书级/",
        )
        book = None
    revision = as_int(state.get("state_revision"), "state.state_revision")
    next_number = as_int(state.get("next_item_number"), "state.next_item_number", minimum=1)
    raw_items = as_mapping(state.get("items"), "state.items")
    items: dict[str, Any] = {}
    max_number = 0
    for raw_id, raw_item in raw_items.items():
        normalized = normalize_item(raw_item, f"state.items.{raw_id}")
        require(raw_id == normalized["id"], f"state.items key {raw_id} does not match item id")
        require(raw_id.startswith(store.prefix), f"state.items.{raw_id} does not belong to the {store.label} store（前缀应为 {store.prefix}）")
        require(scope_fits_store(normalized["scope"], book), f"state.items.{raw_id} scope does not belong to book「{book}」")
        max_number = max(max_number, id_number(raw_id))
        require(normalized["created_revision"] <= normalized["updated_revision"] <= revision, f"state.items.{raw_id} revision is ahead of state")
        items[raw_id] = normalized
    require(next_number > max_number, "state.next_item_number must be greater than every allocated item id")
    for item_id, item in items.items():
        for conflict_id in item["conflicts_with"]:
            require(conflict_id in items and conflict_id != item_id, f"state.items.{item_id} has an invalid conflict id")
        if item["superseded_by"] is not None:
            require(item["superseded_by"] in items and item["superseded_by"] != item_id, f"state.items.{item_id} has an invalid superseded_by id")
        if item["status"] == "active":
            require(not item["conflicts_with"], f"active item {item_id} cannot retain conflicts")
        if item["status"] == "pending":
            require(not item["conflicts_with"], f"pending item {item_id} cannot retain conflicts")
        if item["status"] == "conflict":
            require(bool(item["conflicts_with"]), f"conflict item {item_id} must reference an active item")
            require(all(items[conflict_id]["status"] == "active" for conflict_id in item["conflicts_with"]), f"conflict item {item_id} must reference only active items")
        if item["status"] != "superseded":
            require(item["superseded_by"] is None, f"only superseded item {item_id} may set superseded_by")
    journal = as_list(state.get("journal"), "state.journal")
    require(len(journal) == revision, "state.journal length must equal state.state_revision")
    journal_revisions: dict[str, int] = {}
    for index, entry in enumerate(journal):
        mapping = as_mapping(entry, f"state.journal[{index}]")
        require_known_keys(mapping, {"revision", "transaction_id", "committed_at", "summaries"}, f"state.journal[{index}]")
        entry_revision = as_int(mapping.get("revision"), f"state.journal[{index}].revision", minimum=1)
        require(entry_revision == index + 1, f"state.journal[{index}].revision must be {index + 1}")
        transaction_id = clean_text(mapping.get("transaction_id"), f"state.journal[{index}].transaction_id", max_bytes=128)
        require(transaction_id not in journal_revisions, f"state.journal repeats transaction_id {transaction_id}")
        journal_revisions[transaction_id] = entry_revision
        clean_text(mapping.get("committed_at"), f"state.journal[{index}].committed_at", max_bytes=64)
        summaries = as_list(mapping.get("summaries"), f"state.journal[{index}].summaries")
        require(bool(summaries), f"state.journal[{index}].summaries must not be empty")
        for summary_index, summary in enumerate(summaries):
            clean_text(summary, f"state.journal[{index}].summaries[{summary_index}]", max_bytes=768)
    transactions = as_mapping(state.get("applied_transactions"), "state.applied_transactions")
    require(set(transactions) == set(journal_revisions), "state.applied_transactions must match state.journal transaction ids")
    for transaction_id, record in transactions.items():
        clean_text(transaction_id, "state.applied_transactions key", max_bytes=128)
        mapping = as_mapping(record, f"state.applied_transactions.{transaction_id}")
        require_known_keys(mapping, {"revision", "digest", "item_ids"}, f"state.applied_transactions.{transaction_id}")
        transaction_revision = as_int(mapping.get("revision"), f"state.applied_transactions.{transaction_id}.revision", minimum=1)
        require(transaction_revision == journal_revisions[transaction_id], f"state.applied_transactions.{transaction_id}.revision does not match journal")
        digest = clean_text(mapping.get("digest"), f"state.applied_transactions.{transaction_id}.digest", max_bytes=64)
        require(len(digest) == 64 and all(char in "0123456789abcdef" for char in digest), f"state.applied_transactions.{transaction_id}.digest is invalid")
        item_ids = clean_id_list(mapping.get("item_ids"), f"state.applied_transactions.{transaction_id}.item_ids")
        require(bool(item_ids), f"state.applied_transactions.{transaction_id}.item_ids must not be empty")
        require(all(item_id in items for item_id in item_ids), f"state.applied_transactions.{transaction_id}.item_ids references an unknown item")
    result = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_revision": revision,
        "next_item_number": next_number,
        "items": items,
        "journal": copy.deepcopy(journal),
        "applied_transactions": copy.deepcopy(transactions),
    }
    if book is not None:
        result["book"] = book
    return result


def load_state(store: Store) -> dict[str, Any] | None:
    if not store.state_path.exists():
        return None
    return validate_state(read_json(store.state_path), store=store)


def normalize_preference(value: object, label: str, *, allow_status: bool) -> dict[str, Any]:
    preference = as_mapping(value, label)
    allowed = {"kind", "scope", "assertion", "quote", "source_ref", "source", "confidence", "importance", "reason"}
    if allow_status:
        allowed |= {"status", "conflicts_with"}
    require_known_keys(preference, allowed, label)
    raw_source = preference.get("source")
    require(
        raw_source not in {"repeated_correction", "inferred_pattern"},
        f"{label}.source「{raw_source}」已不再写入：作者记忆只记作者明确表达的偏好，"
        f"不从重复修改或成稿轨迹推断；范围含糊的原话用 explicit_user 并置 status=pending",
    )
    source = choice(raw_source, WRITE_SOURCES, f"{label}.source")
    status = choice(preference.get("status"), ("active", "pending", "conflict"), f"{label}.status") if allow_status else "active"
    conflicts = clean_id_list(preference.get("conflicts_with", []), f"{label}.conflicts_with") if allow_status else []
    if status == "active":
        require(not conflicts, f"{label}.conflicts_with must be empty for active status")
    elif status == "conflict":
        require(bool(conflicts), f"{label}.conflicts_with is required for conflict status")
    else:
        require(not conflicts, f"{label}.conflicts_with is only valid for conflict status")
    return {
        "kind": choice(preference.get("kind"), KINDS, f"{label}.kind"),
        "scope": normalize_scope(preference.get("scope"), f"{label}.scope"),
        # 여기서는 기존 상한을 적용하고 ASSERTION_MAX_BYTES는 실제 새 항목 생성 시에만
        # require_new_item_assertion으로 검사해 기존 긴 단정을 강화할 수 있게 한다.
        "assertion": clean_text(preference.get("assertion"), f"{label}.assertion", max_bytes=LEGACY_ASSERTION_MAX_BYTES),
        "quote": clean_text(preference.get("quote"), f"{label}.quote", max_bytes=768),
        "source_ref": optional_text(preference.get("source_ref"), f"{label}.source_ref", max_bytes=240),
        "source": source,
        "confidence": choice(preference.get("confidence"), CONFIDENCE_LEVELS, f"{label}.confidence"),
        "importance": choice(preference.get("importance"), IMPORTANCE_LEVELS, f"{label}.importance"),
        "status": status,
        "reason": clean_text(preference.get("reason"), f"{label}.reason", max_bytes=480),
        "conflicts_with": conflicts,
    }


def normalize_transaction(value: object) -> dict[str, Any]:
    transaction = as_mapping(value, "transaction")
    require_known_keys(transaction, {"schema_version", "transaction_id", "expected_state_revision", "operations"}, "transaction")
    require(transaction.get("schema_version") == INPUT_SCHEMA_VERSION, f"transaction.schema_version must be {INPUT_SCHEMA_VERSION}")
    transaction_id = clean_text(transaction.get("transaction_id"), "transaction.transaction_id", max_bytes=128)
    operations = as_list(transaction.get("operations"), "transaction.operations")
    require(1 <= len(operations) <= 32, "transaction.operations must contain 1-32 operations")
    normalized_operations: list[dict[str, Any]] = []
    for index, raw_operation in enumerate(operations):
        label = f"transaction.operations[{index}]"
        operation = as_mapping(raw_operation, label)
        action = operation.get("action")
        if action == "remember":
            require_known_keys(operation, {"action", "preference"}, label)
            normalized_operations.append({"action": action, "preference": normalize_preference(operation.get("preference"), f"{label}.preference", allow_status=True)})
        elif action == "decide":
            require_known_keys(operation, {"action", "item_id", "decision", "quote", "reason"}, label)
            normalized_operations.append({
                "action": action,
                "item_id": clean_id_list([operation.get("item_id")], f"{label}.item_id", maximum=1)[0],
                "decision": choice(operation.get("decision"), ("activate", "reject"), f"{label}.decision"),
                "quote": clean_text(operation.get("quote"), f"{label}.quote", max_bytes=768),
                "reason": clean_text(operation.get("reason"), f"{label}.reason", max_bytes=480),
            })
        elif action == "replace":
            require_known_keys(operation, {"action", "old_ids", "preference"}, label)
            old_ids = clean_id_list(operation.get("old_ids"), f"{label}.old_ids")
            require(bool(old_ids), f"{label}.old_ids must not be empty")
            normalized_operations.append({"action": action, "old_ids": old_ids, "preference": normalize_preference(operation.get("preference"), f"{label}.preference", allow_status=False)})
        elif action == "forget":
            require_known_keys(operation, {"action", "item_id", "quote", "reason"}, label)
            normalized_operations.append({
                "action": action,
                "item_id": clean_id_list([operation.get("item_id")], f"{label}.item_id", maximum=1)[0],
                "quote": clean_text(operation.get("quote"), f"{label}.quote", max_bytes=768),
                "reason": clean_text(operation.get("reason"), f"{label}.reason", max_bytes=480),
            })
        else:
            raise AuthorMemoryError(f"{label}.action must be one of: remember, decide, replace, forget")
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "expected_state_revision": as_int(transaction.get("expected_state_revision"), "transaction.expected_state_revision"),
        "operations": normalized_operations,
    }


def normalize_record_event(value: object) -> dict[str, Any]:
    event = as_mapping(value, "event")
    require_known_keys(event, {"schema_version", "event_id", "operation"}, "event")
    require(event.get("schema_version") == INPUT_SCHEMA_VERSION, f"event.schema_version must be {INPUT_SCHEMA_VERSION}")
    event_id = clean_text(event.get("event_id"), "event.event_id", max_bytes=120)
    normalized = normalize_transaction({
        "schema_version": INPUT_SCHEMA_VERSION,
        "transaction_id": f"record:{event_id}",
        "expected_state_revision": 0,
        "operations": [event.get("operation")],
    })
    return {"event_id": event_id, "operation": normalized["operations"][0]}


# ---------------------------------------------------------------------------
# 라우팅: 작업이 어느 store에 속하는가?
# ---------------------------------------------------------------------------


def scope_store_kind(scope: dict[str, str | None]) -> str:
    return "book" if scope["level"] == "book" else "project"


def store_kind_label(kind: str) -> str:
    return "书级（BP）" if kind == "book" else "项目级（AP）"


def operation_store_kind(operation: dict[str, Any], label: str) -> str:
    action = operation["action"]
    if action in {"decide", "forget"}:
        return id_store(operation["item_id"])
    preference = operation["preference"]
    kind = scope_store_kind(preference["scope"])
    if action == "remember":
        for conflict_id in preference["conflicts_with"]:
            require(
                id_store(conflict_id) == kind,
                f"{label}.conflicts_with 只能引用同一 store 的条目（{conflict_id} 在{store_kind_label(id_store(conflict_id))}）："
                f"本书例外不算与全局规则冲突，直接 remember 为 book 条目即可",
            )
        return kind
    for old_id in operation["old_ids"]:
        require(
            id_store(old_id) == kind,
            f"{label} replace 不能跨 store：{old_id} 在{store_kind_label(id_store(old_id))}，新条目范围属于{store_kind_label(kind)}；"
            f"跨 store 改版拆成 forget＋remember，存量 book 条目先 migrate",
        )
    return kind


def transaction_store_kind(transaction: dict[str, Any]) -> str:
    kinds = {
        operation_store_kind(operation, f"transaction.operations[{index}]")
        for index, operation in enumerate(transaction["operations"])
    }
    require(
        len(kinds) == 1,
        "一份事务只能写一个 store：项目级（global/genre/workflow 范围或 AP 编号）与书级（book 范围或 BP 编号）的操作要分开提交",
    )
    return kinds.pop()


# ---------------------------------------------------------------------------
# 트랜잭션
# ---------------------------------------------------------------------------


def transaction_digest(transaction: dict[str, Any]) -> str:
    canonical = json.dumps(transaction, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint(preference: dict[str, Any]) -> str:
    """같은 선호의 식별 기준은 kind+scope+단정이다. scope.value는 same_scope_value처럼 casefold로 비교한다.
    아니면 Urban과 urban을 각각 만들어 동일 단정 둘이 프롬프트에 들어간다."""
    scope = preference["scope"]
    value = {
        "kind": preference["kind"],
        "scope": {"level": scope["level"], "value": None if scope["value"] is None else scope["value"].casefold()},
        "assertion": preference["assertion"].casefold(),
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require_new_item_assertion(preference: dict[str, Any]) -> None:
    """새 단정은 한 문장으로 제한한다. 기존 강화는 이 경로를 거치지 않아 긴 기존 단정도 다시 확인할 수 있다.
    그렇지 않으면 작가가 선호를 재확인할 때 중복 항목만 생겨 저장소가 더 붐빈다."""
    size = len(preference["assertion"].encode("utf-8"))
    require(
        size <= ASSERTION_MAX_BYTES,
        f"新条目的 assertion {size} 字节，超出 {ASSERTION_MAX_BYTES} 字节上限——"
        f"断言限一句话，需要解释的背景写进 reason。若这是对已有条目的重申，"
        f"原样使用该条目的 assertion 即可强化（不受本上限约束）；"
        f"若确实是几条互不依赖的偏好，才拆成几条分别记录。",
    )


def require_scope_fits_store(state: dict[str, Any], scope: dict[str, str | None]) -> None:
    book = state.get("book")
    if book is None:
        require(
            scope["level"] != "book",
            "book 级条目须传 --book-root {书目录}——记忆随书存放在 {书}/.story/작가기억/，不再写进工作区的项目级 store",
        )
    else:
        require(
            scope_fits_store(scope, book),
            f"book 条目的范围「{scope['value']}」与本书 store「{book}」不一致——只有这本书的条目才住在这个书目录",
        )


def next_item_id(state: dict[str, Any]) -> str:
    prefix = STORE_PREFIX["book"] if state.get("book") is not None else STORE_PREFIX["project"]
    item_id = f"{prefix}{state['next_item_number']:03d}"
    state["next_item_number"] += 1
    return item_id


def allocate_item(state: dict[str, Any], preference: dict[str, Any], revision: int) -> dict[str, Any]:
    require_new_item_assertion(preference)
    require_scope_fits_store(state, preference["scope"])
    return {
        "id": next_item_id(state),
        "kind": preference["kind"],
        "scope": copy.deepcopy(preference["scope"]),
        "assertion": preference["assertion"],
        "confidence": preference["confidence"],
        "importance": preference["importance"],
        "status": preference["status"],
        "source": preference["source"],
        "reason": preference["reason"],
        "conflicts_with": list(preference["conflicts_with"]),
        "confirmation_count": 1,
        "evidence": [{"quote": preference["quote"], "source_ref": preference["source_ref"]}],
        "created_revision": revision,
        "updated_revision": revision,
        "superseded_by": None,
    }


def best_level(first: str, second: str) -> str:
    return first if RANK[first] >= RANK[second] else second


def add_evidence(item: dict[str, Any], quote: str, source_ref: str | None) -> None:
    evidence = {"quote": quote, "source_ref": source_ref}
    if evidence not in item["evidence"]:
        item["evidence"].append(evidence)


def require_item(state: dict[str, Any], item_id: str, label: str) -> dict[str, Any]:
    require(item_id in state["items"], f"{label} references unknown item {item_id}")
    return state["items"][item_id]


def apply_remember(state: dict[str, Any], preference: dict[str, Any], revision: int) -> str:
    require_scope_fits_store(state, preference["scope"])
    for conflict_id in preference["conflicts_with"]:
        conflict = require_item(state, conflict_id, "remember")
        require(conflict["status"] == "active", f"remember conflict {conflict_id} must be active")
    preference_fingerprint = fingerprint(preference)
    for item in state["items"].values():
        if item["status"] not in {"active", "pending", "conflict"} or fingerprint(item) != preference_fingerprint:
            continue
        require(not (item["status"] == "conflict" and preference["status"] == "active"), f"conflict item {item['id']} must be resolved with replace or rejected")
        require(not (item["status"] == "active" and preference["status"] == "conflict"), f"active item {item['id']} cannot be recategorized as its own conflict")
        add_evidence(item, preference["quote"], preference["source_ref"])
        item["confirmation_count"] += 1
        item["confidence"] = best_level(item["confidence"], preference["confidence"])
        item["importance"] = best_level(item["importance"], preference["importance"])
        item["updated_revision"] = revision
        item["reason"] = preference["reason"]
        if item["status"] == "pending" and preference["status"] == "active":
            item["status"] = "active"
        elif item["status"] == "pending" and preference["status"] == "conflict":
            item["status"] = "conflict"
            item["conflicts_with"] = list(preference["conflicts_with"])
        elif item["status"] == "conflict" and preference["status"] == "conflict":
            item["conflicts_with"] = sorted(set(item["conflicts_with"]) | set(preference["conflicts_with"]))
        return f"强化 {item['id']}：{item['assertion']}"
    item = allocate_item(state, preference, revision)
    state["items"][item["id"]] = item
    return f"新增 {item['id']}（{item['status']}）：{item['assertion']}"


def apply_decide(state: dict[str, Any], operation: dict[str, Any], revision: int) -> str:
    item = require_item(state, operation["item_id"], "decide")
    require(item["status"] in {"pending", "conflict"}, f"decide requires pending/conflict item, got {item['status']}")
    if operation["decision"] == "activate":
        require(item["status"] == "pending" and not item["conflicts_with"], "conflict candidates must be activated with replace")
        item["status"] = "active"
        verb = "确认"
    else:
        item["status"] = "rejected"
        verb = "拒绝"
    add_evidence(item, operation["quote"], None)
    item["reason"] = operation["reason"]
    item["updated_revision"] = revision
    return f"{verb} {item['id']}：{item['assertion']}"


def release_conflicts(state: dict[str, Any], removed_ids: set[str], revision: int) -> int:
    """내린 active 항목은 더 이상 후보의 충돌 대상이 아니다. 충돌 대상이 빈 후보는 pending으로 돌린다."""
    released = 0
    for candidate in state["items"].values():
        if candidate["status"] != "conflict":
            continue
        retained = [item_id for item_id in candidate["conflicts_with"] if item_id not in removed_ids]
        if retained == candidate["conflicts_with"]:
            continue
        candidate["conflicts_with"] = retained
        candidate["updated_revision"] = revision
        if not retained:
            candidate["status"] = "pending"
            released += 1
    return released


def apply_replace(state: dict[str, Any], operation: dict[str, Any], revision: int) -> str:
    old_items = [require_item(state, item_id, "replace") for item_id in operation["old_ids"]]
    for item in old_items:
        require(item["status"] in {"active", "conflict", "pending"}, f"replace target {item['id']} is already {item['status']}")
    replacement = allocate_item(state, operation["preference"], revision)
    replacement["status"] = "active"
    replacement["conflicts_with"] = []
    state["items"][replacement["id"]] = replacement
    for item in old_items:
        item["status"] = "superseded"
        item["superseded_by"] = replacement["id"]
        item["updated_revision"] = revision
    released = release_conflicts(state, {item["id"] for item in old_items}, revision)
    replaced = ", ".join(item["id"] for item in old_items)
    suffix = f"；{released} 个其他冲突候选退回待确认" if released else ""
    return f"用 {replacement['id']} 替代 {replaced}：{replacement['assertion']}{suffix}"


def apply_forget(state: dict[str, Any], operation: dict[str, Any], revision: int) -> str:
    item = require_item(state, operation["item_id"], "forget")
    require(item["status"] in {"active", "pending", "conflict"}, f"forget target {item['id']} is already {item['status']}")
    item["status"] = "superseded"
    item["superseded_by"] = None
    item["reason"] = operation["reason"]
    item["updated_revision"] = revision
    add_evidence(item, operation["quote"], None)
    released = release_conflicts(state, {item["id"]}, revision)
    suffix = f"；{released} 个冲突候选退回待确认" if released else ""
    return f"忘记 {item['id']}：{item['assertion']}{suffix}"


def committed_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def seal_transaction(
    updated: dict[str, Any],
    transaction_id: str,
    digest: str,
    summaries: list[str],
    *,
    store: Store,
) -> dict[str, Any]:
    """이번 리비전을 journal / applied_transactions에 쓰고 전체 검증한다."""
    revision = updated["state_revision"] + 1
    updated["state_revision"] = revision
    updated["journal"].append({
        "revision": revision,
        "transaction_id": transaction_id,
        "committed_at": committed_now(),
        "summaries": summaries,
    })
    item_ids = sorted(
        (item_id for item_id, item in updated["items"].items() if item["updated_revision"] == revision),
        key=id_number,
    )
    require(bool(item_ids), "transaction did not update any author-memory item")
    updated["applied_transactions"][transaction_id] = {
        "revision": revision,
        "digest": digest,
        "item_ids": item_ids,
    }
    return validate_state(updated, store=store)


def apply_transaction(state: dict[str, Any], transaction: dict[str, Any], digest: str, *, store: Store) -> tuple[dict[str, Any], list[str]]:
    applied = state["applied_transactions"].get(transaction["transaction_id"])
    if applied is not None:
        require(applied["digest"] == digest, "transaction_id was already used with different content")
        return state, [f"事务已应用于修订 {applied['revision']}，本次为幂等重放"]
    require(transaction["expected_state_revision"] == state["state_revision"], f"stale state revision: expected {transaction['expected_state_revision']}, current {state['state_revision']}")
    updated = copy.deepcopy(state)
    revision = updated["state_revision"] + 1
    summaries: list[str] = []
    for operation in transaction["operations"]:
        if operation["action"] == "remember":
            summaries.append(apply_remember(updated, operation["preference"], revision))
        elif operation["action"] == "decide":
            summaries.append(apply_decide(updated, operation, revision))
        elif operation["action"] == "replace":
            summaries.append(apply_replace(updated, operation, revision))
        else:
            summaries.append(apply_forget(updated, operation, revision))
    return seal_transaction(updated, transaction["transaction_id"], digest, summaries, store=store), summaries


# ---------------------------------------------------------------------------
# 파생 뷰
# ---------------------------------------------------------------------------


def scope_label(scope: dict[str, str | None]) -> str:
    if scope["level"] == "global":
        return "全局"
    labels = {"genre": "题材", "book": "本书", "workflow": "流程"}
    return f"{labels[scope['level']]}：{scope['value']}"


def store_caption(state: dict[str, Any]) -> str:
    book = state.get("book")
    if book is None:
        return "项目级记忆（全局、题材、流程）；各书的书级记忆住在各自书目录的 .story/작가기억/。"
    return f"本书「{book}」的书级记忆；全局、题材、流程记忆住在工作区的 .story/작가기억/。"


def render_profile(state: dict[str, Any]) -> str:
    lines = [
        "# 作者画像",
        "",
        "<!-- 由 author_memory_commit.py 生成，请勿手改；修改请提交事务。 -->",
        "",
        f"> 状态修订：{state['state_revision']}。{store_caption(state)}仅列出已确认偏好；当前明确要求、本书设定与硬性门禁优先。",
        "",
    ]
    active = [item for item in state["items"].values() if item["status"] == "active"]
    for kind in KINDS:
        lines.extend([f"## {KIND_TITLES[kind]}", ""])
        items = sorted((item for item in active if item["kind"] == kind), key=lambda item: id_number(item["id"]))
        if not items:
            lines.extend(["- 暂无", ""])
            continue
        for item in items:
            # importance는 초과 시 프롬프트에 남을 항목을 결정하므로 반드시 표시한다. 작가 기억 정리는
            # 이 파일만 입력으로 쓰기 때문에 표시하지 않으면 무엇을 퇴역시킬지 판단할 수 없다.
            lines.append(
                f"- **{item['id']}**〔{scope_label(item['scope'])}｜重要 {item['importance']}"
                f"｜把握 {item['confidence']}｜确认 {item['confirmation_count']} 次〕{item['assertion']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_pending(state: dict[str, Any]) -> str:
    lines = [
        "# 待确认的作者习惯",
        "",
        "<!-- 由 author_memory_commit.py 生成，请勿手改；修改请提交事务。 -->",
        "",
        f"> 状态修订：{state['state_revision']}。{store_caption(state)}待确认项不参与创作约束，也不应打断当前任务。",
        "",
    ]
    items = sorted((item for item in state["items"].values() if item["status"] in {"pending", "conflict"}), key=lambda item: id_number(item["id"]))
    if not items:
        lines.extend(["暂无待确认项。", ""])
    for item in items:
        lines.extend([
            f"## {item['id']} · {'冲突' if item['status'] == 'conflict' else '待确认'}",
            "",
            f"- 候选习惯：{item['assertion']}",
            f"- 范围：{scope_label(item['scope'])}",
            f"- 原话：“{item['evidence'][-1]['quote']}”",
            f"- 依据：{item['reason']}",
            f"- 置信度 / 重要度：{item['confidence']} / {item['importance']}",
        ])
        if item["conflicts_with"]:
            lines.append(f"- 冲突对象：{', '.join(item['conflicts_with'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_journal(state: dict[str, Any]) -> str:
    lines = [
        "# 作者记忆变更记录",
        "",
        "<!-- 由 author_memory_commit.py 生成，请勿手改；最近记录在前。 -->",
        "",
        f"> {store_caption(state)}",
        "",
    ]
    if not state["journal"]:
        lines.extend(["暂无变更。", ""])
    for entry in reversed(state["journal"][-100:]):
        lines.extend([f"## r{entry['revision']} · {entry['committed_at']}", "", f"- 事务：`{entry['transaction_id']}`"])
        lines.extend(f"- {summary}" for summary in entry["summaries"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_views(state: dict[str, Any]) -> dict[str, str]:
    views = {
        "작가프로필.md": render_profile(state),
        "확인대기.md": render_pending(state),
        "변경기록.md": render_journal(state),
    }
    limits = {"작가프로필.md": PROFILE_MAX_BYTES, "확인대기.md": PENDING_MAX_BYTES, "변경기록.md": JOURNAL_MAX_BYTES}
    for name, payload in views.items():
        require(len(payload.encode("utf-8")) <= limits[name], f"{name} exceeds {limits[name]} bytes; consolidate old memory first")
    return views


def write_snapshot(store: Store, state: dict[str, Any]) -> None:
    views = render_views(state)
    state_payload = json_payload(state)
    require(len(state_payload.encode("utf-8")) <= STATE_MAX_BYTES, f"_author-memory-state.json exceeds {STATE_MAX_BYTES} bytes")
    for name, payload in views.items():
        write_if_changed(store.root / name, payload)
    # state가 기준이므로 마지막 커밋 지점이다.
    write_if_changed(store.state_path, state_payload)


# ---------------------------------------------------------------------------
# 조회와 예산
# ---------------------------------------------------------------------------


def same_scope_value(item_value: str | None, requested: str | None) -> bool:
    return requested is not None and item_value is not None and item_value.casefold() == requested.casefold()


def summarize_assertion(assertion: str, *, limit: int = 14) -> str:
    return assertion if len(assertion) <= limit else assertion[:limit] + "…"


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    """query items는 주 세션·스크립트의 kind/scope 판단용 네 필드만 포함한다. reason·evidence 등은 store 밖으로 내보내지 않는다."""
    return {"id": item["id"], "kind": item["kind"], "scope": item["scope"], "assertion": item["assertion"]}


def render_line(item: dict[str, Any]) -> str:
    """실행자가 읽는 한 행은 단정 원문+번호다. 주입 예산은 이 행들만 잰다."""
    return f"- {item['assertion']}（{item['id']}）"


def line_bytes(item: dict[str, Any]) -> int:
    """줄바꿈을 포함한 행의 주입 크기. 추정과 실제 채우기에서 같은 기준만 쓴다."""
    return len((render_line(item) + "\n").encode("utf-8"))


SCOPE_RANK = {"book": 0, "genre": 1, "workflow": 2, "global": 3}


def query_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """중요도→작품 예외→최근 갱신→확인 횟수→번호.
    중요도를 scope보다 먼저 정렬해야 초과 시 중요하지 않은 항목부터 빠진다. scope가 먼저면 low 작품 잡사항이 high 전역 원칙을 밀어낼 수 있다.
    같은 중요도 안에서만 작품 예외를 우선한다. 두 store의 리비전은 비교할 수 없지만 같은 scope는 항상 같은 store이므로
    합친 후에도 리비전으로 최근 갱신을 비교할 수 있다.
    """
    return (
        -RANK[item["importance"]],
        SCOPE_RANK[item["scope"]["level"]],
        -item["updated_revision"],
        -item["confirmation_count"],
        id_number(item["id"]),
    )


def fit_items(
    sorted_items: list[dict[str, Any]],
    revision: int,
    *,
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """렌더링 행을 QUERY_MAX_BYTES에 채운다. 안 들어가는 항목은 중단하지 않고 건너뛰어 뒤 짧은 항목을 막지 않는다. (결과 문서, 모든 누락 ID)를 반환한다.
    예산에는 lines만 센다. items·누락 목록·`extra`(book_revision 등)는 주 세션·스크립트용으로 실행자 프롬프트에 들어가지 않는다.
    따라서 누락은 상한 없이 전부 후보 우선순위로 열거하며 앞 항목일수록 작가에게 알려야 할 중요 누락이다.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    used = 0
    for item in sorted_items:
        size = line_bytes(item)
        if used + size > QUERY_MAX_BYTES:
            dropped.append(item)
            continue
        kept.append(item)
        used += size
    result: dict[str, Any] = {
        "ok": True,
        "command": "query",
        "initialized": True,
        "revision": revision,
        "items": [compact_item(item) for item in kept],
        "lines": [render_line(item) for item in kept],
        "omitted": len(dropped),
        "omitted_ids": [item["id"] for item in dropped],
        "omitted_summaries": {item["id"]: summarize_assertion(item["assertion"]) for item in dropped},
        # 조립 스크립트가 장르×절차로 여러 번 조회·병합한 뒤 누락 항목을 중요도로 재정렬할 수 있도록 중요도를 포함한다.
        "omitted_importance": {item["id"]: item["importance"] for item in dropped},
    }
    result.update(extra or {})
    return result, result["omitted_ids"]


def build_query_result(
    candidates: list[dict[str, Any]],
    project_state: dict[str, Any] | None,
    book_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """실제 조회와 쓰기 측 추정이 공유하는 유일한 채우기 진입점. 정렬된 후보에 book_revision 등을 보충해 채운다.
    기준이 갈라지면 응답에는 문제가 없다면서 실제 query에서 항목이 빠지는 거짓 음성이 된다."""
    extra: dict[str, Any] = {}
    if book_state is not None:
        extra["book_revision"] = book_state["state_revision"]
    revision = project_state["state_revision"] if project_state is not None else 0
    return fit_items(candidates, revision, extra=extra)


def merged_query(
    project_state: dict[str, Any] | None,
    book_state: dict[str, Any] | None,
    kinds: set[str],
    requested_scopes: dict[str, str | None],
) -> tuple[dict[str, Any], list[str]]:
    """실제 조회의 순수 함수 부분. 프로젝트는 kind/scope로 필터링하며 기존 book 항목은 migrate 전까지 제외한다.
    작품 store 전체가 해당 작품이므로 status/kind만 필터링한다. 합친 뒤 중요도→작품 예외→최근 갱신으로 채운다."""

    def relevant(item: dict[str, Any]) -> bool:
        if item["status"] != "active" or item["kind"] not in kinds:
            return False
        level = item["scope"]["level"]
        if level == "global":
            return True
        return level != "book" and same_scope_value(item["scope"]["value"], requested_scopes[level])

    candidates: list[dict[str, Any]] = []
    if project_state is not None:
        candidates.extend(item for item in project_state["items"].values() if relevant(item))
    if book_state is not None:
        candidates.extend(active_of_kinds(book_state, tuple(kinds)))
    candidates.sort(key=query_sort_key)
    return build_query_result(candidates, project_state, book_state)


def slice_weight(items: list[dict[str, Any]]) -> int:
    """실제 내용에서 구간이 차지하는 크기를 렌더링 행과 줄바꿈으로 잰다.
    fit_items와 같아야 한다. JSON 바이트를 쓰면 scope가 길고 단정이 짧은 구간을 무겁게 잘못 선택해
    렌더링 행은 가벼워 추정은 들어간다고 하면서 실제 조회는 넘치는 warnings 거짓 음성이 생긴다.
    """
    return sum(line_bytes(item) for item in items)


def active_of_kinds(state: dict[str, Any] | None, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    if state is None:
        return []
    return [item for item in state["items"].values() if item["status"] == "active" and item["kind"] in kinds]


def worst_case_items(
    project_state: dict[str, Any] | None,
    book_state: dict[str, Any] | None,
    kinds: tuple[str, ...],
) -> list[dict[str, Any]]:
    """작업 조합의 최악 후보: 전역 항목+scope 차원별 가장 무거운 단일 구간.
    조회는 book/genre/workflow 하나씩만 포함해 다른 작품이 함께 나오지 않으므로 전체 합계 대신 가장 무거운 구간을 쓴다.
    same_scope_value처럼 casefold로 합쳐 대소문자만 다른 작품을 별개로 추정하는 하한 오류를 피한다.
    book 차원은 현재 보이는 작품 store 전체이므로 작품 쓰기에서 ‘현재 작품+전역’은 정확하다.
    프로젝트 쓰기에 --book-root가 없으면 작품 store가 보이지 않아 프로젝트만 추정한다. 이전 프로젝트 book 항목은 조회·추정에서 제외한다.
    """
    pool = [item for item in active_of_kinds(project_state, kinds) if item["scope"]["level"] != "book"]
    worst = [item for item in pool if item["scope"]["level"] == "global"]
    slices: dict[str, dict[str, list[dict[str, Any]]]] = {"genre": {}, "workflow": {}}
    for item in pool:
        level = item["scope"]["level"]
        if level != "global":
            slices[level].setdefault((item["scope"]["value"] or "").casefold(), []).append(item)
    for level in ("genre", "workflow"):
        if slices[level]:
            worst.extend(max(slices[level].values(), key=slice_weight))
    worst.extend(active_of_kinds(book_state, kinds))
    worst.sort(key=query_sort_key)
    return worst


def legacy_book_items(project_state: dict[str, Any] | None) -> list[dict[str, Any]]:
    """업그레이드 전에 프로젝트 store에 쓴 활성 book 항목. migrate만 처리한다."""
    if project_state is None:
        return []
    return [
        item for item in project_state["items"].values()
        if item["scope"]["level"] == "book" and item["status"] in {"active", "pending", "conflict"}
    ]


def query_budget_warnings(project_state: dict[str, Any] | None, book_state: dict[str, Any] | None) -> list[str]:
    """쓰기 응답의 예산 안내: 작업 조합별 최악 조회로 채워 보고 못 담은 항목을 명시한다.
    쓰기는 주입 예산 때문에 실패하지 않으며 작가 기억 정리를 안내한다. 번호만으로는 작가프로필.md를 열어야 알 수 있으므로 단정 첫 문장도 보여 준다.
    """
    warnings: list[str] = []
    for task, kinds in QUERY_COMBOS.items():
        worst = worst_case_items(project_state, book_state, kinds)
        _, omitted = build_query_result(worst, project_state, book_state)
        if not omitted:
            continue
        assertions = {item["id"]: item["assertion"] for item in worst}
        shown = "；".join(f"{item_id}「{summarize_assertion(assertions[item_id])}」" for item_id in omitted[:3])
        more = f" 等 {len(omitted)} 条" if len(omitted) > 3 else ""
        warnings.append(
            f"「{task}」最坏查询装不下 {len(omitted)} 条，它们不会进入 prompt："
            f"{shown}{more}——超出 {QUERY_MAX_BYTES} 字节注入预算。"
            f"说「整理作者记忆」可合并同义条、退役过时条。"
        )
    return warnings


def visible_states(
    store: Store,
    updated: dict[str, Any],
    workspace: Path,
    book_root: Path | None,
    book: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """쓰기 후 보이는 두 단계 상태. 방금 쓴 것은 메모리에서, 다른 것은 읽기 전용으로 얻으며 없으면 None이다.
    이미 저장했으므로 다른 store의 디렉터리 부재·작품명 불일치·손상은 안내로만 낮춘다. 오류를 내면 호출자가 기억 실패로 알리고
    다른 event_id로 재시도해 중복 항목을 만들 수 있다."""
    try:
        if store.kind == "project":
            other = load_state(book_store(workspace, book_root, book)) if book_root is not None else None
            return updated, other, []
        return load_state(project_store(workspace)), updated, []
    except AuthorMemoryError as exc:
        other_label = "书级" if store.kind == "project" else "项目级"
        notice = f"已写入{store.label} store；但{other_label} store 读取失败，本次预算提醒没算上它：{exc}"
        return (updated, None, [notice]) if store.kind == "project" else (None, updated, [notice])


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------


def prepare_workspace(workspace: Path, book_root: Path | None = None) -> None:
    """각 명령 진입점에서 작업 공간을 검증하고 단일 작품 구조의 잘못 놓인 state를 먼저 복구한다.
    복구 전에는 프로젝트를 읽지 못하므로 모든 읽기 앞에 두어 읽기 전용 조회도 자체 복구하게 한다."""
    require(workspace.exists() and workspace.is_dir(), f"workspace does not exist: {workspace}")
    relocate_misplaced_book_state(workspace, book_root)


def store_fields(store: Store) -> dict[str, Any]:
    fields: dict[str, Any] = {"store": store.kind, "root": str(store.root)}
    if store.book is not None:
        fields["book"] = store.book
    return fields


def command_init(workspace: Path, book_root: Path | None, book: str | None) -> dict[str, Any]:
    prepare_workspace(workspace, book_root)
    store = book_store(workspace, book_root, book) if book_root is not None else project_store(workspace)
    state = load_state(store)
    if state is None:
        state = empty_state(store.book)
    write_snapshot(store, state)
    return {"ok": True, "command": "init", "revision": state["state_revision"], **store_fields(store)}


def command_commit(workspace: Path, book_root: Path | None, book: str | None, input_path: Path) -> dict[str, Any]:
    prepare_workspace(workspace, book_root)
    transaction = normalize_transaction(read_json(input_path))
    store = resolve_target_store(transaction_store_kind(transaction), workspace, book_root, book)
    require(store.state_path.exists(), f"{store.label} author memory is not initialized; run init first")
    state = load_state(store)
    digest = transaction_digest(transaction)
    updated, summaries = apply_transaction(state, transaction, digest, store=store)
    replayed = updated is state
    # 멱등 재실행에서도 스냅샷을 다시 써 누락·만료된 파생 뷰를 복구한다.
    write_snapshot(store, updated)
    project_state, book_state, load_warnings = visible_states(store, updated, workspace, book_root, book)
    return {
        "ok": True,
        "command": "commit",
        "revision": updated["state_revision"],
        "transaction_id": transaction["transaction_id"],
        "replayed": replayed,
        "item_ids": updated["applied_transactions"][transaction["transaction_id"]]["item_ids"],
        "summaries": summaries,
        "warnings": load_warnings + query_budget_warnings(project_state, book_state),
        **store_fields(store),
    }


def command_record(workspace: Path, book_root: Path | None, book: str | None, input_path: Path) -> dict[str, Any]:
    prepare_workspace(workspace, book_root)
    event = normalize_record_event(read_json(input_path))
    store = resolve_target_store(operation_store_kind(event["operation"], "event.operation"), workspace, book_root, book)
    state = load_state(store)
    if state is None:
        state = empty_state(store.book)
    transaction_id = f"record:{event['event_id']}"
    applied = state["applied_transactions"].get(transaction_id)
    expected_revision = applied["revision"] - 1 if applied is not None else state["state_revision"]
    transaction = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "expected_state_revision": expected_revision,
        "operations": [event["operation"]],
    }
    digest = transaction_digest(transaction)
    updated, summaries = apply_transaction(state, transaction, digest, store=store)
    replayed = updated is state
    write_snapshot(store, updated)
    record = updated["applied_transactions"][transaction_id]
    item_ids = record["item_ids"]
    receipt = f"Author Memory Receipt: r{record['revision']} · {', '.join(item_ids)}"
    project_state, book_state, load_warnings = visible_states(store, updated, workspace, book_root, book)
    return {
        "ok": True,
        "command": "record",
        "revision": updated["state_revision"],
        "applied_revision": record["revision"],
        "event_id": event["event_id"],
        "replayed": replayed,
        "item_ids": item_ids,
        "receipt": receipt,
        "summaries": summaries,
        "warnings": load_warnings + query_budget_warnings(project_state, book_state),
        **store_fields(store),
    }


def command_query(
    workspace: Path,
    book_root: Path | None,
    kinds: list[str] | None,
    book: str | None,
    genre: str | None,
    workflow: str | None,
) -> dict[str, Any]:
    prepare_workspace(workspace, book_root)
    require(
        bool(kinds),
        "query 必须显式传 --kind（按调用方 skill 写好的 query 命令选类型，映射表见 references/author-memory-maintenance.md），不再默认返回全部类型",
    )
    project_state = load_state(project_store(workspace))
    book_state = load_state(book_store(workspace, book_root, book)) if book_root is not None else None
    if project_state is None and book_state is None:
        return {"ok": True, "command": "query", "initialized": False, "revision": 0, "items": [], "lines": [],
                "omitted": 0, "omitted_ids": [], "omitted_summaries": {}, "omitted_importance": {}}
    requested_scopes = {
        "genre": optional_text(genre, "query.genre", max_bytes=180),
        "workflow": optional_text(workflow, "query.workflow", max_bytes=180),
    }
    # 담지 못한 항목은 중단 대신 건너뛴다. 긴 항목 하나가 뒤의 짧은 항목을 막지 않는다. 누락 ID는
    # omitted_ids로 보고한다. 비어 있지 않으면 더 없음이 아니라 기억 예산 초과로 정리가 필요하다는 뜻이다. 쓰기 측의
    # warnings도 같은 build_query_result 기준을 쓰므로 추정이 실제 결과와 일치한다.
    result, _ = merged_query(project_state, book_state, set(kinds), requested_scopes)
    require(
        sum(len((line + "\n").encode("utf-8")) for line in result["lines"]) <= QUERY_MAX_BYTES,
        "query lines exceed their fixed byte budget",
    )
    return result


def check_store(store: Store) -> dict[str, Any]:
    state = load_state(store)
    require(state is not None, f"{store.label} author memory is not initialized")
    views = render_views(state)
    for name, expected in views.items():
        view_path = store.root / name
        require(view_path.exists(), f"missing derived view: {view_path}")
        require(view_path.read_text(encoding="utf-8") == expected, f"derived view is stale or edited: {view_path}")
    counts = {status: sum(1 for item in state["items"].values() if item["status"] == status) for status in STATUSES}
    return {"revision": state["state_revision"], "counts": counts}


def command_check(workspace: Path, book_root: Path | None, book: str | None) -> dict[str, Any]:
    prepare_workspace(workspace, book_root)
    project = project_store(workspace)
    result: dict[str, Any] = {"ok": True, "command": "check"}
    if book_root is not None:
        store = book_store(workspace, book_root, book)
        result["book"] = {"name": store.book, "root": str(store.root), **check_store(store)}
        if project.state_path.exists():
            result["project"] = {"root": str(project.root), **check_store(project)}
    else:
        result["project"] = {"root": str(project.root), **check_store(project)}
    # 이전 호출 호환: 최상위 revision / counts는 프로젝트 store를 가리킨다.
    primary = result.get("project") or result["book"]
    result["revision"] = primary["revision"]
    result["counts"] = primary["counts"]
    return result


MIGRATE_PREFIX = "migrate:"


def migration_digest(item: dict[str, Any]) -> str:
    """이전 트랜잭션의 해시는 불변 식별 정보인 번호·유형·범위·단정만 본다. 증거·상태는 강화나 decide/forget으로 바뀐다.
    이를 넣으면 중간 실패 후 작가가 수정했을 때 영구적으로 already used with different content가 된다."""
    return transaction_digest({"id": item["id"], "kind": item["kind"], "scope": item["scope"], "assertion": item["assertion"]})


def migrated_item(source: dict[str, Any], new_id: str, revision: int, id_map: dict[str, str]) -> dict[str, Any]:
    """프로젝트의 기존 book 항목을 작품 store로 옮기며 단정·증거·확인 횟수·중요도는 보존하고 번호·리비전만 바꾼다.
    충돌 대상은 같은 작품의 이미 이전한 항목만 BP로 재매핑한다. 작품 예외는 전역보다 우선하므로 전역과의 충돌은 제거한다.
    대상이 빈 후보는 pending으로 돌린다."""
    item = copy.deepcopy(source)
    item["id"] = new_id
    item["created_revision"] = revision
    item["updated_revision"] = revision
    item["superseded_by"] = None
    item["conflicts_with"] = [id_map[old] for old in source["conflicts_with"] if old in id_map]
    if item["status"] == "conflict" and not item["conflicts_with"]:
        item["status"] = "pending"
    return item


def migration_records(state: dict[str, Any]) -> dict[str, str]:
    """작품 store의 원본 AP→생성된 BP 번호. 원본 항목마다 migrate:APxxx 트랜잭션 하나다."""
    records: dict[str, str] = {}
    for transaction_id, record in state["applied_transactions"].items():
        if transaction_id.startswith(MIGRATE_PREFIX) and is_item_id(transaction_id[len(MIGRATE_PREFIX):]):
            records[transaction_id[len(MIGRATE_PREFIX):]] = record["item_ids"][0]
    return records


def apply_single(state: dict[str, Any], transaction_id: str, digest: str, mutate, summaries: list[str], *, store: Store) -> dict[str, Any]:
    updated = copy.deepcopy(state)
    mutate(updated, updated["state_revision"] + 1)
    return seal_transaction(updated, transaction_id, digest, summaries, store=store)


def command_migrate(workspace: Path, book_root: Path | None, book: str | None) -> dict[str, Any]:
    """프로젝트의 특정 작품 기존 book 항목을 해당 작품 store로 옮긴다.
    원본별 migrate:APxxx 트랜잭션은 불변 필드 해시만 써 배치 구성·원본 상태 변화와 무관하게 최대 한 번 이전한다.
    이후 프로젝트 트랜잭션 하나로 원본을 superseded 처리하고 목적지를 적는다. 작품을 먼저 쓰고 프로젝트를 나중에 쓴다.
    중간 실패 후 재시도하면 작품의 기존 번호를 재사용하고 프로젝트만 보충한다.
    """
    prepare_workspace(workspace, book_root)
    require(book_root is not None, "migrate 须传 --book-root {书目录}：书名到书目录的映射由调用方给出")
    project = project_store(workspace)
    store = book_store(workspace, book_root, book)
    assert store.book is not None
    project_state = load_state(project)
    book_state = load_state(store)

    def result(migrated: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "ok": True,
            "command": "migrate",
            "migrated": migrated,
            "project_revision": project_state["state_revision"] if project_state is not None else 0,
            "revision": book_state["state_revision"] if book_state is not None else 0,
            "warnings": query_budget_warnings(project_state, book_state),
            **store_fields(store),
        }

    if project_state is None:
        return result([])
    legacy = sorted(
        (item for item in legacy_book_items(project_state) if same_scope_value(item["scope"]["value"], store.book)),
        key=lambda item: id_number(item["id"]),
    )
    if book_state is None:
        if not legacy:
            return result([])
        book_state = empty_state(store.book)
    id_map = migration_records(book_state)

    # 1) 작품 측: 미이전 원본마다 BP를 만들고 이미 이전했으면 번호를 재사용한다.
    for item in legacy:
        if item["id"] in id_map:
            continue
        transaction_id = f"{MIGRATE_PREFIX}{item['id']}"
        new_id = f"{STORE_PREFIX['book']}{book_state['next_item_number']:03d}"

        preview = migrated_item(item, new_id, 1, id_map)

        def create(updated: dict[str, Any], revision: int, source=item, new_id=new_id) -> None:
            updated["next_item_number"] += 1
            updated["items"][new_id] = migrated_item(source, new_id, revision, id_map)

        book_state = apply_single(
            book_state, transaction_id, migration_digest(item), create,
            [f"迁移 {item['id']} → {new_id}（{preview['status']}）：{item['assertion']}"],
            store=store,
        )
        id_map[item["id"]] = new_id
    # 멱등 재실행에서도 스냅샷을 다시 써 누락·만료된 파생 뷰를 복구한다.
    write_snapshot(store, book_state)

    # 2) 프로젝트 측: 이번 원본 항목을 superseded로 표시하고 목적지를 적는다.
    migrated = [{"from": item["id"], "to": id_map[item["id"]]} for item in legacy]
    if legacy:
        transaction_id = f"{MIGRATE_PREFIX}{store.book.casefold()}:r{project_state['state_revision'] + 1}"
        digest = transaction_digest({"transaction_id": transaction_id, "migrated": migrated})

        def move_out(updated: dict[str, Any], revision: int) -> None:
            for item in legacy:
                target = updated["items"][item["id"]]
                target["status"] = "superseded"
                target["superseded_by"] = None
                target["conflicts_with"] = []
                target["reason"] = f"已迁移到书级 store「{store.book}」：{id_map[item['id']]}"
                target["updated_revision"] = revision
            release_conflicts(updated, set(id_map), revision)

        summaries = [f"迁出 {pair['from']} → {pair['to']}：{project_state['items'][pair['from']]['assertion']}" for pair in migrated]
        project_state = apply_single(project_state, transaction_id, digest, move_out, summaries, store=project)
        write_snapshot(project, project_state)
    return result(migrated)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_location(child: argparse.ArgumentParser) -> None:
        child.add_argument("--workspace", required=True, type=Path)
        child.add_argument("--book-root", type=Path, help="书目录；书级条目（scope.level=book / BP 编号）的落点")
        child.add_argument("--book", help="书名；传了 --book-root 时默认取 store 记录的书名或目录名")

    for command in ("init", "check", "migrate"):
        add_location(subparsers.add_parser(command))
    for command in ("commit", "record"):
        child = subparsers.add_parser(command)
        add_location(child)
        child.add_argument("--input", required=True, type=Path)
    query = subparsers.add_parser("query")
    add_location(query)
    query.add_argument("--kind", action="append", choices=KINDS)
    query.add_argument("--genre")
    query.add_argument("--workflow")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            result = command_init(args.workspace, args.book_root, args.book)
        elif args.command == "commit":
            result = command_commit(args.workspace, args.book_root, args.book, args.input)
        elif args.command == "record":
            result = command_record(args.workspace, args.book_root, args.book, args.input)
        elif args.command == "query":
            result = command_query(args.workspace, args.book_root, args.kind, args.book, args.genre, args.workflow)
        elif args.command == "migrate":
            result = command_migrate(args.workspace, args.book_root, args.book)
        else:
            result = command_check(args.workspace, args.book_root, args.book)
        emit(result)
        return 0
    except AuthorMemoryError as exc:
        emit({"ok": False, "error": str(exc)}, error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
