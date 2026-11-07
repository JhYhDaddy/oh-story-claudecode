#!/usr/bin/env python3
"""build_writer_prompt.py — narrative-writer의 spawn 프롬프트 골격을 결정적으로 구성한다.
사용법:
    python build_writer_prompt.py --project <작품디렉터리> --chapter N [--out [<파일>]]
경로 없는 `--out`은 `<작품디렉터리>/.story/work/제NNN장/writer_prompt.md`에 보관한다. segment·프롬프트·장별 트랜잭션 JSON은 이곳에만 둔다.
여러 작품·세션의 같은 장 번호가 충돌하며 Windows에는 없는 시스템 /tmp와, 장으로 오인될 본문/에는 쓰지 않는다.
`storyctl.py chapter commit` 성공 후 해당 장 작업 디렉터리를 자동 삭제한다.
집필 전 준비 첫 단계에 실행한다. stdout의 `===` 위는 주 세션이 빈 칸 외에는 그대로 복사할 프롬프트, 아래는 프롬프트에 넣지 않는 대조 보고서다.
역할 경계:
- 스크립트: 고정 첫 행·위치·제목 리터럴·상세 개요 포인터·문체 전문 경로/판정·앞 장 결말·참조 축소/감정/리듬 칸·고정 블록 포인터.
- 작가 기억(prose_style + story_design)을 조회해 author_preferences를 채우며 누락 항목과 장말에 작가에게 전할 문장을 대조 보고서에 쓴다.
- `설정/소재방향.md`의 ‘作者已定’(작품 선호·금지선·기각안)을 주입한다. AUTHOR_DECIDED_CHARS 가시 글자 초과 시 자르고 원문을 안내한다. 작품 설정이므로 작가 기억보다 우선한다.
- 주 세션은 실행 계획/장 의도/이번 작가 요구/장 기법/구간 속기/관련 인물/genre_prose_card/필수 설정/style_resolution의 고정 9칸을 채운다.
  조건부 2칸도 나타나면 주 세션 담당이다. author_preferences의 --genre/--workflow 한정 기억을 대신 조회하지 못했다면 적용 여부를 판단해 보충 조회한다(스크립트 실패 시 블록 전체 수동 조회).
  참조 축소가 불가능하면 감정·리듬 참조도 주 세션 담당이다. 보고서 끝에는 실제 미입력 칸 수 9–11을 표시한다.
  자료 칸은 기존 3단계 집필 전 준비의 속기·목표 감정·관련 인물·장 기법에 작가 요구·장르 카드·설정 보충·선호를 더한 것으로 모두 판단이 필요하다.
- 이어쓰기 상태 카드는 검증 후 주 세션이 선택해 속기 칸에 이번 장에 필요한 상태를 쓴다.
- 선택 블록이 없으면 제목과 사유를 남겨 원래 없음과 누락을 구분한다. 필수 블록 누락은 exit 2로, 자료 수정 후 재실행해야 하며 수동 조립으로 돌아갈 이유가 아니다.
종료: 0=골격 출력, 2=입력 누락·무효.
"""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from outline_view import parse as parse_volume

TAIL_CHARS = 400          # 앞 장 결말 주입 목표 글자 수. 문장을 자르지 않고 전체 행 단위로 거슬러 올라간다.
STATE_SECTIONS = ("当前位置", "长期约束", "核心角色状态", "活跃伏笔", "近三章速记", "下一章承诺", "连贯性风险")
SLOT_MARK = "［주 세션 작성］"
AUTHOR_DECIDED_CHARS = 600  # ‘作者已定’ 주입 상한(공백 제외). 초과하면 자르고 집필자가 원문을 읽도록 안내한다.
WORK_ROOT = (".story", "work")


def chapter_work_dir(project: Path, chapter: int) -> Path:
    """이번 장 임시 파일의 유일한 위치. storyctl.py 제출 후 정리 디렉터리와 동일하다."""
    width = max(3, len(str(chapter)))
    return project.joinpath(*WORK_ROOT, f"제{chapter:0{width}d}장")


def read_text(path: Path):
    try:
        return io.open(path, encoding="utf-8").read().lstrip("﻿")
    except (OSError, UnicodeError):
        return None


def substantive(text):
    if not text:
        return False
    body = re.sub(r"^#{1,6}[^\n]*", "", text, flags=re.M)
    body = re.sub(r"待补充|待办|待定|暂无|TODO|TBD", "", body, flags=re.I)
    return bool(re.sub(r"[\s_#*\[\]【】{}。，；:：-]", "", body))


def has_custom_style(text):
    # 실질적인 문장 하나로도 작가 선택을 표현할 수 있다.
    return substantive(re.sub(r"<!--[\s\S]*?-->", "", text or ""))


def find_chapter_file(directory: Path, chapter: int, prefix: str):
    if not directory.is_dir():
        return None
    pattern = re.compile(rf"^{prefix}제0*{chapter}장.*\.md$")
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and pattern.match(entry.name) and "_원본_" not in entry.name:
            return entry
    return None


def extract_field(outline_text: str, field: str):
    lines = outline_text.splitlines()
    pattern = re.compile(rf"^([ \t]*)[-*+]\s+\*{{0,2}}{re.escape(field)}\*{{0,2}}[ \t]*[：:][ \t]*(.*)$")
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        values = [match.group(2)]
        for following in lines[index + 1:]:
            bullet = re.match(r"^([ \t]*)[-*+]\s", following)
            if re.match(r"^#{1,6}\s", following) or (bullet and len(bullet.group(1)) <= len(match.group(1))):
                break
            values.append(following)
        return "\n".join(values).strip()
    return None


def extract_title(outline_text: str, chapter: int):
    match = re.search(rf"^#{{1,4}}\s*(?:第|제)\s*0*{chapter}\s*(?:章|장)\s*[：:]\s*(.+?)\s*$",
                      outline_text, re.M)
    return match.group(1).strip() if match else None


def extract_unit_block(volume_text: str, unit_id: str):
    lines, sections = parse_volume(volume_text)
    for section in sections:
        if section.unit != unit_id or "剧情单元" not in section.title or section.status == "已退役":
            continue
        end = next((other.start for other in sections
                    if other.start > section.start and other.level <= section.level), len(lines))
        return "\n".join(lines[section.start:end]).strip()
    return None


def extract_state_sections(state_text: str):
    found = {}
    for section in STATE_SECTIONS:
        match = re.search(rf"^##\s*{section}\s*$(.*?)(?=^##\s|\Z)",
                          state_text, re.M | re.S)
        if match and match.group(1).strip():
            found[section] = match.group(1).strip()
    return found


def previous_chapter_tail(project: Path, chapter: int):
    """끝에서 전체 행 단위로 올라가 TAIL_CHARS가 되면 멈추며 문장 중간을 자르지 않는다."""
    prev = find_chapter_file(project / "본문", chapter - 1, "")
    if prev is None:
        return None, None
    text = read_text(prev)
    if not text:
        return prev, None
    lines = [line for line in text.rstrip().splitlines() if line.strip()]
    picked, total = [], 0
    for line in reversed(lines):
        picked.append(line)
        total += len(line)
        if total >= TAIL_CHARS:
            break
    return prev, "\n".join(reversed(picked))


MEMORY_KINDS = ("prose_style", "story_design")
IMPORTANCE_RANK = {"low": 1, "medium": 2, "high": 3}
MISSED_SHOWN = 8  # 작가에게 전할 문장에 명시할 최대 항목 수. 나머지는 ‘等’으로 줄이고 전체는 작가 기억 정리로 보낸다.
# 절차 한정 작가 기억에서 이 값들은 장편 본문 집필을 뜻한다.
LONG_WRITE_WORKFLOWS = {"장편", "长篇写作", "写长篇", "长篇连载", "长篇网文", "长篇正文", "story-long-write"}


def scoped_memory_values(workspace: Path):
    """프로젝트 store의 장르·절차 한정 active 값: {"genre": {...}, "workflow": {...}}."""
    values = {"genre": set(), "workflow": set()}
    state = read_text(workspace / ".story" / "작가기억" / "_author-memory-state.json")
    try:
        items = (json.loads(state) if state else {}).get("items") or {}
        items = list(items.values())
    except (ValueError, AttributeError, TypeError):
        return values
    for item in items:
        if not isinstance(item, dict):
            continue
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        if (item.get("status") == "active" and item.get("kind") in MEMORY_KINDS
                and scope.get("level") in values and scope.get("value")):
            values[scope["level"]].add(scope["value"])
    return values


WORKSPACE_MARKERS = (".active-book", "장편", "단편", "작품분석실")


def memory_state_kind(directory: Path):
    """`.story/작가기억/` state에 book 필드가 없으면 project, 작품명이 있으면 book, 없거나 읽지 못하면 None이다.
    author_memory_commit.py의 peek_book_name과 같은 기준이다."""
    text = read_text(directory / ".story" / "작가기억" / "_author-memory-state.json")
    try:
        document = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    book = document.get("book")
    return "book" if isinstance(book, str) and book.strip() else "project"


def find_workspace(project: Path):
    """작가 기억 조회용 작업 공간을 author-memory.md의 저장·라우팅 규칙으로 찾아 (디렉터리, 식별 성공 여부)를 반환한다.
    순서: 작품·상위의 `.story-deployed`; 부모가 장편/短篇이면 그 위; 작품 자체의 프로젝트 기억 또는 `书级/`;
    `.active-book`, `장편/`, `단편/`, `작품분석실/`, 프로젝트 기억이 있는 가장 가까운 상위(홈 전까지, 홈 제외).
    모두 없으면 작품 디렉터리를 추정 작업 공간으로 쓴다. DSH 등은 배포 표식을 쓰지 않아 다중 작품의 작품을 공간으로 오인하면 조회 오류나 기억 이동이 생긴다.
    """
    project = project.resolve()
    deployed = next((d for d in (project, *project.parents) if (d / ".story-deployed").is_file()), None)
    if deployed is not None:
        return deployed, True
    if project.parent.name in {"장편", "단편"}:
        return project.parent.parent, True
    if memory_state_kind(project) == "project" or (project / ".story" / "작가기억" / "书级").is_dir():
        return project, True
    try:
        home = Path.home().resolve()
    except (RuntimeError, KeyError):  # 홈 디렉터리를 얻지 못하면 루트까지 탐색한다.
        home = None
    for ancestor in project.parents:
        if ancestor == home:
            break
        if any((ancestor / marker).exists() for marker in WORKSPACE_MARKERS) or memory_state_kind(ancestor) == "project":
            return ancestor, True
    return project, False


def genre_line(project: Path):
    """‘题材类型’ 행 원문. 미입력 템플릿 {…}는 없음으로 본다."""
    text = read_text(project / "설정" / "소재방향.md") or ""
    match = re.search(r"^[ \t]*[-*+]?[ \t]*\**题材(?:类型)?\**[ \t]*[：:](.*)$", text, re.M)
    if not match or "{" in match.group(1):
        return ""
    return match.group(1).strip()


def book_genres(project: Path):
    """‘题材类型’ 행을 구분자로 나눠 단어를 얻는다."""
    return {word.casefold() for word in re.split(r"[\W_丨×]+", genre_line(project)) if word}


GENRE_CARD_DIR = Path(__file__).resolve().parent.parent / "references" / "genre-prose-cards"


def match_genre_cards(project: Path):
    """장르 본문 안내 카드가 없으면 ‘题材类型’을 카드 머리 genre/aliases와 맞춰 주 세션의 전체 색인 읽기를 줄인다.
    최장 일치 우선: ‘玄幻言情’ 안의 ‘玄幻’처럼 다른 카드의 더 긴 일치 안에 들어간 단어는 해당 카드 적중으로 세지 않는다.
    장르 유형에서 먼저 나온 위치(주 장르), 긴 단어, 높은 신뢰도 순으로 선택한다. 최대 주·보조 두 카드의 [(경로, 신뢰도)]를 반환한다."""
    raw = genre_line(project).casefold()
    if not raw or not GENRE_CARD_DIR.is_dir():
        return []
    rank = {"high": 0, "medium": 1, "low": 2}
    spans = []  # (시작, 끝, 카드, 신뢰도): 카드별 일치 단어가 장르 유형에 나타나는 모든 위치.
    for card in sorted(GENRE_CARD_DIR.glob("*.md")):
        head = (read_text(card) or "").split("---")
        meta = head[1] if len(head) > 2 else ""
        genre = re.search(r"^genre:\s*(.+)$", meta, re.M)
        aliases = re.search(r"^aliases:\s*\[(.*)\]", meta, re.M)
        confidence = re.search(r"^confidence:\s*(\w+)", meta, re.M)
        level = confidence.group(1) if confidence else "low"
        names = [genre.group(1).strip()] if genre else [card.stem]
        names += [a.strip() for a in aliases.group(1).split(",")] if aliases else []
        for name in {n.casefold() for n in names if n}:
            spans += [(m.start(), m.end(), card, level) for m in re.finditer(re.escape(name), raw)]
    best = {}
    for start, end, card, level in spans:
        if any(c != card and s <= start and end <= e and e - s > end - start for s, e, c, _ in spans):
            continue
        key = (start, -(end - start), rank.get(level, 2), card.name)
        if card not in best or key < best[card][0]:
            best[card] = (key, level)
    hits = sorted((key, card, level) for card, (key, level) in best.items())
    return [(card, level) for _, card, level in hits[:2]]


def author_decided(project: Path):
    """`설정/소재방향.md`의 ‘## 作者已定’에서 템플릿 자리표시 행을 빼고 (본문, 절단 여부)를 반환한다. 절이 없으면 (None, False)."""
    text = read_text(project / "설정" / "소재방향.md") or ""
    match = re.search(r"^##[ \t]*作者已定[^\n]*\n(.*?)(?=^#{1,2}[ \t]|\Z)", text, re.M | re.S)
    if not match:
        return None, False
    lines = [line.rstrip() for line in match.group(1).splitlines()
             if line.strip() and not re.fullmatch(r"\s*[-*+]?\s*\{.*\}\s*", line)]
    kept, used, cut = [], 0, False
    for line in lines:
        size = len(re.sub(r"\s", "", line))
        if used + size > AUTHOR_DECIDED_CHARS:
            cut = True
            break
        kept.append(line)
        used += size
    return "\n".join(kept), cut


def query_author_memory(project: Path):
    """주 세션 대신 본문 집필의 작가 기억(prose_style + story_design)을 조회한다.
    주입은 query lines 그대로 구성한다. 각 조회 ≤2KB이며 집필자가 읽는 행을 재는 것이므로 다시 꾸미지 않는다.
    find_workspace가 공간을 식별하지 못하고 작품 디렉터리에 작품명 있는 기억이 있으면 조회하지 않는다. 단일 작품의 구형 기억인지
    단서 없는 다중 작품인지 구별할 수 없고 후자를 전자로 오인해 이동시키면 이후 정상 조회가 모두 실패하기 때문이다.
    장르 한정은 값이 작품 ‘题材类型’에 있을 때, 절차 한정은 장편 집필 값일 때만 대신 조회한다. 나머지는 추측하지 않고 주 세션에 보고한다.
    (주입 행, 누락 [(ID, 단정 첫 문장)], 미조회 한정 값, 오류)를 반환하며 오류 시 주 세션이 author-memory.md에 따라 수동 조회한다.
    """
    workspace, recognised = find_workspace(project)
    script = Path(__file__).with_name("author_memory_commit.py")
    if not script.is_file():
        return None, [], {}, "author_memory_commit.py가 없습니다"
    if not recognised and memory_state_kind(project) == "book":
        return None, [], {}, ("집필 작업 공간을 찾지 못했습니다(작품 폴더와 상위 폴더에 .active-book, 장편/, 단편/, 작품분석실/ 또는 프로젝트 작가 기억이 없음). "
                              "작품 폴더에는 작품별 기억만 있습니다. 먼저 author-memory.md에 따라 저장 위치와 라우팅 절을 확인해 --workspace를 지정하세요")
    scoped = scoped_memory_values(workspace)
    book = book_genres(project)
    genres = sorted(v for v in scoped["genre"] if v.casefold() in book) or [None]
    workflows = sorted(v for v in scoped["workflow"] if v.casefold() in {w.casefold() for w in LONG_WRITE_WORKFLOWS})
    skipped = {"genre": sorted(v for v in scoped["genre"] if v not in genres),
               "workflow": sorted(v for v in scoped["workflow"] if v not in workflows)}
    lines, omitted, summaries, importance, seen = [], [], {}, {}, set()
    for genre in genres:
        for workflow in workflows or [None]:
            command = [sys.executable, str(script), "query", "--workspace", str(workspace), "--book-root", str(project)]
            for kind in MEMORY_KINDS:
                command += ["--kind", kind]
            if genre:
                command += ["--genre", genre]
            if workflow:
                command += ["--workflow", workflow]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
            try:
                result = json.loads(completed.stdout or "{}")
            except ValueError:
                result = {}
            if not result.get("ok"):
                return None, [], {}, result.get("error") or completed.stderr.strip() or "query 실패"
            items, rendered = result.get("items") or [], result.get("lines") or []
            if len(items) != len(rendered):
                return None, [], {}, "query 출력에 lines가 없습니다(작가 기억 스크립트와 구성 스크립트의 버전 불일치)"
            for item, line in zip(items, rendered):
                if item.get("id") not in seen:
                    seen.add(item.get("id"))
                    lines.append(line)
            omitted += [i for i in result.get("omitted_ids") or [] if i not in omitted]
            summaries.update(result.get("omitted_summaries") or {})
            importance.update(result.get("omitted_importance") or {})
    # 각 조회의 누락은 우선순위로 정렬되어 있다. 병합 후 중요도로 재정렬하고 같은 중요도는 순서를 유지한다.
    # 작가에게 먼저 명시할 항목이 가장 중요해야 한다. 한 조회에서 빠져도 다른 조회에 포함되면 누락이 아니다.
    ranked = sorted((i for i in omitted if i not in seen),
                    key=lambda i: (-IMPORTANCE_RANK.get(importance.get(i), 0), omitted.index(i)))
    missed = [(i, summaries.get(i, "")) for i in ranked]
    return lines, missed, {k: v for k, v in skipped.items() if v}, None


def learn_heading_form(project: Path, chapter: int, title: str):
    """일반 규칙으로 추론하지 않고 기존 본문에서 제목의 단계·장 번호 채움·구분자를 배운다.
    일반 `## 第N章 章名`과 달리 작품은 `# 第015章 …` 등을 쓴다. 어느 쪽에도 맞지 않아 집필자가 매 장 기존 장을 다시 찾는 일을 대신한다.
    """
    body = project / "본문"
    if not body.is_dir():
        return None, "본문/ 폴더가 없습니다"
    pattern = re.compile(r"^(#+)([ \t　]*)(?:第|제)(0*\d+)(?:章|장)([ \t　]*)(.*)$")
    best = None
    for entry in sorted(body.glob("*.md")):
        num = re.match(r"^제(\d+)장", entry.name)
        if not num or int(num.group(1)) == chapter:
            continue
        head = (read_text(entry) or "").lstrip().splitlines()
        if not head:
            continue
        hit = pattern.match(head[0].strip())
        if hit:
            number = int(num.group(1))
            if number < chapter and (best is None or number > best[0]):
                best = (number, hit)
    if best is None:
        return None, "본문/에 제목 형식을 읽을 수 있는 기존 장이 없습니다. 집필자는 자신의 제목 규칙을 따르세요"
    _, hit = best
    level, gap1, digits, gap2 = hit.group(1), hit.group(2), hit.group(3), hit.group(4)
    # 선행 0이 있어야 0 채움 형식으로 보고 해당 자리 수만큼 채운다. `第15章`처럼 0이 없는 형식에서
    # 2자리 채움 규칙을 배워 9장을 `第09章`으로 쓰면 안 된다.
    if digits.startswith("0"):
        number, how = f"{chapter:0{len(digits)}d}", f"{len(digits)}자리로 앞에 0을 채움"
    else:
        number, how = str(chapter), "앞에 0을 채우지 않음"
    start, end = ("제", "장") if hit[0].lstrip("# \t　").startswith("제") else ("第", "章")
    return (f"{level}{gap1}{start}{number}{end}{gap2 or ' '}{title}",
            f"기존 장 형식 적용({level} + 장 번호 {how})")


def build(project: Path, chapter: int, report: list):
    errors = []

    outline_file = find_chapter_file(project / "개요", chapter, "상세개요_")
    if outline_file is None:
        errors.append(f"필수 자료 누락: {project / '개요'}에 제{chapter}장 상세 개요가 없습니다")
        return None, errors
    outline_text = read_text(outline_file)
    if not outline_text or not outline_text.strip():
        errors.append(f"필수 자료 누락: {outline_file}이(가) 비어 있습니다")
        return None, errors

    parts = []
    title = extract_title(outline_text, chapter)

    # ---- 고정 첫 행(열 이름이 아닌 지시; 빠지면 집필자가 참조를 읽지 않고 시작함) ----
    parts.append(
        f"이번 작업: 제{chapter}장 집필. 작업 범위는 ‘집필 순서’를 따르세요. 시작 전에 ‘참조 파일 체계’의 각 행을 독립적으로 판단해 해당하는 자료를 읽으세요. "
        "해당하면 반드시 읽고, 해당하지 않으면 미리 읽지 않습니다. 전달 요약에 읽은 자료를 밝히세요.")

    parts.append(f"프로젝트 폴더: {project}")
    parts.append(f"대상: 제{chapter}장")
    if title:
        out_path = project / "본문" / f"제{chapter:03d}장_{title}.md"
    else:
        return None, [f"상세 개요에 장 제목이 없습니다: {outline_file}. ‘### 제N장: 장 제목’ 형식이 필요합니다"]
    if any(char in title for char in '/\\'):
        return None, ["장 제목에 경로 구분자를 넣을 수 없습니다"]
    parts.append(f"최종 저장 경로: {out_path}")
    if title:
        heading_line, how = learn_heading_form(project, chapter, title)
        if heading_line:
            parts.append(
                f"제목 행(그대로 복사하고 일반 규칙으로 다시 만들지 않음): {heading_line}")
            report.append(f"제목 행: {heading_line}　{how}")
        else:
            report.append(f"제목 행: 넣지 않음 — {how}")

    # ---- 상세 개요: 경로만 제공하고 전문을 주입하지 않음 ----
    parts.append(f"상세 개요 파일(집필 전에 끝까지 읽기): {outline_file}")

    # ---- 이어쓰기 상태 카드: 구조 검증 후 주 세션이 관련 상태 선택 ----
    state_file = project / "추적" / "문맥.md"
    state_text = read_text(state_file)
    if not state_text:
        errors.append(f"필수 자료 누락: {state_file}을(를) 읽을 수 없습니다")
    else:
        found = extract_state_sections(state_text)
        missing = [s for s in STATE_SECTIONS if s not in found]
        if missing:
            errors.append(
                f"필수 자료 누락: {state_file}에 다음 항목이 없습니다: " + "、".join(missing) +
                "(이어 쓰기 상태 카드는 고정된 7개 항목이어야 합니다. 먼저 tracking_commit.py로 파생 문서를 복구하세요)")
        else:
            report.append("이어 쓰기 상태: 7개 항목 검증 완료. 주 세션은 이번 장에 필요한 내용만 ‘이번 장 속기’에 정리하세요")

    # ---- 문체: 작품 맞춤 문체는 스크립트가 전체 처리 ----
    style_file = project / "설정" / "문체.md"
    style_text = read_text(style_file)
    custom_style = has_custom_style(style_text)
    if custom_style:
        parts.append(f"문체 파일: {style_file}(작품 문체의 기준. 집필과 AI 문체 제거 모두 전문을 읽고 요약은 색인으로만 사용)")
        parts.append(
            "문체 우선순위: `설정/문체.md`의 문장·문단, 문법, 대화 처리, 문장 부호, 삭제·수정 방향에 관한 규정은 "
            "style-resolution.md에 따라 현재 요청 > 작품 문체 > active 작가 기억 > 비교 작품 > 공통 참조 순으로 적용합니다. 상세 개요의 사실, 정보 경계, 호출자가 정한 검사 범위와 파일 구조는 바꾸지 않습니다. "
            "표현 규칙이 충돌하면 작품 문체를 따르고, 전달 요약에 ‘문체 우선으로 적용하지 않은 공통 조항’을 기록하세요.")
        report.append("문체: custom_style=true. 표현 충돌은 항목별로 판단하며 참조 읽기는 작업 조건을 따릅니다")
    else:
        parts.append(
            "——— 문체 ———\n"
            "(사용할 수 있는 설정/문체.md가 없어 사용자 문체 모드를 적용하지 않습니다. "
            "benchmark-recall.md에 따라 비교 작품 문체를 불러오고, 주 세션이 경로와 참조 지시를 채우세요)")
        report.append("문체: custom_style=false. 문체 참조는 주 세션 담당(생략하지 않고 제목을 유지)")

    # ---- 앞 장 결말: 전체 장을 다시 읽지 않도록 경로는 주지 않음 ----
    if chapter > 1:
        prev_file, tail = previous_chapter_tail(project, chapter)
        if prev_file is None or not tail:
            errors.append(f"필수 자료 누락: 제{chapter - 1}장 본문을 찾거나 읽을 수 없습니다")
        else:
            parts.append(
                "——— 앞 장의 끝부분(연결용이며 재작성하지 않음. 장 전체가 필요하지 않아 경로는 제공하지 않음) ———\n" + tail)
            report.append(f"앞 장 끝부분: {prev_file.name}의 마지막 {len(tail)}자(행 전체가 포함되도록 범위를 조정)")

    # ---- 필수 설정: 전체 칸을 주 세션이 담당 ----
    slot_setting = (
        "——— 필수 설정 ———\n"
        f"{SLOT_MARK} 이번 장에 필요한 설정은 **해당 문장을 직접 적으세요**. 경로만 주고 집필자가 찾아보게 하지 마세요"
        "(Grep은 긴 행을 잘라 핵심 문장이 빠질 수 있습니다). 다음 두 출처를 모두 확인하세요: "
        "① 상세 개요가 명시한 `xxx.md`(해당 절 포함), ② 상세 개요에 이름이 없지만 이번 장에서 다루는 설정"
        "(용어의 의미, 절차, 기준 수치). 없으면 ‘없음’으로 적으세요.")

    # ---- 참조 축소 판정과 감정·리듬 칸 ----
    unit_field = extract_field(outline_text, "单元ID/位置")
    unit_id = None
    if unit_field:
        match = re.match(r"([A-Za-z0-9\-]+)", unit_field)
        if match:
            unit_id = match.group(1)
    unit_block = None
    if unit_id:
        for volume in sorted((project / "개요").glob("권개요_*.md")):
            block = extract_unit_block(read_text(volume) or "", unit_id)
            if block:
                unit_block = block
                break

    target_emotion = extract_field(outline_text, "目标情绪")
    card_text = read_text(project / "설정" / "소재본문안내.md")
    engine = extract_field(unit_block or "", "单元情绪引擎")
    tempo = (extract_field(unit_block or "", "单元节拍/章功能分配")
             or extract_field(unit_block or "", "单元节拍／章功能分配"))
    needs = {"장르 본문 안내 카드": card_text, "목표 감정": target_emotion,
             "단위 감정 동력": engine, "단위 박자·장 기능 배분": tempo}
    why = [name + "에 유효한 내용이 없음" for name, value in needs.items() if not substantive(value)]
    # 프로젝트·작업 공간에 비교 작품이 없으면 불러올 비교 문체도 없다. custom_style 누락만으로 참조 축소를 거부하지 않는다.
    # 가져온 작품의 분석 디렉터리가 작품 디렉터리와 같은 이름이면 자기 작품이므로 비교 대상으로 세지 않는다.
    def is_benchmark(base: Path, d: Path) -> bool:
        return d.is_dir() and not (base.name == "작품분석실" and d.name == project.name)
    no_benchmark = not any(is_benchmark(base, d)
                           for base in (project / "비교작품", project / "작품분석실", project.parent / "작품분석실")
                           if base.is_dir() for d in base.iterdir())
    if not custom_style and not no_benchmark:
        why.append("custom_style=false")
    downgrade = not why

    if downgrade:
        lines = [
            "selected_emotion_module: 참조 축소(출처: 상세 개요의 목표 감정「目标情绪」 + 단위 카드의 감정 동력「单元情绪引擎」)",
            f"  상세 개요 목표 감정: {target_emotion}",
        ]
        if engine:
            lines.append(f"  단위 감정 동력: {engine}")
        lines.append("rhythm_reference: 참조 축소(출처: 단위 카드의 박자·장 기능 배분「单元节拍/章功能分配」)")
        if tempo:
            lines.append(f"  {tempo}")
        slot_recall = "——— 감정·리듬 참조 ———\n" + "\n".join(lines)
        report.append(f"참조 축소: 가능. {'비교 작품 없음. ' if no_benchmark and not custom_style else '문체, '}장르 카드, 목표 감정, 단위 {unit_id}의 감정·박자 자료를 사용할 수 있습니다")
    else:
        slot_recall = ("——— 감정·리듬 참조 ———\n"
                       f"{SLOT_MARK} 참조를 축소할 수 없습니다(" + "、".join(why) +
                       "). benchmark-recall.md에 따라 전체 참조를 읽은 뒤 이 칸을 채우세요")
        report.append("참조 축소: 불가(" + "、".join(why) + ") — 전체 참조는 주 세션 담당")

    # ---- 주 세션 판단이 필요한 칸 ----
    work_dir = chapter_work_dir(project, chapter)
    parts.append(
        "——— 집필 순서 ———\n"
        f"{SLOT_MARK} 장 전체의 상세 개요로 구성을 잡으세요. 기본적으로 자연스러운 장면 전환이나 인과 흐름이 멈추는 지점에서 전반·후반으로 나눕니다. "
        "현재 집필할 부분의 사건 지점·구간을 적으세요. 먼저 전반만 작성하고 주 세션이 checkpoint를 한 번 측정한 뒤 "
        "후반 작업과 측정된 잔여 분량 범위를 전달합니다. 사용자가 한 번에 완성을 명시한 경우에만 ‘장 전체를 최종 경로에 바로 작성’으로 적으세요.\n"
        f"구간별 임시 파일: 전반 {work_dir / '전반.md'}, 후반 {work_dir / '후반.md'}"
        "(이곳에만 작성하고 /tmp나 본문/에는 쓰지 않음).")
    parts.append(f"——— 이번 장의 의도(한 문장) ———\n{SLOT_MARK}")
    parts.append("——— 작가의 이번 요청 ———\n"
                 f"{SLOT_MARK} 작가가 이번에 명시한 분량 범위, 반드시 일어날 일, 금지한 일, 멈출 지점, 장 끝에 남길 내용을 적으세요. 없으면 ‘없음’으로 적으세요.")
    parts.append(slot_recall)
    # 복선·권 단위 금기는 기존 설계대로 주 세션이 선택해 속기에 기록한다(3단계 상태 선택).
    # 선택은 판단이며 열 전체를 주입하면 작가만 아는 진실까지 넘기므로 스크립트가 통째로 주입하지 않는다.
    # 주 세션이 매 장 기억해야 하는 부담이 있어 고정된 세 질문 체크리스트를 안내문에 쓴다.
    parts.append(
        "——— 이번 장의 기법 ———\n"
        f"{SLOT_MARK} 상세 개요의 주된 기능에 따라 통쾌한 반격／반전／감정／미스터리／일상／없음 중 하나를 적으세요(SKILL.md의 이번 장 기법 참조). "
        "어느 문단에 사용할지 한 문장으로 덧붙이세요. 집필자는 자신의 읽기 표에 따라 해당 파일을 읽으며 여기에는 기법을 발췌하지 않습니다. 작품 문체는 충돌하는 표현 조항만 대체하며 파일 전체의 읽기를 생략하지 않습니다.")
    parts.append(
        "——— 이번 장 속기 ———\n"
        f"{SLOT_MARK} workflow-chapter 3단계의 상태 선택에 따라 작성하세요(`추적/문맥.md`는 "
        "이 프롬프트에 넣지 않으며 이 칸이 집필자의 유일한 상태 정보입니다). 핵심 인물 상태 중 이번 장에 등장하는 인물／다음 장 약속 중 이번 장에 "
        "지켜야 할 것／이번 장에 해당하는 연속성 위험／활성 복선 중 **다룰 것**과 **피할 것**(금지 사항만 전달하고 "
        "「作者侧：」 뒤의 작가만 아는 진실은 주 세션에 남김)／장기 제약 중 이번 장에 해당하는 권 단위 상시 금기(상세 개요에는 보통 "
        "‘권 개요 참조, 반복하지 않음’이라고만 적히지만 권 개요는 이 프롬프트에 들어가지 않음)／오랜만에 등장하는 인물의 `추적/인물상태/{이름}.md`를 추가로 읽어야 하는지.")
    parts.append(
        "——— 관련 인물 ———\n"
        f"{SLOT_MARK} 상세 개요의 등장 순서「人物出场顺序」와 장면 참여 범위「镜头准入」에 따른 대사·행동 배분을 바탕으로 "
        "이번 장에 읽을 인물 카드를 나열하세요. 이번 장 속기에 전체 상태를 적은 인물은 다시 나열하지 않아도 됩니다.")
    if not substantive(card_text):
        cards = match_genre_cards(project)
        if cards:
            named = "；".join(f"{'주' if i == 0 else '보조'} 장르 {card}(확신도 {level})" for i, (card, level) in enumerate(cards))
            report.append(f"장르 카드: 작품의 장르 본문 안내 카드가 없습니다. 장르 유형「题材类型」에 따라 {named}을(를) 찾았습니다. 카드를 생성해 저장하고 이후 장에서는 바로 읽으세요")
        else:
            report.append("장르 카드: 작품의 장르 본문 안내 카드가 없고 일치하는 카드도 없습니다. style-genre-modules.md의 "
                          "장르 본문 안내 카드 절과 가장 가까운 장르 절을 읽어 생성한 뒤 저장하세요")
    parts.append("——— 장르 본문 안내 카드(genre_prose_card, 이번 장 관련 항목만) ———\n"
                 f"{SLOT_MARK} 주 장르에서 3~5개, 보조 장르에서 1~2개 항목을 고르세요. 내부 점검에만 사용하고 본문에는 넣지 않습니다")
    parts.append(slot_setting)
    decided, cut = author_decided(project)
    if decided:
        note = (f"\n({AUTHOR_DECIDED_CHARS}자 초과로 잘랐습니다. 나머지는 {project / '설정' / '소재방향.md'}의 작가 확정 사항「作者已定」을 집필 전에 끝까지 읽으세요)"
                if cut else "")
        parts.append("——— 작가가 확정한 사항(작품의 결정이며 작가 기억보다 우선. 상세 개요와 충돌하면 개요를 따르고 전달 요약에 설명) ———\n"
                     + decided + note)
        report.append("작가 확정 사항: 반영함" + ("(길이 초과로 잘랐으므로 집필자는 원문을 끝까지 읽어야 함)" if cut else ""))
    else:
        report.append("작가 확정 사항: 소재 방향 파일에 없거나 비어 있어 넣지 않음")
    lines, missed, skipped, memory_error = query_author_memory(project)
    if memory_error:
        memory_block = (f"{SLOT_MARK} 프롬프트 구성 스크립트가 작가 기억을 조회하지 못했습니다({memory_error}). "
                        "author-memory.md에 따라 prose_style + story_design을 직접 query한 뒤 채우세요. 없으면 ‘없음’으로 적으세요")
        report.append(f"작가 기억: 스크립트 조회 실패 — {memory_error}. 주 세션이 직접 조회하세요. 수동 조회 후에도 빠진 항목이 있다면(한 번이라도 포함한 것은 제외) 장말 보고에서 템플릿의 해당 문구로 알리세요")
    else:
        memory_block = "\n".join(lines) if lines else "없음"
        report.append(f"작가 기억: {len(lines)}개 반영" if lines or missed else "작가 기억: 관련 active 항목 없음")
    if missed:
        # 넣지 못한 항목은 조용히 생략하지 않는다. 작가에게 전할 원문을 만들어 장말 보고에서 템플릿 행 그대로 전달한다.
        shown = "".join(f"「{summary or item_id}」" for item_id, summary in missed[:MISSED_SHOWN])
        more = " 등" if len(missed) > MISSED_SHOWN else ""
        report.append(
            f"작가 기억: 분량 한도로 이번 장에 {len(missed)}개를 넣지 못함({', '.join(i for i, _ in missed)}). 장말 보고에 다음 문구를 그대로 전달하세요 — "
            f"기록한 집필 습관 중 이번 장에 포함하지 못한 항목이 {len(missed)}개입니다: {shown}{more}. "
            "‘작가 기억 정리’를 요청하면 비슷한 항목을 합치거나 잘 쓰지 않는 항목의 우선순위를 낮출 수 있습니다.")
    if skipped and not memory_error:
        named = "；".join(f"{'장르' if k == 'genre' else '절차'}: {', '.join(v)}" for k, v in skipped.items())
        memory_block += (f"\n{SLOT_MARK} 범위가 지정된 작가 기억은 별도로 조회하지 않았습니다({named}). 작품에 해당하는 항목은 "
                         "--genre/--workflow를 지정해 SKILL.md 핵심 방법의 query 명령(--kind prose_style --kind story_design)을 실행한 뒤 이 항목에 추가하세요")
        report.append(f"작가 기억: 범위 한정 항목은 조회하지 않음({named}). 주 세션이 적용 여부를 판단하세요. 추가 조회 후에도 빠진 항목이 있으면(이미 이 항목에 포함된 것은 제외) 장말 보고에 템플릿의 해당 문구로 알리세요")
    parts.append("——— author_preferences(작가 기억. 우선순위가 낮은 경향이며 모든 항목의 적용을 목표로 하지 않음) ———\n" + memory_block)
    parts.append("——— style_resolution ———\n"
                 f"{SLOT_MARK} 이번 요청에서 작가가 명시한 표현 요구와 그에 따라 대체되는 기본 조항을 적으세요(없으면 ‘없음’). "
                 "작품 문체와 작가 기억의 우선순위는 위 항목을 따르며 같은 판단을 AI 문체 제거와 검토에도 전달하세요.")

    parts.append("검사 분담: 집필자는 구성, 내용 반영, 형식을 스스로 점검합니다. 주 세션의 품질 단계는 의미를 살피는 AI 문체 제거와 최종 파일 검사를 담당합니다. 집필자가 전체 문체 제거와 같은 검사 과정을 미리 반복하지 않으며, 사건 지점의 배치·추가 사항 보고·정해진 전달물을 유지합니다.")

    # ---- 고정 블록: agent 정의를 되풀이하지 않고 포인터로 압축 ----
    parts.append(
        "이번 작업은 절대 규칙 1~8과 호출 규약을 따르세요(상세 개요 우선 경계, 본문 형식, 추가 요소의 3단계 분류「新增物三级」, "
        "독서 경험 항목, 전달 첨부물 3종은 기존 정의를 따르며 여기서 반복하지 않습니다).")
    parts.append(
        "분량 목표는 상세 개요를 따르고 계산 기준은 visible_chars_v1입니다. 집필 순서에 따라 전달하세요. "
        "목표는 장 전체의 분량 기준이며 밀도는 스스로 배분합니다. 사건 지점별 할당량으로 나누거나 직접 글자 수를 재지 마세요.")

    if errors:
        return None, errors

    prompt = "\n\n".join(parts) + "\n"

    return prompt, []


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--out", nargs="?", const="", default=None,
                        help="프롬프트 보관 경로. 값 없이 지정하면 이번 장 작업 폴더의 writer_prompt.md에 저장")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    if args.chapter < 1:
        parser.error("--chapter는 0보다 커야 합니다")
    if not project.is_dir():
        sys.stderr.write(f"프로젝트 폴더가 없습니다: {project}\n")
        return 2

    report = []
    prompt, errors = build(project, args.chapter, report)
    if prompt is None:
        sys.stderr.write("구성을 중단했습니다. 데이터를 수정한 뒤 다시 실행하세요(수동 구성으로 대체하지 마세요): \n")
        for item in errors:
            sys.stderr.write(f"  - {item}\n")
        return 2

    # 제목 사전 검사: 본문 디렉터리의 동명 장 존재 여부.
    title = None
    outline_file = find_chapter_file(project / "개요", args.chapter, "상세개요_")
    if outline_file:
        title = extract_title(read_text(outline_file) or "", args.chapter)
    if title:
        clashes = [p.name for p in sorted((project / "본문").glob("*.md"))
                   if p.name.endswith(f"_{title}.md")
                   and not p.name.startswith(f"제{args.chapter:03d}장")]
        report.append(
            f"제목 사전 검사: 《{title}》" + ("기존 장과 제목 중복 → " + "、".join(clashes)
                                       if clashes else "제목 중복 없음"))

    if args.out is not None:
        out = Path(args.out) if args.out else chapter_work_dir(project, args.chapter) / "writer_prompt.md"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with io.open(out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(prompt)
        except OSError as exc:
            sys.stderr.write(f"보관 파일 저장 실패: {out}（{exc}）\n")
            return 2
        report.append(f"보관 파일: {out}")

    sys.stdout.write(prompt)
    sys.stdout.write("\n" + "=" * 60 + "\n")
    sys.stdout.write("위 내용이 프롬프트 본문입니다(빈칸 외에는 변경하지 말고 그대로 복사). 아래 내용은 프롬프트에 넣지 않습니다:\n\n")
    for item in report:
        sys.stdout.write(f"- {item}\n")
    sys.stdout.write(
        f"- 작성할 빈칸: {prompt.count(SLOT_MARK)}개({SLOT_MARK} 검색)\n")
    sys.stdout.write(f"- 프롬프트 틀 길이: {len(prompt)}자\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
