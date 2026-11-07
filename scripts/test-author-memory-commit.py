#!/usr/bin/env python3
"""2계층 작가 기억 트랜잭션 도구의 동작 회귀 검사."""

from __future__ import annotations

import importlib.util
import itertools
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "skills" / "story-long-write" / "scripts" / "author_memory_commit.py"


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def transaction(transaction_id: str, revision: int, operations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "expected_state_revision": revision,
        "operations": operations,
    }


def preference(
    assertion: str,
    quote: str,
    *,
    status: str = "active",
    source: str = "explicit_user",
    scope_level: str = "global",
    scope_value: str | None = None,
    conflicts_with: list[str] | None = None,
    kind: str = "prose_style",
    importance: str = "high",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "scope": {"level": scope_level, "value": scope_value},
        "assertion": assertion,
        "quote": quote,
        "source_ref": "test:conversation",
        "source": source,
        "confidence": "high" if source == "explicit_user" else "medium",
        "importance": importance,
        "status": status,
        "reason": "behavior regression evidence",
        "conflicts_with": conflicts_with or [],
    }


def replacement(assertion: str, quote: str, **scope: Any) -> dict[str, Any]:
    document = preference(assertion, quote, **scope)
    document.pop("status")
    document.pop("conflicts_with")
    return document


def event(event_id: str, operation: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "event_id": event_id, "operation": operation}


def remember(event_id: str, pref: dict[str, Any]) -> dict[str, Any]:
    return event(event_id, {"action": "remember", "preference": pref})


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def memory_dir(root: Path) -> Path:
    return root / ".story" / "작가기억"


def state(root: Path) -> dict[str, Any]:
    return json.loads((memory_dir(root) / "_author-memory-state.json").read_text(encoding="utf-8"))


def save_state(root: Path, document: dict[str, Any]) -> None:
    (memory_dir(root) / "_author-memory-state.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def commit(workspace: Path, input_path: Path, document: dict[str, Any], *extra: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    write_json(input_path, document)
    return run("commit", "--workspace", str(workspace), "--input", str(input_path), *extra, expect=expect)


def record(workspace: Path, input_path: Path, document: dict[str, Any], *extra: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    write_json(input_path, document)
    return run("record", "--workspace", str(workspace), "--input", str(input_path), *extra, expect=expect)


def query(workspace: Path, *args: str, expect: int = 0) -> dict[str, Any]:
    result = run("query", "--workspace", str(workspace), *args, expect=expect)
    if expect:
        return {"stderr": result.stderr}
    document = json.loads(result.stdout)
    assert sum(len((line + "\n").encode("utf-8")) for line in document["lines"]) <= 2048, "交给执行者的 lines 恒 ≤2048 字节"
    return document


def load_tool_module() -> Any:
    """테스트 대상 스크립트를 제자리에서 로드한다. 아래 불변식은 함수 수준에서 전수 검사해야 하며 하위 프로세스는 너무 느리다."""
    spec = importlib.util.spec_from_file_location("author_memory_commit", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_state(generator: random.Random, module: Any, *, book: str | None, books: list[str], genres: list[str], workflows: list[str]) -> dict[str, Any]:
    """store를 합성한다. book=None이면 프로젝트 수준(기존 book 항목 포함), 아니면 해당 책 수준 store다."""
    values = {"book": books, "genre": genres, "workflow": workflows}
    prefix = "BP" if book is not None else "AP"
    items = {}
    for number in range(1, generator.randint(1, 60) + 1):
        if book is None:
            level = generator.choice(["global", "global", "book", "genre", "workflow"])
            value = None if level == "global" else generator.choice(values[level])
        else:
            level, value = "book", book
        items[f"{prefix}{number:03d}"] = {
            "id": f"{prefix}{number:03d}",
            "kind": generator.choice(module.KINDS),
            "scope": {"level": level, "value": value},
            "assertion": "文" * generator.randint(1, 40),
            "status": generator.choice(["active"] * 6 + ["pending", "superseded"]),
            "importance": generator.choice(["low", "medium", "high"]),
            "updated_revision": generator.randint(1, 500),
            "confirmation_count": generator.randint(0, 9),
        }
    document: dict[str, Any] = {"items": items, "state_revision": generator.randint(1, 9999), "journal": []}
    if book is not None:
        document["book"] = book
    return document


def assert_no_false_negatives() -> None:
    """핵심 불변식: 쓰기 확인 응답에 알림이 없음 ⟹ 모든 실제 query에서 항목 누락이 없음.

    이는 쓰기 시 사전 알림 체계의 전제다. 추정과 실제 조회는 별도 코드이므로 scope 분할의 casefold
    병합 누락, JSON 구분자를 제외한 분할 크기 계산, 상태 필터 불일치, 프로젝트 수준의 기존 book
    항목 오계산/오반환 중 하나만 있어도 작가가 확인 응답을 받고 항목을 잃는다. 이 체계가 없애려는
    실패 유형이다. 고정 시드 무작위 저장소 전수 검사는 수동 fixture보다 우회하기 어렵다.
    2계층 store에서 책 디렉터리를 지정한 조회와 지정하지 않은 실제 조회를 각각 전수 검사한다.
    """
    module = load_tool_module()
    books = ["甲", "Lucky", "lucky", "LUCKY", "乙"]
    genres = ["悬疑", "Urban", "urban"]
    workflows = ["장편", "short", "SHORT"]
    generator = random.Random(4290918)

    def real_query_omitted(project_state, book_state, kinds, requested):
        # 기준값은 command_query가 사용하는 순수 함수 경로(merged_query) 자체다. 테스트에서 조회를
        # 다시 구현하면 추정과 ‘실제 조회’가 같은 근거를 공유해 결과 구조의 필드 하나를 빼먹어도 검출하지 못한다.
        return module.merged_query(project_state, book_state, set(kinds), requested)[1]

    warned_libraries = 0
    for _ in range(300):
        project_state = synthetic_state(generator, module, book=None, books=books, genres=genres, workflows=workflows)
        visible_book = generator.choice(books + [None])
        book_state = None if visible_book is None else synthetic_state(generator, module, book=visible_book, books=books, genres=genres, workflows=workflows)
        warnings = module.query_budget_warnings(project_state, book_state)
        warned_libraries += any("最坏查询" in warning for warning in warnings)
        for task, kinds in module.QUERY_COMBOS.items():
            if any(f"「{task}」" in warning for warning in warnings):
                continue
            for genre, workflow in itertools.product(genres + [None], workflows + [None]):
                requested = {"genre": genre, "workflow": workflow}
                for visible in ([book_state] if book_state is not None else []) + [None]:
                    omitted = real_query_omitted(project_state, visible, set(kinds), requested)
                    assert not omitted, (
                        f"写入端没提醒「{task}」，但 query(book_root={'有' if visible else '无'}, genre={genre}, workflow={workflow}) "
                        f"漏了 {omitted}——估算与真实查询不是同一把尺"
                    )
    assert warned_libraries > 20, "随机库里触发提醒的太少，这个属性测试没覆盖到超编区间"


def assert_slice_weight_uses_rendered_lines() -> None:
    """가장 큰 분할은 실행자가 읽는 줄을 기준으로 선택해 채우기와 같은 척도를 사용해야 한다.

    JSON 바이트로 고르면 잘못 선택할 수 있다. scope 값이 길고 단언이 짧은 분할은 JSON으로는
    더 크지만 ‘- 단언(번호)’으로 렌더링하면 더 작다. 그러면 추정은 들어간다고 판단해도 실제 조회는
    초과하여 warnings가 거짓 음성이 된다. 아래 fixture는 두 척도가 다른 분할을 고르게 하며 乙만 초과한다.
    """
    module = load_tool_module()

    def item(number: int, value: str, assertion: str) -> dict[str, Any]:
        return {
            "id": f"AP{number:03d}", "kind": "prose_style",
            "scope": {"level": "genre", "value": value},
            "assertion": assertion, "status": "active",
            "importance": "medium", "updated_revision": 400, "confirmation_count": 1,
        }

    items = {}
    for index in range(12):
        items[f"AP{index + 1:03d}"] = item(index + 1, "甲" * 60, f"甲短{index}")
    for index in range(12):
        items[f"AP{index + 100:03d}"] = item(index + 100, "乙", f"乙偏好{index}：" + "文" * 52)
    heavy_json = [entry for entry in items.values() if entry["scope"]["value"].startswith("甲")]
    heavy_lines = [entry for entry in items.values() if entry["scope"]["value"] == "乙"]

    def json_weight(entries: list[dict[str, Any]]) -> int:
        return sum(len(json.dumps(module.compact_item(entry), ensure_ascii=False).encode("utf-8")) for entry in entries)

    assert json_weight(heavy_json) > json_weight(heavy_lines), "fixture 前提：甲的 JSON 更重（按 JSON 挑会挑甲）"
    assert module.slice_weight(heavy_json) < module.slice_weight(heavy_lines), "fixture 前提：乙渲染出的行更重（必须挑乙）"
    assert not module.fit_items(sorted(heavy_json, key=module.query_sort_key), 700)[1], "甲自己装得下"
    assert module.fit_items(sorted(heavy_lines, key=module.query_sort_key), 700)[1], "乙自己会溢出"
    warnings = module.query_budget_warnings({"items": items, "state_revision": 700, "journal": []}, None)
    assert any("最坏查询" in warning for warning in warnings), "挑错切片会让超编的乙被漏报——切片轻重必须按渲染后的行算"

    # 적고 긴 항목과 많고 짧은 항목 비교: 단언 바이트만 보면 ‘甲’를 고르지만 줄당 고정 비용 14바이트를 포함하면 ‘乙’의 렌더링 결과가 더 크다.
    def entry(number: int, level: str, value: str | None, chars: int) -> dict[str, Any]:
        return {**item(number, value or "", "文" * chars), "scope": {"level": level, "value": value}}

    mixed = {}
    for index in range(12):
        mixed[f"AP{index + 1:03d}"] = entry(index + 1, "global", None, 40)
    mixed["AP013"] = entry(13, "global", None, 6)
    for index in range(3):
        mixed[f"AP{index + 20:03d}"] = entry(index + 20, "genre", "甲", 40)
    for index in range(5):
        mixed[f"AP{index + 30:03d}"] = entry(index + 30, "genre", "乙", 23)
    few_long = [e for e in mixed.values() if e["scope"]["value"] == "甲"]
    many_short = [e for e in mixed.values() if e["scope"]["value"] == "乙"]
    assert sum(len(e["assertion"].encode("utf-8")) for e in few_long) > sum(len(e["assertion"].encode("utf-8")) for e in many_short)
    assert module.slice_weight(few_long) < module.slice_weight(many_short), "fixture 前提：乙渲染后更重"
    library = {"items": mixed, "state_revision": 700, "journal": []}
    assert module.merged_query(library, None, {"prose_style"}, {"genre": "乙", "workflow": None})[1], "真实查询乙会漏条"
    assert any("最坏查询" in w for w in module.query_budget_warnings(library, None)), "每行固定开销必须算进切片轻重"


def assert_omitted_follow_priority_and_lines_fit() -> None:
    """채울 분량은 실행자가 읽는 줄만 측정한다. 누락 항목은 후보 우선순위대로 전부 나열하고 단언의 첫 문장을 붙인다.

    누락 목록은 실행자 프롬프트에 넣지 않으므로 상한을 두지 않는다. 작가는 어떤 항목이 빠졌는지
    알아야 하며 목록을 자르면 뒤의 항목은 영원히 언급되지 않는다.
    """
    module = load_tool_module()
    items = [{
        "id": f"AP{number:03d}",
        "kind": "prose_style",
        "scope": {"level": "global", "value": None},
        "assertion": f"第{number}条" + "文" * 36,
        "importance": "medium",
        "updated_revision": 100 - number,
        "confirmation_count": 1,
    } for number in range(1, 41)]
    items.sort(key=module.query_sort_key)
    result, omitted = module.fit_items([dict(item) for item in items], 500)
    order = {item["id"]: index for index, item in enumerate(items)}
    assert len(omitted) > 20, "fixture 必须漏到旧封顶 20 以上，才能证明漏项不再被截断"
    assert len(result["items"]) + result["omitted"] == len(items), "条目守恒"
    assert result["omitted_ids"] == omitted == sorted(omitted, key=order.__getitem__), "漏项全数列出且按候选优先级排序"
    assert set(result["omitted_summaries"]) == set(omitted), "每个漏项都要有给作者看的首句"
    assert all(len(summary) <= 15 for summary in result["omitted_summaries"].values())
    assert result["lines"] == [f"- {item['assertion']}（{item['id']}）" for item in result["items"]], "lines 就是执行者读到的原文＋编号"
    used = sum(len((line + "\n").encode("utf-8")) for line in result["lines"])
    assert used <= module.QUERY_MAX_BYTES, "lines 必须装在注入预算内"
    first_dropped = next(item for item in items if item["id"] == omitted[0])
    assert used + module.line_bytes(first_dropped) > module.QUERY_MAX_BYTES, "第一个漏项确实装不下，不是被提前放弃"
    # 집필자가 읽는 텍스트 한도는 2048이다. 40자(120바이트) 단언은 15개 들어가지만 이전 JSON 외곽 기준으로는 8개만 들어갔다.
    full = [{**item, "assertion": "文" * 40} for item in items[:15]]
    assert not module.fit_items(full, 500)[1], "按行计量时 15 条 40 字断言必须全部装下"
    assert set(result["omitted_importance"]) == set(omitted), "合并多次查询时要靠重要度重排漏项"
    # 경계: lines가 정확히 2048바이트면 모두 포함하고 1바이트 초과하면 마지막 항목이 누락 목록으로 이동한다.
    exact = full + [{**items[15], "assertion": "文" * 8}]
    assert sum(module.line_bytes(item) for item in exact) == module.QUERY_MAX_BYTES
    assert not module.fit_items(exact, 500)[1], "正好 2048 字节必须全部装下"
    over = full + [{**items[15], "assertion": "文" * 8 + "x"}]
    assert module.fit_items(over, 500)[1] == [items[15]["id"]], "多 1 字节最后一条进漏项"
    # 건너뛰되 중단하지 않는다. 들어가지 않는 긴 항목이 뒤의 짧은 항목을 막지 않는다.
    queue = full[:14] + [{**items[20], "assertion": "长" * 250}, {**items[21], "assertion": "短"}]
    skipped_result, skipped = module.fit_items(queue, 500)
    assert skipped == [items[20]["id"]] and skipped_result["items"][-1]["id"] == items[21]["id"], "装不下的跳过，后面的短条照装"


def assert_single_root_layout(temporary: Path, input_path: Path) -> None:
    """단일 책 배치(책 루트가 작업 공간): 두 store의 기본 저장 위치가 겹치므로 책 store를 书级/ 하위 디렉터리로 옮긴다."""
    # ---- 새 작업 공간: 프로젝트 수준과 책 수준에 하나씩 쓰고 query에 둘 다 나오는지 확인 ----
    fresh = temporary / "单书"
    fresh.mkdir()
    root_args = ("--book-root", str(fresh))
    book_pref = preference("本书对话短句推进", "这本书对话都短一点。", scope_level="book", scope_value="单书")
    first = json.loads(record(fresh, input_path, remember("sr-global", preference("全局：动词承重", "记住：动词承重。")), *root_args).stdout)
    assert first["store"] == "project" and first["receipt"] == "Author Memory Receipt: r1 · AP001"
    booked = json.loads(record(fresh, input_path, remember("sr-book", book_pref), *root_args).stdout)
    assert booked["store"] == "book" and booked["book"] == "单书" and booked["receipt"] == "Author Memory Receipt: r1 · BP001"
    book_dir = memory_dir(fresh) / "书级"
    assert Path(booked["root"]) == book_dir.resolve(), "书级 store 必须落在子目录，不与项目级共用 state"
    assert "book" not in state(fresh) and list(state(fresh)["items"]) == ["AP001"]
    assert json.loads((book_dir / "_author-memory-state.json").read_text(encoding="utf-8"))["book"] == "单书"
    # 책 수준 쓰기 후에도 프로젝트 수준 쓰기와 조회가 정상 동작한다(수정 전에는 항상 state.book 오류).
    second = json.loads(record(fresh, input_path, remember("sr-global-2", preference("全局：段尾不抒情", "记住：段尾不抒情。")), *root_args).stdout)
    assert second["item_ids"] == ["AP002"] and second["warnings"] == []
    assert [item["id"] for item in query(fresh, "--kind", "prose_style", *root_args)["items"]] == ["BP001", "AP002", "AP001"]
    assert [item["id"] for item in query(fresh, "--kind", "prose_style")["items"]] == ["AP002", "AP001"], "不传书根拿不到书级条目"
    forgot = json.loads(record(fresh, input_path, event("sr-forget", {"action": "forget", "item_id": "BP001", "quote": "x", "reason": "x"}), *root_args).stdout)
    assert forgot["store"] == "book" and forgot["item_ids"] == ["BP001"]
    run("check", "--workspace", str(fresh), *root_args)

    # ---- v0.7.10 단일 루트 기존 저장소: query / 책 수준 record / migrate가 모두 가능하며 책 제목은 기존 항목에서 가져옴 ----
    legacy = temporary / "novel-root"  # 디렉터리 이름은 책 제목이 아니다.
    legacy.mkdir()
    legacy_args = ("--book-root", str(legacy))
    record(legacy, input_path, remember("v710-global", preference("全局：少用感叹号", "记住：少用感叹号。")))
    seeded = state(legacy)
    old_item = json.loads(json.dumps(seeded["items"]["AP001"], ensure_ascii=False))
    old_item.update({"id": "AP002", "scope": {"level": "book", "value": "雾港来信"}, "assertion": "雾港来信：章末留钩子", "confirmation_count": 2})
    seeded["items"]["AP002"] = old_item
    seeded["next_item_number"] = 3
    save_state(legacy, seeded)
    run("init", "--workspace", str(legacy))
    assert [item["id"] for item in query(legacy, "--kind", "prose_style", *legacy_args)["items"]] == ["AP001"], "存量 book 条目迁移前不参与查询"
    fresh_book = json.loads(record(legacy, input_path, remember("v710-book", preference(
        "雾港来信：对话短句", "这本书对话短一点。", scope_level="book", scope_value="雾港来信",
    )), *legacy_args).stdout)
    assert fresh_book["book"] == "雾港来信" and fresh_book["item_ids"] == ["BP001"], "单书布局下书名默认取唯一的存量书名，而不是目录名"
    moved = json.loads(run("migrate", "--workspace", str(legacy), *legacy_args).stdout)
    assert moved["migrated"] == [{"from": "AP002", "to": "BP002"}] and moved["book"] == "雾港来信"
    after = state(legacy)
    assert "book" not in after and after["items"]["AP002"]["status"] == "superseded"
    moved_book = json.loads((memory_dir(legacy) / "书级" / "_author-memory-state.json").read_text(encoding="utf-8"))
    assert moved_book["items"]["BP002"]["confirmation_count"] == 2
    assert [item["id"] for item in query(legacy, "--kind", "prose_style", *legacy_args)["items"]] == ["BP002", "BP001", "AP001"]
    assert json.loads(run("migrate", "--workspace", str(legacy), *legacy_args).stdout)["migrated"] == []
    run("check", "--workspace", str(legacy), *legacy_args)

    # ---- 이전 버전이 손상한 작업 공간: 프로젝트 위치에 책 수준 state가 있으면 책 루트를 지정해 실행할 때 자동 복구 ----
    donor = temporary / "供体工作区"
    donor_root = donor / "장편" / "雾港来信"
    donor_root.mkdir(parents=True)
    record(donor, input_path, remember("donor-book", preference(
        "雾港来信：对话短句", "这本书对话短一点。", scope_level="book", scope_value="雾港来信",
    )), "--book-root", str(donor_root))
    broken = temporary / "坏库"
    shutil.copytree(memory_dir(donor_root), memory_dir(broken))
    broken_args = ("--book-root", str(broken))
    assert "--book-root" in query(broken, "--kind", "prose_style", expect=2)["stderr"], "报错要指出怎么自愈"
    before_failure = snapshot(memory_dir(broken))
    record(broken, input_path, remember("broken-global", preference("全局：标题短", "记住：标题短。")), expect=2)
    assert snapshot(memory_dir(broken)) == before_failure
    healed = query(broken, "--kind", "prose_style", *broken_args)
    assert [item["id"] for item in healed["items"]] == ["BP001"] and healed["book_revision"] == 1
    assert "book" not in state(broken) and state(broken)["state_revision"] == 0, "项目级位置补一份空 state"
    relocated = json.loads((memory_dir(broken) / "书级" / "_author-memory-state.json").read_text(encoding="utf-8"))
    assert relocated["book"] == "雾港来信" and list(relocated["items"]) == ["BP001"], "归位不改 state 内容"
    run("check", "--workspace", str(broken), *broken_args)
    assert json.loads(record(broken, input_path, remember("healed-global", preference("全局：标题短", "记住：标题短。"))).stdout)["item_ids"] == ["AP001"]
    booked_again = json.loads(record(broken, input_path, remember("healed-book", preference(
        "雾港来信：少用比喻", "这本书少用比喻。", scope_level="book", scope_value="雾港来信",
    )), *broken_args).stdout)
    assert booked_again["item_ids"] == ["BP002"]
    # 두 위치 모두 책 수준 state라면 추측하지 않고 두 파일을 명시해 오류를 낸다.
    shutil.copy(memory_dir(donor_root) / "_author-memory-state.json", memory_dir(broken) / "_author-memory-state.json")
    assert "无法自动归位" in query(broken, "--kind", "prose_style", *broken_args, expect=2)["stderr"]


def error_text(stderr: str) -> str:
    """오류는 JSON(ensure_ascii)으로 출력해 Windows 경로의 백슬래시가 이스케이프된다. 필드별 원문을 추출한 뒤 비교한다."""
    try:
        return str(json.loads(stderr)["error"])
    except (ValueError, KeyError, TypeError):
        return stderr


def assert_book_dir_is_not_single_root(temporary: Path, input_path: Path) -> None:
    """여러 책이 있는 작업 공간의 책 디렉터리가 --workspace로 잘못 전달됨(책 자체에도 .story/작가기억/가 있음):
    단일 책 배치로 취급해 책 state를 옮기면 안 된다. 오류를 내고 아무것도 쓰지 않으며 올바른 호출은 정상 동작한다."""
    workspace = temporary / "多书工作区"
    book_root = workspace / "장편" / "甲书"
    book_root.mkdir(parents=True)
    book_args = ("--book-root", str(book_root))
    record(workspace, input_path, remember("mb-global", preference("全局：动词承重", "记住：动词承重。")))
    record(workspace, input_path, remember("mb-book", preference(
        "甲书：对话短句", "这本书对话短一点。", scope_level="book", scope_value="甲书",
    )), *book_args)
    before = snapshot(workspace)
    mistaken = ("--workspace", str(book_root), *book_args)
    for command in (("query", "--kind", "prose_style"), ("init",), ("check",), ("migrate",)):
        failed = run(command[0], *mistaken, *command[1:], expect=2)
        assert f"--workspace 应传 {workspace.resolve()}" in error_text(failed.stderr), failed.stderr
    record(book_root, input_path, remember("mb-book-2", preference(
        "甲书：少用比喻", "这本书少用比喻。", scope_level="book", scope_value="甲书",
    )), *book_args, expect=2)
    assert snapshot(workspace) == before, "误传书目录为工作区时不得改动任何文件"
    assert not (memory_dir(book_root) / "书级").exists()
    # --book-root 없이 잘못 호출했을 때 오류가 ‘--book-root {작업 공간}을 붙여 재실행’만 안내해서는 안 된다.
    hint = query(book_root, "--kind", "prose_style", expect=2)["stderr"]
    assert "改传创作工作区根" in hint and "单书布局" in hint, hint
    # 올바른 호출은 계속 정상 동작한다.
    assert [item["id"] for item in query(workspace, "--kind", "prose_style", *book_args)["items"]] == ["BP001", "AP001"]
    run("check", "--workspace", str(workspace), *book_args)

    # 나머지 두 징후: 상위에 .active-book가 있거나 프로젝트 수준 store가 있다(책 디렉터리가 장편/ 단편/ 밖에 있음).
    marked = temporary / "标记工作区"
    (marked / "书稿" / "乙书").mkdir(parents=True)
    (marked / ".active-book").write_text("书稿/乙书\n", encoding="utf-8")
    nested = marked / "书稿" / "乙书"
    assert f"--workspace 应传 {marked.resolve()}" in error_text(run("init", "--workspace", str(nested), "--book-root", str(nested), expect=2).stderr)
    stored = temporary / "有项目级工作区"
    (stored / "丙书").mkdir(parents=True)
    run("init", "--workspace", str(stored))
    nested = stored / "丙书"
    assert f"--workspace 应传 {stored.resolve()}" in error_text(run("init", "--workspace", str(nested), "--book-root", str(nested), expect=2).stderr)
    assert not memory_dir(nested).exists()


def assert_single_root_case_insensitive_path(temporary: Path, input_path: Path) -> None:
    """대소문자를 구분하지 않는 파일 시스템(macOS APFS 기본값)에서 대소문자만 다른 책 루트는 같은 디렉터리다."""
    probe = temporary / "CaseProbe"
    probe.mkdir()
    if not (temporary / "caseprobe").exists():
        return  # 대소문자를 구분하는 파일 시스템에는 이런 별칭이 없다.
    workspace = temporary / "Book"
    workspace.mkdir()
    alias = ("--book-root", str(temporary / "book"))
    record(workspace, input_path, remember("ci-global", preference("全局：动词承重", "记住：动词承重。")), *alias)
    booked = json.loads(record(workspace, input_path, remember("ci-book", preference(
        "本书对话短句", "这本书对话短一点。", scope_level="book", scope_value="Book",
    )), *alias).stdout)
    assert booked["item_ids"] == ["BP001"] and Path(booked["root"]).name == "书级", "只差大小写的书根也按单书布局住子目录"
    assert "book" not in state(workspace), "项目级 state 不得被书级条目占用"
    assert [item["id"] for item in query(workspace, "--kind", "prose_style", *alias)["items"]] == ["BP001", "AP001"]


def assert_other_store_failure_is_nonfatal(temporary: Path, input_path: Path) -> None:
    """쓰기가 저장된 뒤 다른 수준의 store 읽기에 실패하면 알림으로만 처리한다. 오류를 내면 에이전트가 작가에게
    기억하지 못했다고 알리고 다른 event_id로 재시도할 때 중복 항목을 만들게 된다."""
    workspace = temporary / "读取失败工作区"
    book_root = workspace / "장편" / "甲"
    book_root.mkdir(parents=True)
    missing = ("--book-root", str(workspace / "장편" / "不存在"))
    global_event = remember("nf-global", preference("全局：动词承重", "记住：动词承重。"))
    written = json.loads(record(workspace, input_path, global_event, *missing).stdout)
    assert written["ok"] and written["receipt"] == "Author Memory Receipt: r1 · AP001"
    assert any("读取失败" in warning and "book root does not exist" in warning for warning in written["warnings"])
    assert state(workspace)["state_revision"] == 1
    replayed = json.loads(record(workspace, input_path, global_event, *missing).stdout)
    assert replayed["replayed"] is True and len(state(workspace)["items"]) == 1, "重试不得派生重复条目"
    committed = json.loads(commit(workspace, input_path, transaction("nf-tx", 1, [
        {"action": "remember", "preference": preference("全局：段尾不抒情", "记住：段尾不抒情。")},
    ]), *missing).stdout)
    assert committed["item_ids"] == ["AP002"] and any("读取失败" in warning for warning in committed["warnings"])

    record(workspace, input_path, remember("nf-book", preference(
        "甲书：对话短句", "这本书对话短一点。", scope_level="book", scope_value="甲",
    )), "--book-root", str(book_root))
    mismatched = json.loads(record(workspace, input_path, remember("nf-global-2", preference("全局：标题短", "记住：标题短。")),
                                   "--book-root", str(book_root), "--book", "乙").stdout)
    assert mismatched["item_ids"] == ["AP003"] and any("不一致" in warning for warning in mismatched["warnings"])

    (memory_dir(workspace) / "_author-memory-state.json").write_text("{损坏", encoding="utf-8")
    book_written = json.loads(record(workspace, input_path, remember("nf-book-2", preference(
        "甲书：少用比喻", "这本书少用比喻。", scope_level="book", scope_value="甲",
    )), "--book-root", str(book_root)).stdout)
    assert book_written["item_ids"] == ["BP002"] and any("项目级 store 读取失败" in warning for warning in book_written["warnings"])
    assert state(book_root)["state_revision"] == 2


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="author-memory-test-") as temporary:
        workspace = Path(temporary) / "创作工作区"
        workspace.mkdir()
        input_path = Path(temporary) / "transaction.json"
        memory = memory_dir(workspace)

        empty_query = query(workspace, "--kind", "prose_style")
        assert empty_query["items"] == []
        assert not memory.exists(), "a read-only query must not initialize author memory"

        init_result = json.loads(run("init", "--workspace", str(workspace)).stdout)
        assert init_result["revision"] == 0 and init_result["store"] == "project"
        assert {path.name for path in memory.iterdir()} == {
            "_author-memory-state.json",
            "작가프로필.md",
            "확인대기.md",
            "변경기록.md",
        }
        run("check", "--workspace", str(workspace))

        first = transaction(
            "tx-active",
            0,
            [{"action": "remember", "preference": preference(
                "对话尽量短，用动作承接情绪，不用大段解释",
                "以后对话都短一点，情绪放动作里，别让角色长篇解释。",
            )}],
        )
        commit(workspace, input_path, first)
        current = state(workspace)
        assert current["state_revision"] == 1
        assert current["items"]["AP001"]["status"] == "active"
        assert "AP001" in (memory / "작가프로필.md").read_text(encoding="utf-8")

        replay = commit(workspace, input_path, first)
        assert json.loads(replay.stdout)["replayed"] is True
        assert state(workspace)["state_revision"] == 1

        reused = json.loads(json.dumps(first, ensure_ascii=False))
        reused["operations"][0]["preference"]["quote"] = "同一 ID 的不同内容"
        before_failure = snapshot(memory)
        error = commit(workspace, input_path, reused, expect=2)
        assert "different content" in error.stderr
        assert snapshot(memory) == before_failure

        # ---- #436: pending의 출처는 작가 원문 범위의 모호함 하나만 남으며 추론 파이프라인은 더 이상 쓰지 않음 ----
        pending = transaction(
            "tx-pending",
            1,
            [{"action": "remember", "preference": preference(
                "倾向用物件细节替代直接心理说明",
                "心理活动……大概还是落到东西上比较好吧。",
                status="pending",
            )}],
        )
        commit(workspace, input_path, pending)
        assert state(workspace)["items"]["AP002"]["status"] == "pending"
        assert "AP002" in (memory / "확인대기.md").read_text(encoding="utf-8")

        for inferred_source in ("inferred_pattern", "repeated_correction"):
            inferred = transaction(
                f"tx-{inferred_source}",
                2,
                [{"action": "remember", "preference": preference(
                    "推断出的习惯不再写入",
                    "从成稿里看起来如此。",
                    status="pending",
                    source=inferred_source,
                )}],
            )
            before_failure = snapshot(memory)
            error = commit(workspace, input_path, inferred, expect=2)
            assert "已不再写入" in error.stderr and "explicit_user" in error.stderr, "拒写要告诉 agent 该怎么改"
            assert snapshot(memory) == before_failure

        decide = transaction(
            "tx-decide",
            2,
            [{
                "action": "decide",
                "item_id": "AP002",
                "decision": "activate",
                "quote": "对，这也是我的长期习惯。",
                "reason": "author confirmed the candidate",
            }],
        )
        commit(workspace, input_path, decide)
        assert state(workspace)["items"]["AP002"]["status"] == "active"

        # 같은 store 안의 충돌 후보: 새 전역 표현이 AP001과 모순되면 먼저 conflict로 기록한다.
        conflict = transaction(
            "tx-conflict",
            3,
            [{"action": "remember", "preference": preference(
                "允许更长的试探性对话",
                "以后对话慢一点，多试探几轮。",
                status="conflict",
                conflicts_with=["AP001"],
            )}],
        )
        commit(workspace, input_path, conflict)
        assert state(workspace)["items"]["AP003"]["status"] == "conflict"

        illegal_activation = transaction(
            "tx-illegal-conflict-activation",
            4,
            [{
                "action": "decide",
                "item_id": "AP003",
                "decision": "activate",
                "quote": "启用它。",
                "reason": "must still use replace",
            }],
        )
        before_failure = snapshot(memory)
        error = commit(workspace, input_path, illegal_activation, expect=2)
        assert "must be activated with replace" in error.stderr
        assert snapshot(memory) == before_failure

        replace = transaction(
            "tx-replace",
            4,
            [{
                "action": "replace",
                "old_ids": ["AP001", "AP003"],
                "preference": replacement(
                    "对话允许更长的试探，但避免解释设定",
                    "以后可以让对话慢一点，多试探，但还是别拿台词讲设定。",
                ),
            }],
        )
        commit(workspace, input_path, replace)
        current = state(workspace)
        assert current["items"]["AP001"]["status"] == "superseded"
        assert current["items"]["AP003"]["status"] == "superseded"
        assert current["items"]["AP004"]["status"] == "active"
        assert current["items"]["AP001"]["superseded_by"] == "AP004"

        forget = transaction(
            "tx-forget",
            5,
            [{
                "action": "forget",
                "item_id": "AP002",
                "quote": "忘掉这个偏好。",
                "reason": "author withdrew it",
            }],
        )
        commit(workspace, input_path, forget)
        assert state(workspace)["items"]["AP002"]["status"] == "superseded"

        reinforce_preference = replacement(
            "对话允许更长的试探，但避免解释设定",
            "就按慢对话和少解释继续。",
        )
        reinforce_preference["status"] = "active"
        reinforce_preference["conflicts_with"] = []
        reinforce = transaction(
            "tx-reinforce",
            6,
            [{"action": "remember", "preference": reinforce_preference}],
        )
        commit(workspace, input_path, reinforce)
        current = state(workspace)
        assert current["next_item_number"] == 5
        assert current["items"]["AP004"]["confirmation_count"] == 2
        assert len(current["items"]["AP004"]["evidence"]) == 2

        stale = transaction(
            "tx-stale",
            5,
            [{"action": "forget", "item_id": "AP004", "quote": "旧事务", "reason": "stale"}],
        )
        before_failure = snapshot(memory)
        error = commit(workspace, input_path, stale, expect=2)
        assert "stale state revision" in error.stderr
        assert snapshot(memory) == before_failure

        partial_failure = transaction(
            "tx-partial-failure",
            7,
            [
                {"action": "remember", "preference": preference("不应落盘", "这条事务后面会失败。")},
                {"action": "forget", "item_id": "AP999", "quote": "不存在", "reason": "force rollback"},
            ],
        )
        before_failure = snapshot(memory)
        error = commit(workspace, input_path, partial_failure, expect=2)
        assert "unknown item AP999" in error.stderr
        assert snapshot(memory) == before_failure

        unknown_field = transaction(
            "tx-unknown-field",
            7,
            [{"action": "forget", "item_id": "AP004", "quote": "x", "reason": "x", "extra": True}],
        )
        before_failure = snapshot(memory)
        error = commit(workspace, input_path, unknown_field, expect=2)
        assert "unsupported fields" in error.stderr
        assert snapshot(memory) == before_failure

        profile = memory / "작가프로필.md"
        profile.write_text(profile.read_text(encoding="utf-8") + "手工污染\n", encoding="utf-8")
        check_error = run("check", "--workspace", str(workspace), expect=2)
        assert "stale or edited" in check_error.stderr
        replay = commit(workspace, input_path, reinforce)
        assert json.loads(replay.stdout)["replayed"] is True
        run("check", "--workspace", str(workspace))
        assert "手工污染" not in profile.read_text(encoding="utf-8")

        record_event = remember("conversation-message-42", preference(
            "全局偏好用具体物件承载情绪",
            "记住：以后尽量让情绪落到具体物件上。",
        ))
        recorded = json.loads(record(workspace, input_path, record_event).stdout)
        assert recorded["receipt"] == "Author Memory Receipt: r8 · AP005"
        assert recorded["replayed"] is False and recorded["store"] == "project"

        queried = query(workspace, "--kind", "prose_style", "--book", "雾港来信")
        assert [item["id"] for item in queried["items"]] == ["AP005", "AP004"], "同重要度、同 scope 下最近写入的排前"
        assert all(item["id"] not in {"AP001", "AP002", "AP003"} for item in queried["items"])
        assert "book_revision" not in queried

        forget_event = event("conversation-message-43", {
            "action": "forget",
            "item_id": "AP005",
            "quote": "这个全局偏好先忘掉。",
            "reason": "author withdrew the newly recorded preference",
        })
        forgotten = json.loads(record(workspace, input_path, forget_event).stdout)
        assert forgotten["receipt"] == "Author Memory Receipt: r9 · AP005"
        replayed_record = json.loads(record(workspace, input_path, record_event).stdout)
        assert replayed_record["replayed"] is True
        assert replayed_record["applied_revision"] == 8
        assert state(workspace)["items"]["AP005"]["status"] == "superseded"

        final = state(workspace)
        assert final["state_revision"] == 9
        assert set(final["applied_transactions"]) == {
            "tx-active", "tx-pending", "tx-decide", "tx-conflict", "tx-replace", "tx-forget", "tx-reinforce",
            "record:conversation-message-42", "record:conversation-message-43",
        }
        assert all(record["item_ids"] for record in final["applied_transactions"].values())

        # ---- #436: 기존 state의 추론 출처 항목은 계속 읽고 decide/forget할 수 있음 ----
        legacy_source = state(workspace)
        legacy_source["items"]["AP002"]["source"] = "repeated_correction"
        legacy_source["items"]["AP004"]["source"] = "inferred_pattern"
        save_state(workspace, legacy_source)
        run("check", "--workspace", str(workspace))
        assert [item["id"] for item in query(workspace, "--kind", "prose_style")["items"]] == ["AP004"]
        legacy_forget = json.loads(record(workspace, input_path, event("legacy-source-forget", {
            "action": "forget", "item_id": "AP004", "quote": "这条也忘掉。", "reason": "存量推断条目照常可退役",
        })).stdout)
        assert legacy_forget["item_ids"] == ["AP004"]

        # ================= #435: 프로젝트 수준 / 책 수준의 2계층 store =================
        book_root = workspace / "장편" / "雾港来信"
        book_root.mkdir(parents=True)
        book_memory = memory_dir(book_root)
        book_pref = preference(
            "本书对话允许更长的试探，但避免解释设定",
            "这本书可以让对话慢一点，多试探，但还是别拿台词讲设定。",
            scope_level="book", scope_value="雾港来信",
        )

        # book 항목에 --book-root가 없으면 쓰기를 거부하고 경로를 안내한다. 프로젝트 store에는 아무것도 쓰지 않는다.
        before_failure = snapshot(memory)
        routed = record(workspace, input_path, remember("book-without-root", book_pref), expect=2)
        assert "--book-root" in routed.stderr and "随书" in routed.stderr
        assert snapshot(memory) == before_failure
        assert not book_memory.exists()

        # --book-root가 있으면 책 디렉터리에 BP 번호로 저장하고 책 제목 기본값은 디렉터리 이름이다.
        book_recorded = json.loads(record(workspace, input_path, remember("book-with-root", book_pref), "--book-root", str(book_root)).stdout)
        assert book_recorded["receipt"] == "Author Memory Receipt: r1 · BP001"
        assert book_recorded["store"] == "book" and book_recorded["book"] == "雾港来信"
        assert {path.name for path in book_memory.iterdir()} == {"_author-memory-state.json", "작가프로필.md", "확인대기.md", "변경기록.md"}
        book_state = state(book_root)
        assert book_state["book"] == "雾港来信" and book_state["items"]["BP001"]["scope"] == {"level": "book", "value": "雾港来信"}
        assert "BP001" in (book_memory / "작가프로필.md").read_text(encoding="utf-8")
        assert "雾港来信" in (book_memory / "작가프로필.md").read_text(encoding="utf-8"), "书级画像要标明是哪本书"
        assert "BP001" not in (memory / "작가프로필.md").read_text(encoding="utf-8"), "书级条目不进项目级画像"
        assert state(workspace)["state_revision"] == 10, "写书级 store 不推进项目级修订"

        # 다른 책 항목을 이 책 디렉터리에 넣을 수 없다.
        wrong_book = preference("乙书偏好", "乙书原话。", scope_level="book", scope_value="乙")
        error = record(workspace, input_path, remember("wrong-book", wrong_book), "--book-root", str(book_root), expect=2)
        assert "不一致" in error.stderr
        # --book이 store에 기록된 책 제목과 달라도 거부한다.
        error = record(workspace, input_path, remember("wrong-name", book_pref), "--book-root", str(book_root), "--book", "别的书", expect=2)
        assert "不一致" in error.stderr

        # 단언이 같고 scope.value의 대소문자만 다르면 강화하며 두 번째 항목을 만들지 않는다.
        for value in ("Urban", "urban"):
            genre_result = json.loads(record(workspace, input_path, remember(f"genre-{value}", preference(
                "都市文多用短句", "都市文短句。", scope_level="genre", scope_value=value,
            ))).stdout)
        assert genre_result["item_ids"] == ["AP006"] and "强化" in genre_result["summaries"][0], "scope.value 按 casefold 归并"
        assert state(workspace)["items"]["AP006"]["confirmation_count"] == 2
        record(workspace, input_path, event("genre-forget", {"action": "forget", "item_id": "AP006", "quote": "x", "reason": "x"}))
        # 전역 항목은 --book-root가 있어도 프로젝트 수준으로 보낸다.
        global_via_book = json.loads(record(workspace, input_path, remember("global-with-book-root", preference(
            "段尾不落抒情句", "记住：段尾别落抒情句。",
        )), "--book-root", str(book_root)).stdout)
        assert global_via_book["store"] == "project" and global_via_book["item_ids"] == ["AP007"]

        # 통합 조회: 프로젝트 수준 + 책 수준. 중요도가 같으면 이 책의 예외를 앞에 둔다.
        merged = query(workspace, "--kind", "prose_style", "--book-root", str(book_root))
        assert [item["id"] for item in merged["items"]] == ["BP001", "AP007"]
        assert merged["book_revision"] == 1 and merged["revision"] == 14
        # 책 디렉터리를 주지 않으면 책 수준 항목을 얻을 수 없다. 책 store는 책 디렉터리에서만 읽는다.
        assert [item["id"] for item in query(workspace, "--kind", "prose_style")["items"]] == ["AP007"]
        # 책 디렉터리는 있지만 책 store가 아직 없으면 정상적으로 프로젝트 항목만 반환한다.
        other_root = workspace / "장편" / "无记忆之书"
        other_root.mkdir()
        assert [item["id"] for item in query(workspace, "--kind", "prose_style", "--book-root", str(other_root))["items"]] == ["AP007"]
        assert not memory_dir(other_root).exists(), "只读查询不得初始化书级 store"

        # 트랜잭션 하나는 store 하나만 쓴다. replace와 conflicts_with는 store를 넘을 수 없다.
        run("init", "--workspace", str(workspace), "--book-root", str(book_root))
        mixed = transaction("tx-mixed-stores", 1, [
            {"action": "forget", "item_id": "BP001", "quote": "x", "reason": "x"},
            {"action": "forget", "item_id": "AP007", "quote": "x", "reason": "x"},
        ])
        error = commit(workspace, input_path, mixed, "--book-root", str(book_root), expect=2)
        assert "只能写一个 store" in error.stderr
        cross_replace = transaction("tx-cross-replace", 1, [{
            "action": "replace", "old_ids": ["AP007"],
            "preference": replacement("本书段尾可以落抒情句", "这本书段尾可以抒情。", scope_level="book", scope_value="雾港来信"),
        }])
        error = commit(workspace, input_path, cross_replace, "--book-root", str(book_root), expect=2)
        assert "不能跨 store" in error.stderr and "forget" in error.stderr
        cross_conflict = remember("cross-conflict", preference(
            "本书允许段尾抒情", "这本书例外。", status="conflict", scope_level="book", scope_value="雾港来信", conflicts_with=["AP007"],
        ))
        error = record(workspace, input_path, cross_conflict, "--book-root", str(book_root), expect=2)
        assert "同一 store" in error.stderr and "本书例外" in error.stderr
        assert state(book_root)["state_revision"] == 1 and state(workspace)["state_revision"] == 14

        # decide / forget은 번호 접두사로 분기한다. BP에 --book-root가 없으면 거부하고 있으면 책 수준으로 보낸다.
        error = record(workspace, input_path, event("bp-forget-no-root", {
            "action": "forget", "item_id": "BP001", "quote": "x", "reason": "x",
        }), expect=2)
        assert "--book-root" in error.stderr
        book_commit = json.loads(commit(workspace, input_path, transaction("tx-book-replace", 1, [{
            "action": "replace", "old_ids": ["BP001"],
            "preference": replacement("本书对话可以慢，但不拿台词讲设定", "改一下说法。", scope_level="book", scope_value="雾港来信"),
        }]), "--book-root", str(book_root)).stdout)
        assert book_commit["store"] == "book" and book_commit["item_ids"] == ["BP001", "BP002"]
        assert state(book_root)["items"]["BP001"]["superseded_by"] == "BP002"

        # check는 두 수준을 함께 확인하며 책 프로필을 수동 수정한 경우도 찾아낸다.
        checked = json.loads(run("check", "--workspace", str(workspace), "--book-root", str(book_root)).stdout)
        assert checked["project"]["revision"] == 14 and checked["book"]["revision"] == 2 and checked["book"]["name"] == "雾港来信"
        book_profile = book_memory / "작가프로필.md"
        book_profile.write_text(book_profile.read_text(encoding="utf-8") + "手工污染\n", encoding="utf-8")
        assert "stale or edited" in run("check", "--workspace", str(workspace), "--book-root", str(book_root), expect=2).stderr
        assert json.loads(commit(workspace, input_path, transaction("tx-book-replace", 1, [{
            "action": "replace", "old_ids": ["BP001"],
            "preference": replacement("本书对话可以慢，但不拿台词讲设定", "改一下说法。", scope_level="book", scope_value="雾港来信"),
        }]), "--book-root", str(book_root)).stdout)["replayed"] is True, "幂等重放也要重写快照"
        assert len(state(book_root)["items"]) == 2, "重放不得派生条目"
        run("check", "--workspace", str(workspace), "--book-root", str(book_root))

        # 책 디렉터리 이름이 바뀌어도 책 제목은 state를 기준으로 하므로 영향을 받지 않는다.
        renamed_root = workspace / "장편" / "雾港来信（改名）"
        book_root.rename(renamed_root)
        renamed = query(workspace, "--kind", "prose_style", "--book-root", str(renamed_root))
        assert [item["id"] for item in renamed["items"]] == ["BP002", "AP007"]
        renamed_root.rename(book_root)

        # ---- 기존 데이터 이전: 업그레이드 전 프로젝트 store에 쓴 book 항목은 조회/추정에서 제외하고 migrate로 책 디렉터리에 옮긴 뒤 다시 포함 ----
        legacy_workspace = Path(temporary) / "存量工作区"
        legacy_workspace.mkdir()
        legacy_root = legacy_workspace / "장편" / "甲"
        legacy_root.mkdir(parents=True)
        record(legacy_workspace, input_path, remember("seed-global", preference("全局：动词承重", "记住：动词承重。")))
        record(legacy_workspace, input_path, remember("seed-pending", preference("甲书候选：章末留钩子", "这本书章末……留个钩子吧。", status="pending")))
        legacy_state = state(legacy_workspace)
        # state를 직접 바꿔 업그레이드 전 저장소를 재현한다. AP002는 甲 책 active, AP003은 甲 책 conflict(충돌 상대는 전역 AP001),
        # AP004는 甲 책 pending, AP005는 乙 책 active다.
        template = legacy_state["items"]["AP001"]

        def legacy_item(number: int, value: str, status: str, assertion: str, **fields: Any) -> dict[str, Any]:
            item = json.loads(json.dumps(template, ensure_ascii=False))
            item.update({"id": f"AP{number:03d}", "scope": {"level": "book", "value": value}, "status": status, "assertion": assertion, "confirmation_count": 3, "evidence": [{"quote": f"原话 {number}", "source_ref": None}, {"quote": f"再说一次 {number}", "source_ref": None}]})
            item.update(fields)
            return item

        legacy_state["items"]["AP002"] = legacy_item(2, "甲", "active", "甲书：对话短句推进")
        legacy_state["items"]["AP003"] = legacy_item(3, "甲", "conflict", "甲书：名词承重不用动词", conflicts_with=["AP001"])
        legacy_state["items"]["AP004"] = legacy_item(4, "甲", "pending", "甲书：章末留钩子")
        legacy_state["items"]["AP005"] = legacy_item(5, "乙", "active", "乙书：多用长句")
        legacy_state["next_item_number"] = 6
        save_state(legacy_workspace, legacy_state)
        run("init", "--workspace", str(legacy_workspace))  # state를 직접 바꾼 뒤 파생 뷰를 재생성한다.
        run("check", "--workspace", str(legacy_workspace))

        assert [item["id"] for item in query(legacy_workspace, "--kind", "prose_style")["items"]] == ["AP001"], "存量 book 条目不参与查询"
        with_root = query(legacy_workspace, "--kind", "prose_style", "--book-root", str(legacy_root))
        assert [item["id"] for item in with_root["items"]] == ["AP001"] and "book_revision" not in with_root
        seeded_write = json.loads(record(legacy_workspace, input_path, remember("seed-global-2", preference("全局：段尾不抒情", "记住：段尾不抒情。"))).stdout)
        assert seeded_write["warnings"] == [], "存量 book 条目不参与估算"

        migrate_error = run("migrate", "--workspace", str(legacy_workspace), expect=2)
        assert "--book-root" in migrate_error.stderr
        migrated = json.loads(run("migrate", "--workspace", str(legacy_workspace), "--book-root", str(legacy_root)).stdout)
        assert migrated["migrated"] == [{"from": "AP002", "to": "BP001"}, {"from": "AP003", "to": "BP002"}, {"from": "AP004", "to": "BP003"}]
        assert migrated["book"] == "甲" and migrated["revision"] == 3
        moved = state(legacy_root)
        assert moved["book"] == "甲" and moved["state_revision"] == 3, "书级每个源条目一笔事务"
        assert set(moved["applied_transactions"]) == {"migrate:AP002", "migrate:AP003", "migrate:AP004"}
        assert moved["items"]["BP001"]["status"] == "active" and moved["items"]["BP001"]["confirmation_count"] == 3
        assert len(moved["items"]["BP001"]["evidence"]) == 2, "证据随条目搬家"
        assert moved["items"]["BP002"]["status"] == "pending" and moved["items"]["BP002"]["conflicts_with"] == [], "与全局条目的冲突关系不再成立，退回待确认"
        assert moved["items"]["BP003"]["status"] == "pending"
        after = state(legacy_workspace)
        assert all(after["items"][item_id]["status"] == "superseded" for item_id in ("AP002", "AP003", "AP004"))
        assert "BP001" in after["items"]["AP002"]["reason"] and after["items"]["AP002"]["superseded_by"] is None
        assert after["items"]["AP005"]["status"] == "active", "别的书的存量条目不动"
        assert any("迁出 AP002 → BP001" in summary for summary in after["journal"][-1]["summaries"])
        run("check", "--workspace", str(legacy_workspace), "--book-root", str(legacy_root))
        after_query = query(legacy_workspace, "--kind", "prose_style", "--book-root", str(legacy_root))
        assert [item["id"] for item in after_query["items"]] == ["BP001", "AP006", "AP001"], "迁移后书级条目回来；全局条目按最近更新排"
        again = json.loads(run("migrate", "--workspace", str(legacy_workspace), "--book-root", str(legacy_root)).stdout)
        assert again["migrated"] == [] and again["warnings"] == [] and again["revision"] == 3, "没有存量时输出形状不变"
        assert state(legacy_workspace)["state_revision"] == after["state_revision"], "重复 migrate 项目级零写入"
        book_profile_a = memory_dir(legacy_root) / "작가프로필.md"
        book_profile_a.write_text(book_profile_a.read_text(encoding="utf-8") + "手工污染\n", encoding="utf-8")
        run("migrate", "--workspace", str(legacy_workspace), "--book-root", str(legacy_root))
        assert "手工污染" not in book_profile_a.read_text(encoding="utf-8"), "重跑 migrate 也要修复派生视图"
        # 프로젝트 store가 없는 작업 공간에서 migrate는 오류가 아닌 무작업이다.
        fresh = Path(temporary) / "无项目级"
        (fresh / "장편" / "书").mkdir(parents=True)
        assert json.loads(run("migrate", "--workspace", str(fresh), "--book-root", str(fresh / "장편" / "书")).stdout)["migrated"] == []
        assert not memory_dir(fresh / "장편" / "书").exists()

        # 도중 실패 후 재실행: 책 store만 썼다면 프로젝트 store만 보완하고 BP를 중복 생성하지 않는다.
        # 실패 구간에서 작가가 기존 항목을 decide할 수 있으므로 재실행이 요약 변화 때문에 막히면 안 된다.
        b_root = legacy_workspace / "장편" / "乙"
        b_root.mkdir()
        seeded = state(legacy_workspace)  # state를 직접 바꿔 업그레이드 전에 저장한 乙 책 항목을 재현한다.
        seeded["items"]["AP007"] = legacy_item(7, "乙", "pending", "乙书补充：章末留白")
        seeded["items"]["AP008"] = legacy_item(8, "乙", "active", "乙书补充：少用感叹号")
        seeded["next_item_number"] = 9
        save_state(legacy_workspace, seeded)
        run("init", "--workspace", str(legacy_workspace))
        before_project = state(legacy_workspace)
        run("migrate", "--workspace", str(legacy_workspace), "--book-root", str(b_root))
        assert [item["id"] for item in state(b_root)["items"].values()] == ["BP001", "BP002", "BP003"]
        # 프로젝트 store를 이전 전으로 롤백해 두 번째 쓰기 실패를 재현한다. 그 사이 작가는 AP007을 확인하고 AP008을 폐기했다.
        save_state(legacy_workspace, before_project)
        run("init", "--workspace", str(legacy_workspace))
        record(legacy_workspace, input_path, event("window-decide", {"action": "decide", "item_id": "AP007", "decision": "activate", "quote": "对。", "reason": "窗口内确认"}))
        resumed = json.loads(run("migrate", "--workspace", str(legacy_workspace), "--book-root", str(b_root)).stdout)
        assert resumed["migrated"] == [{"from": "AP005", "to": "BP001"}, {"from": "AP007", "to": "BP002"}, {"from": "AP008", "to": "BP003"}], "重跑复用已建编号，不重复建条，也不因源条目状态变化锁死"
        b_state = state(b_root)
        assert len(b_state["items"]) == 3 and b_state["state_revision"] == 3, "书级零新写入"
        assert b_state["items"]["BP002"]["status"] == "pending", "复用编号的副本保持迁移时的状态，窗口内的确认由作者对副本重做"
        assert all(state(legacy_workspace)["items"][item_id]["status"] == "superseded" for item_id in ("AP005", "AP007", "AP008"))
        run("check", "--workspace", str(legacy_workspace), "--book-root", str(b_root))
        assert [item["id"] for item in query(legacy_workspace, "--kind", "prose_style", "--book-root", str(b_root))["items"]][:2] == ["BP003", "BP001"]

        # ---- 2계층 store에서의 예산 알림 기준 ----
        auto_workspace = Path(temporary) / "自动初始化工作区"
        auto_workspace.mkdir()
        auto_result = json.loads(record(auto_workspace, input_path, remember("first-explicit-memory", preference("偏好短标题", "记住：标题短一点。"))).stdout)
        assert auto_result["receipt"] == "Author Memory Receipt: r1 · AP001"
        assert state(auto_workspace)["state_revision"] == 1
        # 예산 안의 묶음은 정상 저장하며 확인 응답에 알림을 붙이지 않는다.
        fitting = transaction(
            "tx-query-budget-fit",
            1,
            [
                {
                    "action": "remember",
                    "preference": preference(
                        f"短偏好 {index}：动词承重，不用被动式。",
                        f"第 {index} 条短偏好。",
                    ),
                }
                for index in range(2)
            ] + [{
                "action": "remember",
                "preference": preference(
                    "悬疑故事优先让线索改变人物关系",
                    "悬疑里我更看重线索对关系的改变。",
                    scope_level="genre",
                    scope_value="悬疑",
                    kind="story_design",
                ),
            }],
        )
        assert json.loads(commit(auto_workspace, input_path, fitting).stdout)["warnings"] == []
        assert query(auto_workspace, "--kind", "prose_style")["omitted_ids"] == []
        matching_design = query(auto_workspace, "--kind", "story_design", "--genre", "悬疑")
        assert [item["id"] for item in matching_design["items"]] == ["AP004"]
        assert query(auto_workspace, "--kind", "story_design", "--genre", "甜宠")["items"] == []
        run("check", "--workspace", str(auto_workspace))

        # 단언은 한 문장으로 제한한다. 새 항목이 120바이트를 넘으면 즉시 거부한다(기존 항목 강화는 이 제한에서 제외, 아래 사례 참고).
        long_assertion = transaction(
            "tx-assertion-too-long",
            state(auto_workspace)["state_revision"],
            [{"action": "remember", "preference": preference("长" * 45, "太长的断言应当拆条。")}],
        )
        error = commit(auto_workspace, input_path, long_assertion, expect=2)
        assert "超出 120 字节上限" in error.stderr
        assert "强化" in error.stderr, "报错要告诉 agent 重申老条目该怎么走"

        # 알림 방식: ‘본문 초안/이어쓰기’ 조합을 예산 초과로 만드는 쓰기도 성공하며 확인 응답에 warnings를 넣는다.
        before_revision = state(auto_workspace)["state_revision"]
        crowding = transaction(
            "tx-query-budget-crowding",
            before_revision,
            [
                {
                    "action": "remember",
                    "preference": preference(
                        f"长偏好{index}：先给动作再给判断，段尾不落抒情句，比喻每场最多留一个。",
                        f"第 {index} 条用于撑满注入预算。",
                    ),
                }
                for index in range(24)
            ],
        )
        crowded = json.loads(commit(auto_workspace, input_path, crowding).stdout)
        assert crowded["warnings"], "超编写入必须携带预算提醒"
        assert any("整理作者记忆" in warning for warning in crowded["warnings"])
        assert state(auto_workspace)["state_revision"] == before_revision + 1

        # 감량 정리: 예산 초과 작업 공간에서도 항목별 삭제는 성공해야 한다(쓰기 거부 방식이면 여기서 교착된다).
        cleaned = json.loads(record(auto_workspace, input_path, event("cleanup-step-1", {
            "action": "forget",
            "item_id": crowded["item_ids"][0],
            "quote": "这条先退役。",
            "reason": "整理：逐条退役",
        })).stdout)
        assert cleaned["replayed"] is False
        assert cleaned["warnings"], "仍超编时提醒应继续存在，但写入不失败"

        # kind 없는 조회는 즉시 오류를 내며 더 이상 모든 유형을 기본 반환하지 않는다.
        assert "--kind" in query(auto_workspace, expect=2)["stderr"]

        # 조회 정렬은 최신성을 포함한다. 중요도가 같으면 최근 항목이 앞에 오고 오래된 항목이 제외된다.
        recency_query = query(auto_workspace, "--kind", "prose_style")
        assert len(recency_query["items"]) > 0
        assert recency_query["items"][0]["id"] == crowded["item_ids"][1], "最近写入应排最前（首条已退役）"
        assert recency_query["omitted_ids"], "超编查询必须报漏项"
        assert recency_query["omitted"] == len(recency_query["omitted_ids"])

        # 책 수준 정확한 계산: 책 항목을 쓸 때 알림은 ‘전역 + 이 책 store’로 계산하며 다른 책을 섞지 않는다.
        # 프로젝트 항목을 쓸 때 --book-root가 주어져도 이 책을 함께 계산한다.
        ruler_workspace = Path(temporary) / "两书工作区"
        ruler_workspace.mkdir()
        root_a = ruler_workspace / "장편" / "甲"
        root_b = ruler_workspace / "장편" / "乙"
        root_a.mkdir(parents=True)
        root_b.mkdir(parents=True)
        for index in range(3):
            record(ruler_workspace, input_path, remember(f"book-a-{index}", preference(
                f"甲书短偏好{index}", "甲书原话交代来龙去脉，" * 22, scope_level="book", scope_value="甲",
            )), "--book-root", str(root_a))
        for index in range(4):
            record(ruler_workspace, input_path, remember(f"global-{index}", preference(
                f"全局偏好{index}：动词承重不用被动式，段尾不落抒情句，比喻每场只留一个。",
                f"第 {index} 条全局偏好。",
            )))
        last_b = None
        for index in range(16):
            last_b = json.loads(record(ruler_workspace, input_path, remember(f"book-b-{index}", preference(
                f"乙书偏好{index}：情绪落在具体物件上，对话短句推进，收尾用动作不用感叹。",
                f"第 {index} 条乙书偏好。",
                scope_level="book", scope_value="乙",
            )), "--book-root", str(root_b)).stdout)
        assert any("正文初稿" in warning for warning in last_b["warnings"]), "书乙自身超编必须被点名"
        book_a = query(ruler_workspace, "--kind", "prose_style", "--kind", "story_design", "--book-root", str(root_a))
        assert book_a["omitted_ids"] == [] and {item["id"][:2] for item in book_a["items"]} == {"AP", "BP"}, "不同书的记忆不得加在一起算"
        book_b = query(ruler_workspace, "--kind", "prose_style", "--kind", "story_design", "--book-root", str(root_b))
        assert book_b["omitted_ids"], "书乙自身切片超编必须体现在查询漏项"
        # 프로젝트 항목 쓰기: 책 디렉터리가 없으면 책 store를 볼 수 없어 알리지 않으며 乙를 지정하면 乙를 포함한다.
        blind = json.loads(record(ruler_workspace, input_path, remember("global-blind", preference("全局：标题短", "记住：标题短。"))).stdout)
        assert blind["warnings"] == [], "看不到书级 store 时不该凭空报警"
        sighted = json.loads(record(ruler_workspace, input_path, remember("global-sighted", preference("全局：少用感叹号", "记住：少用感叹号。")), "--book-root", str(root_b)).stdout)
        assert sighted["store"] == "project" and any("正文初稿" in warning for warning in sighted["warnings"]), "传了 --book-root 的项目级写入要把这本书算进提醒"

        # 극단적 예산 초과(state를 직접 바꿔 기존 긴 단언 재현): 모든 누락 항목과 첫 문장을 나열한다. 주입 줄은 항상 ≤2048이며
        # 전체 묶음을 오류 처리하지 않는다. 768B 기존 단언도 검증을 통과할 수 있다.
        flood = state(ruler_workspace)
        base_item = json.loads(json.dumps(flood["items"]["AP001"], ensure_ascii=False))
        for number in range(100, 140):
            clone = json.loads(json.dumps(base_item, ensure_ascii=False))
            clone["id"] = f"AP{number}"
            clone["assertion"] = f"直改状态的超长断言{number}：" + "长" * 200
            clone["scope"] = {"level": "global", "value": None}
            flood["items"][f"AP{number}"] = clone
        flood["next_item_number"] = 200
        save_state(ruler_workspace, flood)
        flooded_document = query(ruler_workspace, "--kind", "prose_style")
        assert flooded_document["items"], "跳过不中断——装得下的条目仍应返回"
        assert flooded_document["omitted"] > 20
        assert len(flooded_document["omitted_ids"]) == flooded_document["omitted"], "漏项清单不进 prompt，不再封顶"
        assert set(flooded_document["omitted_summaries"]) == set(flooded_document["omitted_ids"])
        assert sum(len((line + "\n").encode("utf-8")) for line in flooded_document["lines"]) <= 2048

        # ---- 중요도 우선: high 전역 원칙이 low 책별 사소한 항목 때문에 주입 예산에서 밀려나면 안 됨(책 항목은 책 store에 있음) ----
        priority_workspace = Path(temporary) / "重要度工作区"
        priority_root = priority_workspace / "장편" / "雾港来信"
        priority_root.mkdir(parents=True)
        for index, rule in enumerate((
            "铁律一：绝不写第二人称叙述，任何情况都不破例。",
            "铁律二：未成年角色绝不出现性描写，平台红线。",
        )):
            record(priority_workspace, input_path, remember(f"rule-{index}", preference(rule, f"作者原话：{rule}", importance="high")))
        crowd_out = None
        for index in range(24):
            crowd_out = json.loads(record(priority_workspace, input_path, remember(f"trivia-{index}", preference(
                f"本书临时{index}：这一卷多用短句，场景切换不加过渡段落。",
                f"第 {index} 条本卷临时偏好。",
                scope_level="book", scope_value="雾港来信", importance="low",
            )), "--book-root", str(priority_root)).stdout)
        priority_query = query(priority_workspace, "--kind", "prose_style", "--kind", "story_design", "--book-root", str(priority_root))
        kept_ids = [item["id"] for item in priority_query["items"]]
        assert priority_query["omitted_ids"], "撑满预算后必须有漏项，否则这个用例没在测东西"
        assert "AP001" in kept_ids and "AP002" in kept_ids, "high 全局铁律不得被 low 本书条目挤掉"
        assert all(item_id.startswith("BP") for item_id in priority_query["omitted_ids"]), "先丢的必须是重要度低的条目"
        assert crowd_out["warnings"], "超编写入必须携带提醒"
        assert any("「" in warning for warning in crowd_out["warnings"]), "提醒要带断言首句，只给编号作者无从判断"

        # ---- 주입 데이터는 계약: 실행자는 lines(단언 원문 + 번호)만 읽고 items는 주 세션 판단용 네 필드만 제공 ----
        assert all(set(item) == {"id", "kind", "scope", "assertion"} for item in priority_query["items"]), \
            "query items 只带 id/kind/scope/assertion；reason、evidence 等一律不出 store"
        assert priority_query["lines"] == [f"- {item['assertion']}（{item['id']}）" for item in priority_query["items"]], \
            "lines 与 items 一一对应，就是交给执行者的原文"

        # ---- 작가프로필.md는 importance를 표시해야 함: 작가 기억 정리에서 유지/삭제 판단의 근거 ----
        priority_profile = (memory_dir(priority_workspace) / "작가프로필.md").read_text(encoding="utf-8")
        assert "重要 high" in priority_profile, "画像要显示重要度，否则整理时无从判断该退役哪条"
        assert "重要 low" in (memory_dir(priority_root) / "작가프로필.md").read_text(encoding="utf-8")

        # ---- 기존 긴 단언: 그대로 재확인하면 강화하며 새 상한으로 거부하거나 중복 항목을 만들지 않음 ----
        legacy_long_workspace = Path(temporary) / "存量长断言工作区"
        legacy_long_workspace.mkdir()
        legacy_assertion = "存量长断言：" + "以后写对话时别用破折号表示打断改用省略号但叙述里的插入语破折号保留" * 2
        assert len(legacy_assertion.encode("utf-8")) > 120
        record(legacy_long_workspace, input_path, remember("legacy-seed", preference("占位短断言。", "原话。")))
        legacy_long_state = state(legacy_long_workspace)
        legacy_long_state["items"]["AP001"]["assertion"] = legacy_assertion
        save_state(legacy_long_workspace, legacy_long_state)
        reinforced = json.loads(record(legacy_long_workspace, input_path, remember("legacy-restate", preference(legacy_assertion, "作者又说了一遍。"))).stdout)
        assert reinforced["item_ids"] == ["AP001"], "原样重申存量长断言必须强化原条目，不得新建"
        after_legacy = state(legacy_long_workspace)
        assert len(after_legacy["items"]) == 1, "强化路径不得派生重复条目"
        assert after_legacy["items"]["AP001"]["confirmation_count"] == 2
        run("check", "--workspace", str(legacy_long_workspace))
        new_long = record(legacy_long_workspace, input_path, remember("legacy-new-long", preference(legacy_assertion + "再补一句。", "新的长断言。")), expect=2)
        assert "超出 120 字节上限" in new_long.stderr, "新建条目仍受一句话上限约束"

        assert_single_root_layout(Path(temporary), input_path)
        assert_book_dir_is_not_single_root(Path(temporary), input_path)
        assert_single_root_case_insensitive_path(Path(temporary), input_path)
        assert_other_store_failure_is_nonfatal(Path(temporary), input_path)
        assert_no_false_negatives()
        assert_omitted_follow_priority_and_lines_fit()
        assert_slice_weight_uses_rendered_lines()

    # 표현을 고정하지 않고 프롬프트와 런타임 CLI / 슬롯의 연결 구간만 앵커로 삼는다.
    injection_contracts = {
        # 한 장 집필의 슬롯 설명은 집필자에게 전달할 때만 쓰도록 agent-calls.md로 이동했다(v0.8.2).
        REPO / "skills/story-long-write/references/agent-calls.md": (
            "`author_preferences`",
        ),
        # 조회한 선호가 하위 에이전트 프롬프트 슬롯에 들어가야 한다. 그렇지 않으면 query는 실행되어도 결과가 집필자에게 도달하지 않는다.
        # 단편 집필자 배정 프롬프트도 전달 시점에만 쓰도록 agent-calls.md로 이동했다(v0.8.2).
        REPO / "skills/story-short-write/references/agent-calls.md": (
            "作者偏好 query",
            "\n作者偏好：{",
        ),
        # AI 문체 제거를 집필자에게 맡기는 프롬프트도 전달 시점에만 쓰도록 agent-calls.md로 이동했다(v0.8.3).
        REPO / "skills/story-deslop/references/agent-calls.md": (
            "\n作者偏好：{",
        ),
        REPO / "skills/story-short-write/SKILL.md": (
            "query --workspace {工作区} --book-root {项目目录} --kind prose_style --kind story_design",
            "没装下的",
        ),
        # 포함하지 못한 습관은 원문으로 작가에게 알려야 한다(dsh#61). 조립 스크립트가 문장을 만들고 단일 장/일일 배치 종료 보고 템플릿이 각각 한 줄로 받는다.
        REPO / "skills/story-long-write/references/workflow-chapter.md": ("习惯没带上",),
        REPO / "skills/story-long-write/references/workflow-daily.md": ("习惯没带上",),
    }
    for path, required_fragments in injection_contracts.items():
        # 한 줄 이스케이프 프롬프트와 여러 줄 코드 블록 프롬프트는 실제로 같은 필드를 전달해야 한다.
        content = path.read_text(encoding="utf-8").replace("\\n", "\n")
        for fragment in required_fragments:
            equivalents = {"作者偏好 query": ("작가 선호 query",), "没装下的": ("담지 못한 항목",),
                           "习惯没带上": ("반영 못 한 습관은 작가 원문으로 안내", "반영하지 못한 습관은 작가의 원문 표현으로 한 번에 안내")}
            assert fragment in content or any(value in content for value in equivalents.get(fragment, ())), f"missing author-memory injection contract in {path}: {fragment}"
    # 기억 규약과 도구는 집필 스킬만 소유하고 다른 스킬은 호출자를 통해 결정 결과를 받는다.
    owners = ("story-long-write", "story-short-write")
    expected_protocols = {REPO / "skills" / owner / "references" / name
                          for owner in owners
                          for name in ("author-memory.md", "author-memory-maintenance.md")}
    assert set((REPO / "skills").glob("*/references/author-memory*.md")) == expected_protocols
    assert set((REPO / "skills").glob("*/scripts/author_memory_commit.py")) == {
        REPO / "skills" / owner / "scripts/author_memory_commit.py" for owner in owners}
    # #436: 집필 진입점과 규약은 더 이상 추론 결과 저장을 유도하지 않는다.
    for path in sorted(expected_protocols) + [REPO / "skills" / owner / "SKILL.md" for owner in owners]:
        content = path.read_text(encoding="utf-8")
        assert "repeated_correction" not in content and "inferred_pattern" not in content, f"{path} 仍在引导推断写入"
    # v0.8.2: 작가의 작업 시점별로 규약을 분리했다. 선호 하나를 기록할 때는 author-memory.md만 읽고 드문 작업 규칙은 유지관리 파일에 둔다.
    # 절과 경로 안내만 고정해 규칙이 조용히 삭제되거나 상시 읽는 파일로 돌아가지 않게 한다.
    moment_anchors = {
        "author-memory.md": ("author-memory-maintenance.md", "## 回执怎么告诉作者", "## 记不记、记成什么", "record --workspace", "query  --workspace"),
        "author-memory-maintenance.md": ("## 整理作者记忆", "## 任务映射表", "## 单书布局", "## 存量迁移", "## 冲突候选", "12288", "migrate --workspace", "commit  --workspace", "check   --workspace"),
    }
    moment_equivalents = {
        "## 回执怎么告诉作者": "## 작가에게 영수증 전달하기",
        "## 记不记、记成什么": "## 무엇을 어떻게 기억할 것인가",
        "## 整理作者记忆": "## 작가 기억 정리",
        "## 任务映射表": "## 작업 매핑 표",
        "## 单书布局": "## 단일 작품 배치",
        "## 存量迁移": "## 기존 항목 마이그레이션",
        "## 冲突候选": "## 충돌 후보",
    }
    for name, fragments in moment_anchors.items():
        for path in sorted(path for path in expected_protocols if path.name == name):
            content = path.read_text(encoding="utf-8")
            for fragment in fragments:
                assert fragment in content or (fragment in moment_equivalents and moment_equivalents[fragment] in content), f"{path} 缺少作者记忆时刻锚点：{fragment}"
    hot = (REPO / "skills/story-long-write/references/author-memory.md").read_text(encoding="utf-8")
    for rare in ("## 整理作者记忆", "12288", "migrate --workspace", "commit  --workspace"):
        assert rare not in hot, f"少见时刻规则回流到 author-memory.md：{rare}"
        if rare in moment_equivalents:
            assert moment_equivalents[rare] not in hot, f"유지관리 규칙이 author-memory.md에 들어옴: {rare}"

    print("OK: author-memory transaction behavior")


if __name__ == "__main__":
    main()
