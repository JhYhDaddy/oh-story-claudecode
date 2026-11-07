import { mkdir, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("한국어 데모의 분석 자료를 열고 프로젝트를 검색·편집·저장한다", async ({ page, request }) => {
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/");
  await expect(page).toHaveTitle(/OH STORY/);
  await expect(page.getByText("OH STORY", { exact: true })).toBeVisible();
  await expect(page.locator("#connectionStatus")).toContainText("이 컴퓨터에서만 사용");
  await expect(page.locator("#libraryCount")).toHaveText("2");
  await expect(page.locator("#projectCount")).toHaveText("1");
  await expect(page.locator("#fileCount")).not.toHaveText("—");

  await page.locator("#librariesTab").focus();
  await page.locator("#librariesTab").press("ArrowRight");
  await expect(page.locator("#projectsTab")).toHaveAttribute("aria-selected", "true");
  await page.locator("#projectsTab").press("ArrowLeft");
  await expect(page.locator("#librariesTab")).toHaveAttribute("aria-selected", "true");

  await expect(page.locator("#fileTree")).toContainText("盘龙");
  await expect(page.locator("#fileTree")).toContainText("曾将爱意私藏");
  await page.locator(".file-row[data-path='작품분석실/盘龙/작품분석보고서.md']").click();
  await expect(page.locator("#editorTitle")).toHaveText("작품분석보고서.md");
  await expect(page.locator("#editorInput")).toHaveValue(/盘龙/);

  const marker = `\n\n<!-- dashboard-e2e-${Date.now()} -->`;
  await page.locator("#editorInput").fill(
    `${await page.locator("#editorInput").inputValue()}${marker}`,
  );
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");
  await expect(page.locator("#saveButton")).toBeEnabled();

  const shortcut = process.platform === "darwin" ? "Meta+s" : "Control+s";
  await page.locator("#editorInput").press(shortcut);
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");
  await expect(page.locator("#toastRegion")).toContainText("저장했습니다");

  const activePath = await page.locator(".file-row[data-active='true']").getAttribute("data-path");
  const persisted = await request.get(`/api/file?path=${encodeURIComponent(activePath)}`);
  expect(persisted.ok()).toBeTruthy();
  expect((await persisted.json()).content).toContain(marker.trim());

  await page.locator("#editorInput").fill("<img src=x onerror=alert('unsafe')>\n\n# 安全미리 보기");
  await page.getByRole("button", { name: "미리 보기", exact: true }).click();
  await expect(page.locator("#previewPane")).toContainText("<img src=x onerror=alert('unsafe')>");
  await expect(page.locator("#previewPane img")).toHaveCount(0);
  await expect(page.locator("#previewPane h1")).toHaveText("安全미리 보기");

  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await expect(page.locator("#treeTruncationNotice")).toHaveCount(0);
  await expect(page.locator("#fileTree")).not.toContainText("관계.md");
  await page.locator("summary").filter({ hasText: "설정" }).click();
  await expect(page.locator("#fileTree")).toContainText("관계.md");
  const unfilteredRows = await page.locator("#fileTree .file-row").count();
  expect(unfilteredRows).toBeGreaterThan(1);

  // 검색은 서버가 필요할 때 스캔하므로 인물 디렉터리를 펼치지 않아도 江晨을 찾아야 한다.
  await page.locator("#treeSearch").fill("江晨");
  await expect(page.locator("#fileTree")).toContainText("江晨.md");
  await expect(page.locator("#fileTree")).not.toContainText("관계.md");
  await expect(page.locator("#fileTree")).not.toContainText("상세개요_제003장");
  await expect(page.locator("#fileTree")).not.toContainText("盘龙");
  // 행 수 대신 트리가 검색 결과 집합으로 필터링됐는지 단언한다. 데모에 동명 파일이 늘면 결과 수도 달라진다.
  // (인물은 설정/인물/{名}.md와 추적/인물상태/{名}.md에 모두 있으므로 행 수 비교는 우연히 실패할 수 있다.)
  const filteredPaths = await page
    .locator("#fileTree .file-row")
    .evaluateAll((rows) => rows.map((row) => row.dataset.path ?? ""));
  expect(filteredPaths.length).toBeGreaterThan(0);
  expect(filteredPaths.every((path) => path.includes("江晨"))).toBe(true);
  await page.locator("#refreshButton").click();
  await expect(page.locator("#toastRegion")).toContainText("작업 공간 목록을 새로고침했습니다");
  await expect(page.locator("#fileTree")).toContainText("江晨.md");

  // 검색을 지우면 로드된 디렉터리로 돌아가며 작가가 방금 펼친 설정 디렉터리가 접히면 안 된다.
  await page.locator("#treeSearch").press("Escape");
  await expect(page.locator("#treeSearch")).toHaveValue("");
  await expect(page.locator("#fileTree")).toContainText("관계.md");
  expect(await page.locator("#fileTree .file-row").count()).toBe(unfilteredRows);

  expect(consoleErrors).toEqual([]);
});

test("원고 삭제 전에 확인하고 파일 목록을 갱신한다", async ({ page, request }, testInfo) => {
  const retryFiles = [
    "작품분석실/盘龙/_progress.md",
    "작품분석실/盘龙/빠른미리보기.md",
    "작품분석실/盘龙/개요요약.md",
  ];
  const filePath = retryFiles[testInfo.retry];
  await page.goto("/");
  await expect(page.locator("#fileCount")).toContainText("+");
  const initialFileCount = Number(
    (await page.locator("#fileCount").textContent()).replace(/[,+]/g, ""),
  );
  expect(Number.isFinite(initialFileCount)).toBeTruthy();

  const fileName = filePath.split("/").at(-1);
  await page.locator(`.file-row[data-path='${filePath}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText(fileName);

  // dialog 콜백 안의 단언은 대화상자가 열리지 않으면 실행되지 않아 검증 효과가 없다.
  // 콜백 밖에 먼저 기록하고 클릭 후 단언한다. 반드시 삭제 취소 경로부터 검사한다.
  let dismissed = null;
  page.once("dialog", async (dialog) => {
    dismissed = { type: dialog.type(), message: dialog.message() };
    await dialog.dismiss();
  });
  await page.locator("#deleteButton").click();
  await expect.poll(() => dismissed).not.toBeNull();
  expect(dismissed.type).toBe("confirm");
  expect(dismissed.message).toContain(fileName);
  expect(dismissed.message).toContain("되돌릴 수 없습니다");

  await expect(page.locator(`.file-row[data-path='${filePath}']`)).toHaveCount(1);
  await expect(page.locator("#fileCount")).toHaveText(`${initialFileCount}+`);
  await expect(page.locator("#editorTitle")).toHaveText(fileName);
  const survived = await request.get(`/api/file?path=${encodeURIComponent(filePath)}`);
  expect(survived.status()).toBe(200);

  let accepted = null;
  page.once("dialog", async (dialog) => {
    accepted = { type: dialog.type(), message: dialog.message() };
    await dialog.accept();
  });
  await page.locator("#deleteButton").click();
  await expect.poll(() => accepted).not.toBeNull();
  expect(accepted.type).toBe("confirm");
  expect(accepted.message).toContain(fileName);
  expect(accepted.message).toContain("되돌릴 수 없습니다");

  await expect(page.locator("#toastRegion")).toContainText("삭제했습니다");
  await expect(page.locator("#editorEmpty")).toBeVisible();
  await expect(page.locator(`.file-row[data-path='${filePath}']`)).toHaveCount(0);
  await expect(page.locator("#fileCount")).toHaveText(`${initialFileCount - 1}+`);

  const deleted = await request.get(`/api/file?path=${encodeURIComponent(filePath)}`);
  expect(deleted.status()).toBe(404);
});

test("저장 중 다른 원고를 열어도 저장 결과가 섞이지 않는다", async ({ page, request }) => {
  const fileA = "작품분석실/盘龙/문체.md";
  const fileB = "작품분석실/盘龙/작품분석보고서.md";
  await page.goto("/");
  await expect(page.locator("#fileCount")).not.toHaveText("—");

  // PUT을 늦춰 네트워크 드라이브나 백신 검사로 인한 느린 저장을 재현한다.
  await page.route("**/api/file", async (route) => {
    if (route.request().method() === "PUT") {
      await new Promise((accept) => setTimeout(accept, 1500));
    }
    await route.continue();
  });

  await page.locator(`.file-row[data-path='${fileA}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText("문체.md");
  const markerA = `\n<!-- dashboard-race-a-${Date.now()} -->`;
  await page.locator("#editorInput").fill(
    `${await page.locator("#editorInput").inputValue()}${markerA}`,
  );
  await page.locator("#saveButton").click();
  await expect(page.locator("#dirtyStatus")).toContainText("저장 중");

  // 저장이 진행 중일 때 다른 원고로 전환해 계속 작성한다.
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator(`.file-row[data-path='${fileB}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText("작품분석보고서.md");
  const markerB = `\n<!-- dashboard-race-b-${Date.now()} -->`;
  await page.locator("#editorInput").fill(
    `${await page.locator("#editorInput").inputValue()}${markerB}`,
  );
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");

  // A 저장 완료 시 A만 알리고 B는 미저장 상태를 유지해야 한다. B를 저장 완료로 처리하면 안 된다.
  await expect(page.locator("#toastRegion")).toContainText("《문체.md》을(를) 저장했습니다");
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");
  await expect(page.locator("#saveButton")).toBeEnabled();

  const persistedA = await request.get(`/api/file?path=${encodeURIComponent(fileA)}`);
  expect((await persistedA.json()).content).toContain(markerA.trim());
  const staleB = await request.get(`/api/file?path=${encodeURIComponent(fileB)}`);
  expect((await staleB.json()).content).not.toContain(markerB.trim());

  // B를 저장할 때는 B의 버전 번호를 사용해야 한다. A의 버전이 섞여 거짓 충돌이 생기면 안 된다.
  await page.locator("#saveButton").click();
  await expect(page.locator("#toastRegion")).toContainText("《작품분석보고서.md》을(를) 저장했습니다");
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");
  await expect(page.locator("#conflictDialog")).toBeHidden();
  const savedB = await request.get(`/api/file?path=${encodeURIComponent(fileB)}`);
  expect((await savedB.json()).content).toContain(markerB.trim());
});

test("저장 중 추가한 내용은 미저장 상태로 남는다", async ({ page, request }) => {
  const filePath = "작품분석실/盘龙/문체.md";
  await page.goto("/");
  await expect(page.locator("#fileCount")).not.toHaveText("—");
  await page.route("**/api/file", async (route) => {
    if (route.request().method() === "PUT") {
      await new Promise((accept) => setTimeout(accept, 1500));
    }
    await route.continue();
  });

  await page.locator(`.file-row[data-path='${filePath}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText("문체.md");
  const saveMarker = `\n<!-- dashboard-inflight-saved-${Date.now()} -->`;
  await page.locator("#editorInput").fill(
    `${await page.locator("#editorInput").inputValue()}${saveMarker}`,
  );

  const shortcut = process.platform === "darwin" ? "Meta+s" : "Control+s";
  await page.locator("#editorInput").press(shortcut);
  await expect(page.locator("#dirtyStatus")).toContainText("저장 중");
  const lateMarker = "\n<!-- dashboard-inflight-late -->";
  await page.locator("#editorInput").fill(
    `${await page.locator("#editorInput").inputValue()}${lateMarker}`,
  );

  await expect(page.locator("#toastRegion")).toContainText("《문체.md》을(를) 저장했습니다");
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");
  await expect(page.locator("#saveButton")).toBeEnabled();

  const persisted = await request.get(`/api/file?path=${encodeURIComponent(filePath)}`);
  const content = (await persisted.json()).content;
  expect(content).toContain(saveMarker.trim());
  expect(content).not.toContain(lateMarker.trim());
});

test("CRLF 원고의 줄바꿈과 변경 표시를 보존한다", async ({ page, request }) => {
  const filePath = "장편/让你管账号，你高燃混剪炸全网/설정/문체.md";
  const loaded = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  const crlfContent = loaded.content.replaceAll("\r\n", "\n").replaceAll("\n", "\r\n");
  const converted = await request.put("/api/file", {
    data: { path: filePath, content: crlfContent, expectedVersion: loaded.version },
  });
  expect(converted.ok()).toBeTruthy();
  expect(crlfContent).toContain("\r\n");

  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await page.locator("#treeSearch").fill("문체");
  await page.locator(`.file-row[data-path='${filePath}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText("문체.md");
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");

  // 한 글자를 입력했다 지우면 저장 완료로 돌아가야 한다. 기준값에 CRLF가 남으면 계속 저장 대기 상태가 된다.
  await page.locator("#editorInput").press("End");
  await page.locator("#editorInput").pressSequentially("改");
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");
  await page.locator("#editorInput").press("Backspace");
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");

  await page.locator("#editorInput").pressSequentially("改");
  await page.locator("#saveButton").click();
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");

  const saved = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  expect(saved.content).toContain("\r\n");
  expect(saved.content.replaceAll("\r\n", "")).not.toContain("\n");
  expect(saved.size).toBe(Buffer.byteLength(crlfContent) + Buffer.byteLength("改"));
});

test("LF 원고 안의 단독 CR이 전체 줄바꿈을 바꾸지 않는다", async ({ page, request }) => {
  const filePath = "장편/让你管账号，你高燃混剪炸全网/설정/문체.md";
  const loaded = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  const mixedContent = "# 文风\n第一行。\n第二行前\r第二行后。\n第三行。\n";
  const converted = await request.put("/api/file", {
    data: { path: filePath, content: mixedContent, expectedVersion: loaded.version },
  });
  expect(converted.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await page.locator("#treeSearch").fill("문체");
  await page.locator(`.file-row[data-path='${filePath}']`).click();
  await expect(page.locator("#editorTitle")).toHaveText("문체.md");

  await page.locator("#editorInput").press("End");
  await page.locator("#editorInput").pressSequentially("改");
  await page.locator("#saveButton").click();
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");

  const saved = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  expect(saved.content).toContain("\n");
  expect(saved.content).not.toContain("\r");
  expect(saved.content.split("\n")).toHaveLength(6);
});

test("CRLF 원고 안의 단독 CR이 전체를 LF로 바꾸지 않는다", async ({ page, request }) => {
  const filePath = "장편/让你管账号，你高燃混剪炸全网/설정/문체.md";
  const loaded = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  const converted = await request.put("/api/file", {
    data: {
      path: filePath,
      content: "# 文风\r\n第一行。\r\n第二行前\r第二行后。\r\n第三行。",
      expectedVersion: loaded.version,
    },
  });
  expect(converted.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await page.locator("#treeSearch").fill("문체");
  await page.locator(`.file-row[data-path='${filePath}']`).click();
  const editor = page.locator("#editorInput");
  await expect(page.locator("#editorTitle")).toHaveText("문체.md");
  await expect(editor).toBeEnabled();
  await editor.press("End");
  await editor.pressSequentially("\n改");
  await page.locator("#saveButton").click();
  await expect(page.locator("#dirtyStatus")).toContainText("저장됨");

  const saved = await request
    .get(`/api/file?path=${encodeURIComponent(filePath)}`)
    .then((response) => response.json());
  expect(saved.content).toContain("\r\n");
  expect(saved.content.replaceAll("\r\n", "")).not.toContain("\r");
  expect(saved.content.split("\r\n")).toHaveLength(6);
});

test("원고를 열어도 펼친 폴더가 접히지 않는다", async ({ page }) => {
  const rowPath = "장편/让你管账号，你高燃混剪炸全网/개요/상세개요_제002장.md";
  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await expect(page.locator("#fileTree")).toContainText("让你管账号，你高燃混剪炸全网");

  await page.locator("summary").filter({ hasText: "개요" }).click();
  const row = page.locator(`.file-row[data-path='${rowPath}']`);
  await expect(row).toBeVisible();

  await row.click();
  await expect(page.locator("#editorTitle")).toHaveText("상세개요_제002장.md");
  await expect(row).toBeVisible();
  await expect(row).toHaveAttribute("data-active", "true");

  await page.locator("#refreshButton").click();
  await expect(page.locator("#toastRegion")).toContainText("작업 공간 목록을 새로고침했습니다");
  await expect(row).toBeVisible();
  await expect(row).toHaveAttribute("data-active", "true");

  await page.locator("#treeSearch").fill("상세개요_제002장");
  await expect(page.locator("#fileTree")).not.toContainText("상세개요_제003장");
  await page.locator("#treeSearch").fill("");
  await expect(row).toBeVisible();
});

test("깊은 폴더의 원고도 검색으로 찾는다", async ({ page, request }) => {
  const workspace = await request.get("/api/workspace").then((response) => response.json());
  const projectPath = workspace.projects[0].path;
  const nestedRoot = resolve(workspace.workspace.path, projectPath, "본문", "深卷");
  const nestedLeaf = resolve(
    nestedRoot,
    ...Array.from({ length: 11 }, (_, index) => `第${index + 1}折`),
  );

  try {
    await mkdir(nestedLeaf, { recursive: true });
    await writeFile(resolve(nestedLeaf, "埋掉的一章.md"), "深处的正文", "utf8");

    await page.goto("/");
    await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
    await page.locator("#treeSearch").fill("埋掉的一章");
    await expect(page.locator("#fileTree")).toContainText("埋掉的一章.md");
    await expect(page.locator("#treeTruncationNotice")).toHaveCount(0);
  } finally {
    await rm(nestedRoot, { recursive: true, force: true });
  }
});

test("폴더 읽기 실패 시 권한과 연결 상태를 안내한다", async ({ page }) => {
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.libraries = [];
    payload.scanErrors = [
      { path: "작품분석실", code: "EACCES", message: "目录无法读取" },
    ];
    payload.limits = {
      ...payload.limits,
      truncated: true,
      truncatedByReadError: true,
    };
    await route.fulfill({ response, json: payload });
  });

  await page.goto("/");
  await expect(page.locator("#treeTruncationNotice")).toContainText("작품분석실을(를) 읽을 수 없어");
  await expect(page.locator("#treeTruncationNotice")).toContainText("폴더 접근 권한과 외장 드라이브 연결을 확인한 뒤 목록을 새로고침하세요");
  await expect(page.locator("#fileCount")).toHaveAttribute(
    "title",
    "폴더를 펼칠 때 원고를 불러옵니다. 전체 작업 공간을 미리 읽지 않습니다",
  );
});

test("폴더 자동 로드 실패 후 사용자 요청이 있을 때만 재시도한다", async ({ page }) => {
  let treeRequests = 0;
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.libraries = [
      {
        name: "坏档案",
        path: "작품분석실/坏档案",
        type: "directory",
        children: [],
        loaded: false,
      },
    ];
    payload.stats.libraries = 1;
    await route.fulfill({ response, json: payload });
  });
  await page.route("**/api/tree?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("path") !== "작품분석실/坏档案") {
      await route.continue();
      return;
    }
    treeRequests += 1;
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "directory_unreadable",
          message: "폴더를 읽을 수 없습니다. 접근 권한이나 드라이브 연결 상태를 확인하세요: 작품분석실/坏档案",
        },
      }),
    });
  });

  await page.goto("/");
  const retry = page.getByRole("button", { name: "폴더를 불러오지 못했습니다. 눌러서 다시 시도하세요" });
  await expect(retry).toBeVisible();
  await page.waitForTimeout(500);
  expect(treeRequests).toBe(1);
  await expect(page.locator("#toastRegion .toast")).toHaveCount(1);

  await retry.click();
  await expect.poll(() => treeRequests).toBe(2);
  await page.waitForTimeout(300);
  expect(treeRequests).toBe(2);
  await expect(retry).toBeVisible();
});

test("검색 결과가 없어도 제한에 도달한 원인을 표시한다", async ({ page }) => {
  await page.route("**/api/search?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "不存在的파일",
        scope: "projects",
        results: [],
        truncated: true,
        truncation: {
          byResults: false,
          byNodes: true,
          byDepth: false,
          byReadError: false,
        },
        scanErrors: [],
        limits: {
          maxResults: 100,
          maxNodes: 5000,
          maxDepth: 20,
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await page.locator("#treeSearch").fill("不存在的파일");
  await expect(page.locator("#fileTree")).toContainText(
    "검색이 끝나지 않아 “不存在的파일”의 존재 여부를 확인하지 못했습니다",
  );
  await expect(page.locator("#fileTree")).toContainText(
    "검색 항목 수가 5,000개 한도에 도달해 나머지 폴더는 확인하지 못했습니다",
  );
});

test("검색 중 읽기 실패 시 권한과 연결 상태를 안내한다", async ({ page }) => {
  await page.route("**/api/search?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "目标章",
        scope: "projects",
        results: [],
        truncated: true,
        truncation: {
          byResults: false,
          byNodes: false,
          byDepth: false,
          byReadError: true,
        },
        scanErrors: [{ path: "示例书/본문/受限卷", code: "EACCES" }],
        limits: {
          maxResults: 100,
          maxNodes: 5000,
          maxDepth: 20,
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await page.locator("#treeSearch").fill("目标章");
  await expect(page.locator("#fileTree")).toContainText(
    "검색이 끝나지 않아 “目标章”의 존재 여부를 확인하지 못했습니다",
  );
  await expect(page.locator("#fileTree")).toContainText("示例书/본문/受限卷을(를) 읽을 수 없어");
  await expect(page.locator("#fileTree")).toContainText("접근 권한이나 외장 드라이브 연결 상태");
  await expect(page.locator("#fileTree")).not.toContainText("“目标章”을(를) 찾지 못했습니다");
});

test("목록을 추가로 불러와도 앞서 표시한 파일이 유지된다", async ({ page, request }) => {
  const workspace = await request.get("/api/workspace").then((response) => response.json());
  const project = resolve(workspace.workspace.path, workspace.projects[0].path);
  const volume = resolve(project, "批量卷");

  try {
    await mkdir(volume, { recursive: true });
    for (let start = 0; start < 205; start += 100) {
      await Promise.all(
        Array.from({ length: Math.min(100, 205 - start) }, (_, offset) =>
          writeFile(
            resolve(volume, `제${String(start + offset + 1).padStart(5, "0")}장.md`),
            "凑数",
            "utf8",
          ),
        ),
      );
    }

    await page.goto("/");
    await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
    await page.locator("summary").filter({ hasText: "批量卷" }).click();
    const first = page.locator(
      `.file-row[data-path='${workspace.projects[0].path}/批量卷/제00001장.md']`,
    );
    const last = page.locator(
      `.file-row[data-path='${workspace.projects[0].path}/批量卷/제00205장.md']`,
    );
    await expect(first).toBeVisible();
    await expect(last).toHaveCount(0);
    await page.getByRole("button", { name: "더 불러오기" }).click();
    await expect(first).toBeVisible();
    await expect(last).toBeVisible();
    await expect(page.getByRole("button", { name: "더 불러오기" })).toHaveCount(0);
  } finally {
    await rm(volume, { recursive: true, force: true });
  }
});

test("@mobile 모바일 화면에서 장편 프로젝트 개요를 연다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("OH STORY", { exact: true })).toBeVisible();
  await expect(page.locator(".archive-panel")).toBeVisible();

  await page.getByRole("tab", { name: /집필 프로젝트/ }).click();
  await expect(page.locator("#fileTree")).toContainText("让你管账号，你高燃混剪炸全网");
  await page.locator("summary").filter({ hasText: "개요" }).click();
  await page
    .locator(".file-row[data-path='장편/让你管账号，你高燃混剪炸全网/개요/개요.md']")
    .click();

  await expect(page.locator("#editorTitle")).toHaveText("개요.md");
  await expect(page.locator("#editorWorkspace")).toBeVisible();
  await expect(page.locator("#saveButton")).toBeVisible();
  await expect(page.locator("#editorInput")).toBeVisible();

  if (page.viewportSize().width <= 720) {
    await expect(page.locator(".archive-panel")).toBeHidden();
    await page.locator("#mobileBackButton").click();
    await expect(page.locator(".archive-panel")).toBeVisible();
    await expect(page.locator(".editor-panel")).toBeHidden();
  }
});
