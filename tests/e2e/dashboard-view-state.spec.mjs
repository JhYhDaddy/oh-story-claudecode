import { rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const fileA = "작품분석실/盘龙/dashboard-view-a.md";
const fileB = "작품분석실/盘龙/dashboard-view-b.md";
const original = "# 状态恢复\n\n这是磁盘上的正文。\n";
const documentUrl = (file, mode = "edit") => `/?${new URLSearchParams({ file, mode })}`;

test.beforeEach(async ({ request }) => {
  const { workspace } = await (await request.get("/api/workspace")).json();
  await writeFile(resolve(workspace.path, fileA), original);
  await writeFile(resolve(workspace.path, fileB), "# 另一份원고\n");
});

test.afterEach(async ({ request }) => {
  const { workspace } = await (await request.get("/api/workspace")).json();
  await Promise.all([fileA, fileB].map((file) => rm(resolve(workspace.path, file), { force: true })));
});

test("@mobile 새로고침 후 보기·파일·모드·줄 번호를 복원하고 명시적 링크를 우선한다", async ({ page }) => {
  await page.goto(documentUrl(fileA));
  await expect(page.locator("#editorInput")).toHaveValue(original);
  await page.getByRole("button", { name: "미리 보기", exact: true }).click();
  await page.locator("#lineNumbersButton").click();
  // 파일의 소속 모음과 현재 사이드바 보기는 다를 수 있으므로 복원 시 각각 유지해야 한다.
  if (await page.locator("#mobileBackButton").isVisible()) {
    await page.locator("#mobileBackButton").click();
  }
  await page.locator("#projectsTab").click();
  for (const navigate of [() => page.reload(), () => page.goto("/")]) {
    await navigate();
    await expect(page.locator("#previewPane")).toBeVisible();
    await expect(page.locator("#previewPane")).toContainText("这是磁盘上的正文");
    await expect(page.locator("#projectsTab")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#lineNumbersButton")).toHaveAttribute("aria-pressed", "false");
  }
  await page.goto(documentUrl(fileB));
  await expect(page.locator("#editorInput")).toBeVisible();
  await expect(page.locator("#editorTitle")).toHaveText("dashboard-view-b.md");
  await expect(page.locator("#librariesTab")).toHaveAttribute("aria-selected", "true");

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#deleteButton").click();
  await expect(page.locator("#toastRegion")).toContainText("삭제했습니다");
  await expect(page.locator("#editorWorkspace")).toBeHidden();
  await expect(page.locator("#fileTree")).toBeVisible();
  expect(new URL(page.url()).searchParams.has("file")).toBe(false);
  await page.reload();
  await expect(page.locator("#connectionStatus")).toContainText("이 컴퓨터에서만 사용");
  await expect(page.locator("#editorWorkspace")).toBeHidden();
  await expect(page.locator("#toastRegion")).not.toContainText("파일이 없습니다");
});

test("목록 갱신과 전환 취소 시 미저장 원고를 유지한다", async ({ page, context }) => {
  await page.goto(documentUrl(fileA));
  await expect(page.locator("#editorInput")).toHaveValue(original);
  const draft = `${original}未저장的改动`;
  await page.locator("#editorInput").fill(draft);
  await page.locator("#refreshButton").click();
  await expect(page.locator("#toastRegion")).toContainText("작업 공간 목록을 새로고침했습니다");
  await expect(page.locator("#editorInput")).toHaveValue(draft);
  await expect(page.locator("#dirtyStatus")).toContainText("저장 필요");
  let dismissed = false;
  page.once("dialog", async (dialog) => {
    dismissed = true;
    await dialog.dismiss();
  });
  await page.locator(`.file-row[data-path='${fileB}']`).click();
  expect(dismissed).toBe(true);
  await expect(page.locator("#editorInput")).toHaveValue(draft);
  expect(new URL(page.url()).searchParams.get("file")).toBe(fileA);
  await page.getByRole("button", { name: "미리 보기", exact: true }).click();
  const stored = await page.evaluate(() => JSON.stringify(localStorage));
  expect(stored).not.toContain("未저장的改动");
  const reopened = await context.newPage();
  await reopened.goto("/");
  await expect(reopened.locator("#previewPane")).toBeVisible();
  await expect(reopened.locator("#previewPane")).not.toContainText("未저장的改动");
  await reopened.close();
});

test("작업 공간을 구분하고 손상된 상태와 없는 파일을 복구한다", async ({ page, request }) => {
  const data = await (await request.get("/api/workspace")).json();
  const key = `story_dashboard_view:${data.workspace.path}`;
  await page.goto(documentUrl(fileA));
  await expect(page.locator("#editorInput")).toHaveValue(original);
  await page.route("**/api/workspace", (route) => route.fulfill({
    json: { ...data, workspace: { ...data.workspace, path: `${data.workspace.path}/another-workspace` } },
  }));
  await page.goto("/");
  await expect(page.locator("#editorEmpty")).toBeVisible();
  await expect(page.locator("#connectionStatus")).toContainText("이 컴퓨터에서만 사용");
  await page.unroute("**/api/workspace");

  await page.evaluate((key) => localStorage.setItem(key, "{broken"), key);
  await page.goto("/");
  await expect(page.locator("#editorEmpty")).toBeVisible();
  await page.evaluate((key) => localStorage.setItem(key, JSON.stringify({
    file: "작품분석실/盘龙/不存在的원고.md", view: "invalid", mode: "invalid",
  })), key);
  await page.goto("/");
  await expect(page.locator("#toastRegion")).toContainText("파일이 없습니다");
  await expect(page.locator("#editorEmpty")).toBeVisible();
  await expect.poll(() => page.evaluate((key) => JSON.parse(localStorage.getItem(key)).file, key)).toBeNull();
  expect(new URL(page.url()).searchParams.has("file")).toBe(false);
  await page.locator(`.file-row[data-path='${fileA}']`).click();
  await expect(page.locator("#editorInput")).toHaveValue(original);
});

test("localStorage 없이도 파일 링크와 줄 번호를 사용한다", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new DOMException("blocked", "SecurityError"); } });
  });
  await page.goto(documentUrl(fileA, "preview"));
  await expect(page.locator("#previewPane")).toContainText("状态恢复");
  await page.locator("#lineNumbersButton").click();
  await page.reload();
  await expect(page.locator("#previewPane")).toBeVisible();
  expect(errors).toEqual([]);
});

test("시스템 테마를 따르되 수동 선택을 기억한다", async ({ page }) => {
  const scheme = () => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect.poll(scheme).toBe("dark");

  await page.locator("#themeButton").click();
  await expect.poll(scheme).toBe("light");
  await page.reload();
  await expect.poll(scheme).toBe("light");

  await page.locator("#themeButton").click();
  await page.emulateMedia({ colorScheme: "light" });
  await page.reload();
  await expect.poll(scheme).toBe("dark");
});

test("@mobile 긴 문단·빈 줄·스크롤에서 줄 번호를 맞추고 미리 보기에도 유지한다", async ({ page }, testInfo) => {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(documentUrl(fileA));
  await expect(page.locator("#editorInput")).toHaveValue(original);
  const mixed = "中文折行 test_with_a_long_word_without_spaces 😀\t".repeat(12);
  const content = Array.from({ length: 40 }, (_, index) => index % 3 ? mixed : "").join("\n") + "\n";
  await page.locator("#editorInput").fill(content);
  await expect(page.locator(".gutter-line")).toHaveCount(41);
  const heightDifference = () => page.evaluate(() => {
    const input = document.querySelector("#editorInput");
    const gutter = document.querySelector("#lineNumbersGutter");
    return Math.abs(input.scrollHeight - gutter.scrollHeight);
  });
  await expect.poll(heightDifference).toBeLessThanOrEqual(2);
  await page.locator("#editorInput").press(process.platform === "darwin" ? "Meta+End" : "Control+End");
  // 명시적 스크롤은 브라우저와 호스트 운영체제의 단축키가 다른 경우도 다룬다.
  await page.locator("#editorInput").evaluate((input) => { input.scrollTop = input.scrollHeight; });
  await expect.poll(() => page.evaluate(() => Math.abs(
    document.querySelector("#editorInput").scrollTop - document.querySelector("#lineNumbersGutter").scrollTop,
  ))).toBeLessThanOrEqual(2);
  if (testInfo.project.name === "chromium") {
    await page.setViewportSize({ width: 900, height: 700 });
    await expect.poll(heightDifference).toBeLessThanOrEqual(2);
  }
  await page.locator("#lineNumbersButton").click();
  await expect(page.locator("#lineNumbersGutter")).toBeHidden();
  await page.locator("#lineNumbersButton").click();
  await expect.poll(heightDifference).toBeLessThanOrEqual(2);
  const markdown = "# 标题\n\n一段正文。\n- 프로젝트\n> 引用\n```txt\n示例\n```\n\n尾声";
  await page.locator("#editorInput").fill(markdown);
  await page.getByRole("button", { name: "미리 보기", exact: true }).click();
  expect(await page.locator("#previewPane [data-line]").evaluateAll((nodes) => nodes.map((node) => node.dataset.line)))
    .toEqual(["1", "3", "4", "5", "6", "10"]);
  await expect(page.locator("#previewPane pre")).toHaveText("示例");
  await page.screenshot({ path: testInfo.outputPath("preview-line-numbers.png") });
  expect(errors).toEqual([]);
});
