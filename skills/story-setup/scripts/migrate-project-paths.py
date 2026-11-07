#!/usr/bin/env python3
"""기존 프로젝트를 원본 보존 방식으로 한국어 경로의 새 폴더에 복사한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

MAP = json.loads(Path(__file__).with_name("project-paths-ko.json").read_text(encoding="utf-8"))
CHAPTER = re.compile(r"第([0-9一二三四五六七八九十百零〇两]+)(?:-([0-9一二三四五六七八九十百零〇两]+))?章")
VOLUME = re.compile(r"第([0-9一二三四五六七八九十百零〇两]+)卷")


def number(raw: str) -> str:
    if raw.isascii() and raw.isdigit():
        return raw
    digits = dict(zip("零〇一二三四五六七八九两", [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2]))
    total = current = 0
    for char in raw:
        if char in digits:
            current = digits[char]
        elif char in "十百":
            total += (current or 1) * {"十": 10, "百": 100}[char]
            current = 0
        else:
            raise ValueError(f"지원하지 않는 장/권 번호: {raw}")
    return str(total + current)


def translate_component(name: str) -> str:
    if name in MAP["directories"]:
        return MAP["directories"][name]
    if name in MAP["files"]:
        return MAP["files"][name]
    for old, new in MAP["prefixes"].items():
        if name.startswith(old):
            name = new + name[len(old):]
            break
    name = CHAPTER.sub(lambda match: "제" + number(match[1]) + ("-" + number(match[2]) if match[2] else "") + "장", name)
    name = VOLUME.sub(lambda match: "제" + number(match[1]) + "권", name)
    for old, new in MAP["suffixes"].items():
        name = name.replace(old, new)
    return name


def plan(source: Path, destination: Path) -> list[tuple[Path, Path]]:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_dir():
        raise ValueError("원본 프로젝트 폴더가 없습니다.")
    if destination.exists():
        raise ValueError("목적지가 이미 있습니다. 새 폴더를 지정하세요.")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("원본과 목적지는 서로 포함할 수 없습니다.")
    if not any((source / name).exists() for name in ("设定", "大纲", "正文", "追踪", "설정", "개요", "본문", "추적", "正文.md", "본문.md", "长篇", "短篇", "장편", "단편")):
        raise ValueError("집필 프로젝트를 찾지 못했습니다.")
    rows, targets = [], {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError(f"링크는 자동 변환하지 않습니다: {path}")
        relative = path.relative_to(source)
        if ".git" in relative.parts:
            raise ValueError("Git 프로젝트는 별도 작업 복사본에서 .git 없이 전환하세요.")
        if path.name in (".tracking-commit.lock", ".author-memory.lock"):
            raise ValueError(f"진행 중인 작업 잠금을 먼저 확인하세요: {relative}")
        target = Path(*(translate_component(part) for part in relative.parts))
        key = target.as_posix().casefold()
        if key in targets:
            raise ValueError(f"경로 충돌: {targets[key]} / {relative} → {target}")
        targets[key] = relative
        rows.append((relative, target))
    return rows


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(source: Path, destination: Path, *, apply: bool = False) -> dict:
    if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
        raise ValueError("원본 루트 링크는 자동 변환하지 않습니다.")
    source, destination = source.resolve(), destination.resolve()
    rows = plan(source, destination)
    report = {"schema": "story-project-path-migration/v1", "applied": False,
              "source": str(source), "destination": str(destination),
              "renamed": [{"from": a.as_posix(), "to": b.as_posix()} for a, b in rows if a != b]}
    if not apply:
        return report
    if not destination.parent.is_dir():
        raise ValueError("목적지의 상위 폴더가 없습니다.")
    before = {a: digest(source / a) for a, _ in rows if (source / a).is_file()}
    staging = Path(tempfile.mkdtemp(prefix=".story-paths-", dir=destination.parent))
    try:
        # 파일 이름이 아니라 실제 프로젝트 상대 경로를 기준으로 참조를 바꾼다.
        replacements = []
        for a, b in rows:
            if (source / a).is_dir():
                # 단독 단어는 스키마의 분류/상태 값일 수 있다. 디렉터리는 구분자를 포함한다.
                replacements.extend([((source / a).as_posix() + "/", (destination / b).as_posix() + "/"),
                                     (str(source / a) + os.sep, str(destination / b) + os.sep)])
                if a != b:
                    replacements.extend([(a.as_posix() + "/", b.as_posix() + "/"),
                                         (str(a) + os.sep, str(b) + os.sep)])
                continue
            replacements.extend([((source / a).as_posix(), (destination / b).as_posix()),
                                 (str(source / a), str(destination / b))])
            if a != b:
                replacements.extend([(a.as_posix(), b.as_posix()), (str(a), str(b))])
        replacements = sorted(dict(replacements).items(), key=lambda pair: len(pair[0]), reverse=True)
        pattern = re.compile("|".join(re.escape(a) for a, _ in replacements)) if replacements else None
        lookup = dict(replacements)
        for old, new in rows:
            src, dst = source / old, staging / new
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            is_body = any(part in ("正文", "본문", "原文", "원문") for part in old.parts[:-1]) or old.name in ("正文.md", "본문.md")
            if not is_body and (src.suffix.lower() in (".md", ".json", ".yaml", ".yml", ".toml", ".csv") or src.name == ".active-book") and pattern:
                # 같은 폴더/상위 폴더를 기준으로 쓴 Markdown 링크도 실제 대상에 맞춘다.
                local_lookup = dict(lookup)
                for a, b in rows:
                    relative_old = Path(os.path.relpath(a, old.parent)).as_posix()
                    relative_new = Path(os.path.relpath(b, new.parent)).as_posix()
                    if (source / a).is_dir():
                        relative_old += "/"
                        relative_new += "/"
                    if relative_old != relative_new:
                        local_lookup[relative_old] = relative_new
                        local_lookup[relative_old.replace("/", "\\")] = relative_new.replace("/", "\\")
                local_pattern = re.compile("|".join(re.escape(a) for a in sorted(local_lookup, key=len, reverse=True)))
                raw = src.read_bytes()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise ValueError(f"UTF-8이 아닌 참조 문서: {old}")
                # 경로 앞뒤가 더 긴 이름의 일부인 경우에는 바꾸지 않는다.
                def rewrite(value):
                    def replace(match):
                        left = value[match.start()-1:match.start()] if match.start() else ""
                        right = value[match.end():match.end()+1]
                        if (left and (left.isalnum() or left == "_")) or (not match[0].endswith(("/", "\\")) and right and (right.isalnum() or right == "_")):
                            return match[0]
                        return local_lookup[match[0]]
                    return local_pattern.sub(replace, value)
                def walk(value):
                    if isinstance(value, str):
                        return rewrite(value)
                    if isinstance(value, list):
                        return [walk(item) for item in value]
                    if isinstance(value, dict):
                        return {key: walk(item) for key, item in value.items()}
                    return value
                if src.suffix.lower() == ".json":
                    document = json.loads(text.lstrip("\ufeff"))
                    converted = walk(document)
                    updated = json.dumps(converted, ensure_ascii=False, indent=2) + "\n" if converted != document else text
                else:
                    updated = rewrite(text)
                if updated != text:
                    dst.write_bytes(updated.encode("utf-8"))
        if plan(source, destination) != rows:
            raise ValueError("변환 도중 원본 파일 목록이 변경됐습니다.")
        for old, new in rows:
            if old in before and digest(source / old) != before[old]:
                raise ValueError(f"변환 도중 원본이 변경됐습니다: {old}")
            if old in before and (any(part in ("正文", "본문", "原文", "원문") for part in old.parts[:-1]) or old.name in ("正文.md", "본문.md")):
                if digest(staging / new) != before[old]:
                    raise ValueError(f"원고 보존 검사 실패: {old}")
        # 모든 복사가 성공한 후에만 새 프로젝트를 공개한다. 기존 목적지는 덮어쓰지 않는다.
        if destination.exists():
            raise ValueError("변환 중 목적지가 생성됐습니다.")
        os.rename(staging, destination)
        report["applied"] = True
        report["source_files_verified"] = len(before)
        return report
    finally:
        if staging.exists():
            if staging.resolve().parent != destination.parent or not staging.name.startswith(".story-paths-"):
                raise ValueError("임시 폴더 경계 검사 실패")
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="생략하면 변경 계획만 출력")
    args = parser.parse_args()
    try:
        report = migrate(args.source, args.destination, apply=args.apply)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"경로 변환 실패: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
