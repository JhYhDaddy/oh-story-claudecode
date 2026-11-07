// 밝음·어둠 테마는 이 브라우저의 읽기 선호다. 선택 전에는 시스템을 따르고 선택 후에는 기억한다.
const THEME_KEY = "story_dashboard_theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
let themeChoice = null;
try {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") themeChoice = saved;
} catch {}

function effectiveTheme() {
  return themeChoice || (systemDark.matches ? "dark" : "light");
}

function applyTheme() {
  if (themeChoice) document.documentElement.dataset.theme = themeChoice;
  else delete document.documentElement.dataset.theme;
  const button = document.querySelector("#themeButton");
  if (!button) return;
  const label = effectiveTheme() === "dark" ? "밝은 테마로 전환" : "어두운 테마로 전환";
  button.title = label;
  button.setAttribute("aria-label", label);
}

applyTheme();

const state = {
  workspace: null,
  activeView: "libraries",
  activeFile: null,
  originalContent: "",
  dirty: false,
  mode: "edit",
  restored: false,
  showLineNumbers: true,
  filter: "",
  loadingFile: false,
  saving: false,
  deleting: false,
  searching: false,
  searchResults: [],
  searchTruncation: null,
  searchSequence: 0,
  searchTimer: null,
  // 작가가 펼치거나 접은 디렉터리를 기억해 트리를 다시 그려도 살펴보던 장 폴더가 닫히지 않게 한다.
  expandedDirs: new Set(),
  collapsedDirs: new Set(),
};

const elements = {
  workspaceName: document.querySelector("#workspaceName"),
  workspacePath: document.querySelector("#workspacePath"),
  connectionStatus: document.querySelector("#connectionStatus"),
  treeSearch: document.querySelector("#treeSearch"),
  libraryCount: document.querySelector("#libraryCount"),
  projectCount: document.querySelector("#projectCount"),
  fileCount: document.querySelector("#fileCount"),
  librariesBadge: document.querySelector("#librariesBadge"),
  projectsBadge: document.querySelector("#projectsBadge"),
  archiveTabs: [...document.querySelectorAll(".archive-tabs [role='tab']")],
  treePanel: document.querySelector("#treePanel"),
  treeLoading: document.querySelector("#treeLoading"),
  fileTree: document.querySelector("#fileTree"),
  refreshButton: document.querySelector("#refreshButton"),
  themeButton: document.querySelector("#themeButton"),
  mobileBackButton: document.querySelector("#mobileBackButton"),
  editorEmpty: document.querySelector("#editorEmpty"),
  editorWorkspace: document.querySelector("#editorWorkspace"),
  editorBody: document.querySelector("#editorBody"),
  editorContainer: document.querySelector("#editorContainer"),
  lineNumbersGutter: document.querySelector("#lineNumbersGutter"),
  lineNumbersButton: document.querySelector("#lineNumbersButton"),
  editorTitle: document.querySelector("#editorTitle"),
  breadcrumbs: document.querySelector("#breadcrumbs"),
  dirtyStatus: document.querySelector("#dirtyStatus"),
  documentMeta: document.querySelector("#documentMeta"),
  editorInput: document.querySelector("#editorInput"),
  previewPane: document.querySelector("#previewPane"),
  modeButtons: [...document.querySelectorAll(".mode-switch button")],
  deleteButton: document.querySelector("#deleteButton"),
  saveButton: document.querySelector("#saveButton"),
  cursorPosition: document.querySelector("#cursorPosition"),
  encodingLabel: document.querySelector("#encodingLabel"),
  toastRegion: document.querySelector("#toastRegion"),
  conflictDialog: document.querySelector("#conflictDialog"),
  reloadConflictButton: document.querySelector("#reloadConflictButton"),
  truncationNotice: null,
};

class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function requestJson(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    setConnection("offline", "연결 끊김");
    throw new ApiError(0, "network_error", "로컬 대시보드 서비스에 연결할 수 없습니다");
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code || "request_failed",
      payload?.error?.message || `요청 실패(${response.status})`,
    );
  }
  setConnection("online", "이 컴퓨터에서만 사용");
  return payload;
}

function setConnection(status, label) {
  elements.connectionStatus.dataset.state = status;
  elements.connectionStatus.querySelector("span:last-child").textContent = label;
}

function showToast(message, kind = "success") {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.dataset.kind = kind;
  const text = document.createElement("p");
  text.textContent = message;
  toast.append(text);
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function formatNumber(value) {
  return new Intl.NumberFormat("ko-KR").format(value || 0);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function countCharacters(content) {
  return [...content.replace(/\s/g, "")].length;
}

// textarea의 value는 항상 LF다. 읽을 때 정규화하고 쓸 때 원래 줄바꿈으로 복원한다.
// 그렇지 않으면 CRLF 원고의 한 번 수정으로 전체가 다시 쓰이고 변경 표시도 일치하지 않아 사라지지 않는다.
function detectEol(content) {
  let crlf = 0;
  let lf = 0;
  let cr = 0;
  for (let index = 0; index < content.length; index += 1) {
    if (content[index] === "\r") {
      if (content[index + 1] === "\n") {
        crlf += 1;
        index += 1;
      } else {
        cr += 1;
      }
    } else if (content[index] === "\n") {
      lf += 1;
    }
  }
  // 주된 LF/CRLF 형식으로 저장하며 순수 CR 파일만 CR을 유지한다. 붙여 넣은 고립 CR 하나가
  // 모든 LF를 CR로 바꾸게 하거나 반대로 CRLF 원고 전체를 LF로 바꾸게 해서는 안 된다.
  if (crlf > lf) return "\r\n";
  if (lf > 0) return "\n";
  if (cr > 0) return "\r";
  return "\n";
}

function normalizeEol(content) {
  return content.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
}

function applyEol(content, eol) {
  return !eol || eol === "\n" ? content : content.replaceAll("\n", eol);
}

function activeEol() {
  return state.activeFile?.eol || "\n";
}

function currentByteSize() {
  return new TextEncoder().encode(applyEol(elements.editorInput.value, activeEol())).length;
}

function fileExtension(name) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1) : "";
}

function iconSvg(kind) {
  if (kind === "folder") {
    return `<svg class="tree-icon folder-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6l2 2h9v10h-17z"></path></svg>`;
  }
  return `<svg class="tree-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3.5h8l4 4v13H6z"></path><path d="M14 3.5v4h4M9 12h6M9 16h5"></path></svg>`;
}

function createTreeEntry(node, depth = 0) {
  const item = document.createElement("li");
  if (node.type === "directory") {
    const details = document.createElement("details");
    details.dataset.path = node.path;
    const shouldOpen =
      state.expandedDirs.has(node.path) ||
      (depth === 0 && !state.collapsedDirs.has(node.path));
    details.open = shouldOpen;
    // 작가가 직접 펼치거나 접은 조작만 기록한다. 첫 번째 수준을 프로그램으로 펼치는 것은 선호 설정에 포함하지 않는다.
    let recorded = shouldOpen;
    details.addEventListener("toggle", () => {
      if (details.open === recorded) return;
      recorded = details.open;
      if (details.open) {
        state.expandedDirs.add(node.path);
        state.collapsedDirs.delete(node.path);
        if (!node.loaded && !node.loading) loadDirectory(node);
      } else {
        state.expandedDirs.delete(node.path);
        state.collapsedDirs.add(node.path);
      }
    });
    const summary = document.createElement("summary");
    summary.innerHTML = iconSvg("folder");
    const label = document.createElement("span");
    label.className = "tree-label";
    label.textContent = node.name;
    summary.append(label);
    details.append(summary);

    const list = document.createElement("ul");
    node.children.forEach((child) => {
      const childItem = createTreeEntry(child, depth + 1);
      if (childItem) list.append(childItem);
    });
    if (node.loading) {
      const loading = document.createElement("li");
      loading.className = "tree-inline-status";
      loading.textContent = "폴더를 읽는 중…";
      list.append(loading);
    } else if (node.loadError) {
      const retry = document.createElement("li");
      retry.className = "tree-inline-status";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "폴더를 불러오지 못했습니다. 눌러서 다시 시도하세요";
      button.addEventListener("click", () => loadDirectory(node));
      retry.append(button);
      list.append(retry);
    } else if (node.loaded && node.children.length === 0) {
      const empty = document.createElement("li");
      empty.className = "tree-inline-status";
      empty.textContent = "빈 폴더";
      list.append(empty);
    }
    if (node.nextCursor && !node.loading) {
      const more = document.createElement("li");
      more.className = "tree-inline-status";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "더 불러오기";
      button.addEventListener("click", () => loadDirectory(node, { append: true }));
      more.append(button);
      list.append(more);
    }
    details.append(list);
    item.append(details);
    if (shouldOpen && !node.loaded && !node.loading && !node.loadError && !node.loadQueued) {
      node.loadQueued = true;
      window.queueMicrotask(() => {
        node.loadQueued = false;
        if (!node.loaded && !node.loading && !node.loadError) loadDirectory(node);
      });
    }
    return item;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "file-row";
  button.dataset.path = node.path;
  button.dataset.active = String(state.activeFile?.path === node.path);
  button.disabled = !node.editable;
  button.title = node.editable ? node.path : `${node.path}(이 형식은 표시만 가능하며 편집할 수 없습니다)`;
  button.innerHTML = iconSvg("file");

  const label = document.createElement("span");
  label.className = "tree-label";
  label.textContent = node.name;
  button.append(label);

  const extension = document.createElement("span");
  extension.className = "file-ext";
  extension.textContent = fileExtension(node.name);
  button.append(extension);
  if (node.editable) {
    button.addEventListener("click", () => openFile(node.path));
  }
  item.append(button);
  return item;
}

function mergeDirectoryEntries(node, entries, append) {
  if (!append) {
    node.children = entries;
    return;
  }
  const existingPaths = new Set(node.children.map((entry) => entry.path));
  node.children.push(...entries.filter((entry) => !existingPaths.has(entry.path)));
}

async function loadDirectory(node, { append = false } = {}) {
  if (node.loading) return;
  node.loading = true;
  node.loadError = "";
  renderTree();
  try {
    const cursor = append && node.nextCursor ? `&cursor=${encodeURIComponent(node.nextCursor)}` : "";
    const page = await requestJson(`/api/tree?path=${encodeURIComponent(node.path)}${cursor}`);
    mergeDirectoryEntries(node, page.entries, append);
    node.nextCursor = page.nextCursor;
    node.loaded = true;
  } catch (error) {
    node.loadError = error.message;
    showToast(error.message, "error");
  } finally {
    node.loading = false;
    renderLoadedFileCount();
    renderTree();
  }
}

function loadedFileCount() {
  const paths = new Set();
  function visit(node) {
    if (node.type === "file") {
      paths.add(node.path);
      return;
    }
    node.children.forEach(visit);
  }
  state.workspace?.libraries.forEach(visit);
  state.workspace?.projects.forEach(visit);
  return paths.size;
}

function renderLoadedFileCount() {
  if (!state.workspace) return;
  const count = loadedFileCount();
  elements.fileCount.textContent = count ? `${formatNumber(count)}+` : "필요할 때 불러옴";
  elements.fileCount.title = "폴더를 펼칠 때 원고를 불러옵니다. 전체 작업 공간을 미리 읽지 않습니다";
}

// 현재 강조 행만 바꾸고 트리 전체를 재생성하지 않는다. 재생성하면 살펴보던 디렉터리가 모두 접힌다.
function syncActiveRow() {
  const activePath = state.activeFile?.path;
  elements.fileTree.querySelectorAll(".file-row").forEach((row) => {
    row.dataset.active = String(row.dataset.path === activePath);
  });
}

function searchTruncationMessage() {
  const status = state.searchTruncation;
  if (!status) return "";
  const messages = [];
  if (status.byResults) {
    messages.push(
      `검색 결과가 ${formatNumber(status.limits.maxResults)}개를 넘어 먼저 찾은 일부만 표시합니다. 파일명을 더 구체적으로 입력하세요`,
    );
  }
  if (status.byNodes) {
    messages.push(
      `검색 항목 수가 ${formatNumber(status.limits.maxNodes)}개 한도에 도달해 나머지 폴더는 확인하지 못했습니다. 대상 폴더를 직접 펼쳐 찾으세요`,
    );
  }
  if (status.byDepth) {
    messages.push(
      `일부 폴더는 깊이가 ${formatNumber(status.limits.maxDepth)}단계를 넘어 더 안쪽을 검색하지 않았습니다. 다른 프로젝트의 검색은 계속했습니다`,
    );
  }
  if (status.byReadError) {
    const paths = status.scanErrors.map((entry) => entry.path).filter(Boolean);
    const shown = paths.slice(0, 3).join(", ") || "일부 폴더";
    const more = paths.length > 3 ? ` 등 ${formatNumber(paths.length)}곳` : "";
    messages.push(
      `${shown}${more}을(를) 읽을 수 없어 검색 결과가 완전하지 않을 수 있습니다. 폴더 접근 권한이나 외장 드라이브 연결 상태를 확인하세요`,
    );
  }
  return messages.join("；");
}

function renderTree() {
  elements.fileTree.replaceChildren();
  elements.treeLoading.hidden = true;
  const query = state.filter.trim();
  const collection = query
    ? state.searchResults
    : state.workspace?.[state.activeView] || [];

  if (query && state.searching) {
    const message = document.createElement("div");
    message.className = "tree-message";
    const text = document.createElement("p");
    text.textContent = `“${query}” 검색 중…`;
    message.append(text);
    elements.fileTree.append(message);
    return;
  }

  if (!collection.length) {
    const message = document.createElement("div");
    message.className = "tree-message";
    const text = document.createElement("p");
    text.textContent = query
      ? state.searchTruncation
        ? `검색이 끝나지 않아 “${query}”의 존재 여부를 확인하지 못했습니다`
        : `“${query}”을(를) 찾지 못했습니다`
      : state.activeView === "libraries"
        ? "작업 공간에 작품 분석 자료가 없습니다. 작품 분석 스킬을 실행하면 여기에 표시됩니다."
        : "집필 프로젝트를 찾지 못했습니다. 장편은 본문·개요·설정·추적 폴더 중 하나가 있어야 합니다. 단편은 본문.md와 함께 구간개요.md 또는 설정.md가 있어야 합니다.";
    message.append(text);
    elements.fileTree.append(message);
    const truncation = searchTruncationMessage();
    if (query && truncation) {
      const status = document.createElement("div");
      status.className = "tree-message";
      status.setAttribute("role", "status");
      const statusText = document.createElement("p");
      statusText.textContent = truncation;
      status.append(statusText);
      elements.fileTree.append(status);
    }
    return;
  }

  const list = document.createElement("ul");
  collection.forEach((node) => {
    const item = createTreeEntry(node);
    if (item) list.append(item);
  });
  const truncation = searchTruncationMessage();
  if (query && truncation) {
    const status = document.createElement("li");
    status.className = "tree-inline-status";
    status.setAttribute("role", "status");
    status.textContent = truncation;
    list.append(status);
  }
  elements.fileTree.append(list);
}

function truncationMessage(scanErrors = []) {
  const paths = scanErrors.map((entry) => entry.path).filter(Boolean);
  const shown = paths.slice(0, 3).join(", ") || "일부 폴더";
  const more = paths.length > 3 ? ` 등 ${formatNumber(paths.length)}곳` : "";
  return `${shown}${more}을(를) 읽을 수 없어 해당 원고를 표시하지 못했습니다. 폴더 접근 권한과 외장 드라이브 연결을 확인한 뒤 목록을 새로고침하세요.`;
}

function renderTruncationNotice(limits, scanErrors) {
  if (!limits?.truncated) {
    elements.truncationNotice?.remove();
    elements.truncationNotice = null;
    return;
  }
  if (!elements.truncationNotice) {
    const notice = document.createElement("div");
    notice.id = "treeTruncationNotice";
    notice.className = "tree-message";
    notice.setAttribute("role", "status");
    notice.append(document.createElement("p"));
    elements.treePanel.insertBefore(notice, elements.fileTree);
    elements.truncationNotice = notice;
  }
  elements.truncationNotice.querySelector("p").textContent = truncationMessage(scanErrors);
}

function renderWorkspace() {
  const { workspace, stats, libraries, projects, limits, scanErrors } = state.workspace;
  elements.workspaceName.textContent = workspace.name;
  elements.workspacePath.textContent = workspace.path;
  elements.workspacePath.title = workspace.path;
  elements.libraryCount.textContent = formatNumber(stats.libraries);
  elements.projectCount.textContent = formatNumber(stats.projects);
  renderLoadedFileCount();
  elements.librariesBadge.textContent = formatNumber(libraries.length);
  elements.projectsBadge.textContent = formatNumber(projects.length);
  renderTruncationNotice(limits, scanErrors);
  renderTree();
}

async function loadWorkspace({ announce = false } = {}) {
  window.clearTimeout(state.searchTimer);
  state.searchSequence += 1;
  elements.treeLoading.hidden = false;
  elements.fileTree.replaceChildren();
  setConnection("", "연결 중");
  try {
    state.workspace = await requestJson("/api/workspace");
    state.searchResults = [];
    state.searchTruncation = null;
    state.searching = Boolean(state.filter.trim());
    renderWorkspace();
    if (!state.restored) await restoreViewState();
    if (state.filter.trim()) scheduleSearch();
    if (announce) showToast("작업 공간 목록을 새로고침했습니다");
  } catch (error) {
    elements.treeLoading.hidden = true;
    const message = document.createElement("div");
    message.className = "tree-message";
    const text = document.createElement("p");
    text.textContent = error.message;
    message.append(text);
    elements.fileTree.replaceChildren(message);
    showToast(error.message, "error");
  }
}

function confirmDiscard() {
  return !state.dirty || window.confirm("현재 원고에 저장하지 않은 변경 사항이 있습니다. 변경 사항을 버리고 다른 파일을 여시겠습니까?");
}

function setDirty(dirty) {
  state.dirty = dirty;
  elements.dirtyStatus.dataset.state = dirty ? "dirty" : "saved";
  elements.dirtyStatus.querySelector("span:last-child").textContent = dirty ? "저장 필요" : "저장됨";
  syncActionAvailability();
}

function syncActionAvailability() {
  const busy = state.loadingFile || state.saving || state.deleting;
  elements.saveButton.disabled = busy || !state.dirty;
  elements.deleteButton.disabled = busy || !state.activeFile;
}

function setSaving(saving) {
  state.saving = saving;
  elements.dirtyStatus.dataset.state = saving ? "saving" : state.dirty ? "dirty" : "saved";
  elements.dirtyStatus.querySelector("span:last-child").textContent = saving
    ? "저장 중"
    : state.dirty
      ? "저장 필요"
      : "저장됨";
  syncActionAvailability();
}

function renderBreadcrumbs(path) {
  elements.breadcrumbs.replaceChildren();
  path.split("/").forEach((part, index, parts) => {
    const label = document.createElement("span");
    label.textContent = part;
    elements.breadcrumbs.append(label);
    if (index < parts.length - 1) {
      const divider = document.createElement("i");
      divider.textContent = "／";
      elements.breadcrumbs.append(divider);
    }
  });
}

function updateDocumentMeta() {
  if (!state.activeFile) return;
  const content = elements.editorInput.value;
  elements.documentMeta.textContent = [
    formatBytes(currentByteSize()),
    `${formatNumber(countCharacters(content))}자`,
    fileExtension(state.activeFile.name).toUpperCase(),
  ].join("  ·  ");
}

function updateCursorPosition() {
  const content = elements.editorInput.value;
  const caret = elements.editorInput.selectionStart;
  const before = content.slice(0, caret);
  const lines = before.split("\n");
  updateActiveGutterLine(lines.length);
  elements.cursorPosition.textContent = `${lines.length}행, ${[...lines.at(-1)].length + 1}열`;
}

function updateActiveGutterLine(currentLine) {
  const prevActive = elements.lineNumbersGutter.querySelector(".gutter-line.active");
  if (prevActive && prevActive.dataset.line === String(currentLine)) return;
  if (prevActive) prevActive.classList.remove("active");
  const target = elements.lineNumbersGutter.querySelector(`.gutter-line[data-line='${currentLine}']`);
  if (target) target.classList.add("active");
}

let lineMirror = null;
function getLineMirror() {
  if (!lineMirror) {
    lineMirror = document.createElement("div");
    lineMirror.className = "editor-line-mirror";
    document.body.appendChild(lineMirror);
  }
  return lineMirror;
}

function updateLineNumbers() {
  if (!state.showLineNumbers || elements.editorContainer.hidden) return;
  const input = elements.editorInput;
  const text = input.value;
  const lines = text.split("\n");
  const count = lines.length;

  const style = window.getComputedStyle(input);
  const mirror = getLineMirror();
  mirror.style.fontFamily = style.fontFamily;
  mirror.style.fontSize = style.fontSize;
  mirror.style.fontWeight = style.fontWeight;
  mirror.style.fontStyle = style.fontStyle;
  // textarea처럼 단위 없는 행 높이를 써 픽셀 소수점 반올림 오차가 장문에서 누적되지 않게 한다.
  mirror.style.lineHeight = String(parseFloat(style.lineHeight) / parseFloat(style.fontSize));
  mirror.style.letterSpacing = style.letterSpacing;
  mirror.style.wordSpacing = style.wordSpacing;
  mirror.style.textTransform = style.textTransform;
  mirror.style.textIndent = style.textIndent;
  mirror.style.whiteSpace = "pre-wrap";
  mirror.style.wordBreak = style.wordBreak;
  mirror.style.overflowWrap = "break-word";
  mirror.style.tabSize = style.tabSize || "4";

  const padLeft = parseFloat(style.paddingLeft) || 0;
  const padRight = parseFloat(style.paddingRight) || 0;
  const innerWidth = input.clientWidth - padLeft - padRight;
  if (innerWidth <= 0) return;
  mirror.style.width = `${innerWidth}px`;

  mirror.innerHTML = lines.map((line) => `<div>${escapeHtml(line) || "&#8203;"}</div>`).join("");

  const caret = input.selectionStart || 0;
  const beforeCaret = text.slice(0, caret);
  const activeLineIndex = beforeCaret.split("\n").length - 1;

  elements.lineNumbersGutter.style.paddingTop = style.paddingTop;
  elements.lineNumbersGutter.style.paddingBottom = style.paddingBottom;
  elements.lineNumbersGutter.style.lineHeight = style.lineHeight;
  const children = mirror.children;
  const rows = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const isActive = i === activeLineIndex ? " active" : "";
    const row = document.createElement("div");
    row.className = `gutter-line${isActive}`;
    row.dataset.line = String(i + 1);
    row.textContent = String(i + 1);
    row.style.height = `${children[i].getBoundingClientRect().height}px`;
    rows.append(row);
  }
  elements.lineNumbersGutter.replaceChildren(rows);
  elements.lineNumbersGutter.scrollTop = input.scrollTop;
}

let lineNumbersFrame = null;
function scheduleLineNumbers() {
  if (lineNumbersFrame !== null) return;
  lineNumbersFrame = window.requestAnimationFrame(() => {
    lineNumbersFrame = null;
    updateLineNumbers();
  });
}

function setLineNumbersVisible(visible) {
  state.showLineNumbers = visible;
  elements.editorBody.classList.toggle("show-line-numbers", visible);
  elements.lineNumbersButton.setAttribute("aria-pressed", String(visible));
  scheduleLineNumbers();
  syncViewState();
}

function viewStateKey() {
  return `story_dashboard_view:${state.workspace.workspace.path}`;
}

function syncViewState() {
  if (!state.restored) return;
  const saved = {
    view: state.activeView,
    file: state.activeFile?.path || null,
    mode: state.mode,
    showLineNumbers: state.showLineNumbers,
  };
  try {
    localStorage.setItem(viewStateKey(), JSON.stringify(saved));
  } catch {}
  const url = new URL(window.location.href);
  url.searchParams.set("view", saved.view);
  if (saved.file) {
    url.searchParams.set("file", saved.file);
    url.searchParams.set("mode", saved.mode);
  } else {
    url.searchParams.delete("file");
    url.searchParams.delete("mode");
  }
  window.history.replaceState(null, "", url);
}

async function restoreViewState() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(viewStateKey())) || {};
  } catch {}
  const params = new URLSearchParams(window.location.search);
  // 명시적 링크는 이 작업 공간에서 마지막으로 연 원고보다 우선한다.
  const linked = ["view", "file", "mode"].some((key) => params.has(key));
  const file = linked ? params.get("file") : saved.file;
  const mode = (linked ? params.get("mode") : saved.mode) === "preview" ? "preview" : "edit";
  const requestedView = linked ? params.get("view") : saved.view;
  const defaultView = state.workspace.libraries.length ? "libraries" : "projects";
  const view = ["libraries", "projects"].includes(requestedView)
    ? requestedView
    : typeof file === "string" ? deduceViewForPath(file) : defaultView;
  setLineNumbersVisible(saved.showLineNumbers !== false);
  setMode(mode);
  if (typeof file === "string" && file) await openFile(file, { force: true });
  setActiveView(view);
  state.restored = true;
  syncViewState();
}

function expandParentDirs(filePath) {
  if (!filePath) return;
  const parts = filePath.split("/");
  let current = "";
  for (let i = 0; i < parts.length - 1; i++) {
    current = current ? `${current}/${parts[i]}` : parts[i];
    state.expandedDirs.add(current);
    state.collapsedDirs.delete(current);
  }
}

function deduceViewForPath(filePath) {
  if (!state.workspace || !filePath) return state.activeView;
  const containsFile = ({ path }) => path === "." || filePath.startsWith(`${path}/`);
  if (state.workspace.libraries.some(containsFile)) {
    return "libraries";
  }
  if (state.workspace.projects.some(containsFile)) {
    return "projects";
  }
  return state.activeView;
}

async function openFile(path, { force = false } = {}) {
  if (state.loadingFile || (!force && !confirmDiscard())) return;
  state.loadingFile = true;
  syncActionAvailability();
  elements.fileTree.setAttribute("aria-busy", "true");
  try {
    const file = await requestJson(`/api/file?path=${encodeURIComponent(path)}`);
    const normalized = normalizeEol(file.content);
    file.eol = detectEol(file.content);
    file.content = normalized;
    state.activeFile = file;
    state.originalContent = normalized;
    elements.editorInput.value = normalized;
    elements.editorTitle.textContent = file.name;
    renderBreadcrumbs(file.path);
    setDirty(false);
    expandParentDirs(file.path);
    setActiveView(deduceViewForPath(file.path));
    setMode(state.mode);
    updateDocumentMeta();
    updateCursorPosition();
    elements.editorEmpty.hidden = true;
    elements.editorWorkspace.hidden = false;
    document.body.classList.add("document-open");
    syncActiveRow();
    syncViewState();
    scheduleLineNumbers();
    if (state.mode === "edit") window.requestAnimationFrame(() => elements.editorInput.focus());
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    state.loadingFile = false;
    syncActionAvailability();
    elements.fileTree.removeAttribute("aria-busy");
  }
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(value) {
  return value
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
}

function markdownToSafeHtml(markdown) {
  const lines = escapeHtml(markdown).replaceAll("\r\n", "\n").split("\n");
  const output = [];
  let inCode = false;
  let codeLines = [];
  let codeStartLine = 1;
  let listType = null;

  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;
    if (line.trim().startsWith("```")) {
      closeList();
      if (inCode) {
        output.push(`<div class="preview-code-block" data-line="${codeStartLine}"><pre><code>${codeLines.join("\n")}</code></pre></div>`);
        codeLines = [];
      } else {
        codeStartLine = lineNum;
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      output.push(`<h${level} data-line="${lineNum}">${inlineMarkdown(heading[2])}</h${level}>`);
    } else if (unordered || ordered) {
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        output.push(`<${listType}>`);
      }
      output.push(`<li data-line="${lineNum}">${inlineMarkdown((unordered || ordered)[1])}</li>`);
    } else if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      closeList();
      output.push(`<hr data-line="${lineNum}">`);
    } else if (line.startsWith("&gt; ")) {
      closeList();
      output.push(`<blockquote data-line="${lineNum}">${inlineMarkdown(line.slice(5))}</blockquote>`);
    } else if (line.trim()) {
      closeList();
      output.push(`<p data-line="${lineNum}">${inlineMarkdown(line)}</p>`);
    } else {
      closeList();
    }
  }
  if (inCode) output.push(`<div class="preview-code-block" data-line="${codeStartLine}"><pre><code>${codeLines.join("\n")}</code></pre></div>`);
  closeList();
  return output.join("");
}

function setMode(mode) {
  state.mode = mode;
  elements.modeButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
  });
  const previewing = mode === "preview";
  elements.editorContainer.hidden = previewing;
  elements.previewPane.hidden = !previewing;
  if (previewing) {
    elements.previewPane.innerHTML = markdownToSafeHtml(elements.editorInput.value);
  } else {
    window.requestAnimationFrame(() => elements.editorInput.focus());
  }
  scheduleLineNumbers();
  syncViewState();
}

async function saveFile() {
  if (!state.activeFile || !state.dirty || state.saving || state.deleting) return;
  // 요청 전에 식별 정보와 본문 스냅샷을 만든다. 저장 중 작가가 파일을 바꾸거나 계속 입력할 수 있으므로
  // 마무리에서는 실제로 전송한 원고만 갱신하고 다른 원고에 반영하면 안 된다.
  const file = state.activeFile;
  const sent = elements.editorInput.value;
  setSaving(true);
  try {
    const saved = await requestJson("/api/file", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: file.path,
        content: applyEol(sent, file.eol),
        expectedVersion: file.version,
      }),
    });
    file.mtimeMs = saved.mtimeMs;
    file.version = saved.version;
    file.size = saved.size;
    showToast(`《${file.name}》을(를) 저장했습니다`);
    if (state.activeFile !== file) return;
    state.originalContent = sent;
    // 저장 중 입력한 글자는 여전히 미저장 변경이다. 이번 결과로 저장 완료 상태로 덮지 않는다.
    setDirty(elements.editorInput.value !== sent);
    updateDocumentMeta();
  } catch (error) {
    if (state.activeFile !== file) {
      showToast(`《${file.name}》 저장 실패: ${error.message}`, "error");
      return;
    }
    setDirty(true);
    if (error instanceof ApiError && error.status === 409) {
      elements.conflictDialog.showModal();
    } else {
      showToast(error.message, "error");
    }
  } finally {
    setSaving(false);
  }
}

async function deleteFile() {
  if (!state.activeFile || state.saving || state.deleting) return;
  const file = state.activeFile;
  const warning = state.dirty
    ? `《${file.name}》에 저장하지 않은 변경 사항이 있습니다. 삭제하면 디스크의 파일과 변경 사항이 영구히 사라지며 되돌릴 수 없습니다. 삭제하시겠습니까?`
    : `《${file.name}》을(를) 영구 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`;
  if (!window.confirm(warning)) return;

  state.deleting = true;
  syncActionAvailability();
  try {
    await requestJson("/api/file", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: file.path,
        expectedVersion: file.version,
      }),
    });
    state.activeFile = null;
    state.originalContent = "";
    elements.editorInput.value = "";
    elements.editorWorkspace.hidden = true;
    elements.editorEmpty.hidden = false;
    document.body.classList.remove("document-open");
    setDirty(false);
    syncViewState();
    await loadWorkspace();
    showToast(`《${file.name}》을(를) 삭제했습니다`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    state.deleting = false;
    syncActionAvailability();
  }
}

async function searchWorkspace(query, sequence) {
  state.searching = true;
  renderTree();
  try {
    const result = await requestJson(
      `/api/search?q=${encodeURIComponent(query)}&scope=${encodeURIComponent(state.activeView)}`,
    );
    if (sequence !== state.searchSequence) return;
    state.searchResults = result.results;
    state.searchTruncation = result.truncated
      ? {
          ...(result.truncation || {
            byResults: true,
            byNodes: false,
            byDepth: false,
            byReadError: false,
          }),
          scanErrors: result.scanErrors || [],
          limits: result.limits,
        }
      : null;
  } catch (error) {
    if (sequence !== state.searchSequence) return;
    state.searchResults = [];
    state.searchTruncation = null;
    showToast(error.message, "error");
  } finally {
    if (sequence === state.searchSequence) {
      state.searching = false;
      renderTree();
    }
  }
}

function scheduleSearch() {
  window.clearTimeout(state.searchTimer);
  const query = state.filter.trim();
  state.searchSequence += 1;
  const sequence = state.searchSequence;
  if (!query) {
    state.searching = false;
    state.searchResults = [];
    state.searchTruncation = null;
    renderTree();
    return;
  }
  state.searching = true;
  renderTree();
  state.searchTimer = window.setTimeout(() => searchWorkspace(query, sequence), 180);
}

function setActiveView(view) {
  state.activeView = view;
  elements.archiveTabs.forEach((tab) => {
    const selected = tab.dataset.view === view;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  elements.treePanel.setAttribute(
    "aria-labelledby",
    view === "libraries" ? "librariesTab" : "projectsTab",
  );
  if (state.filter.trim()) {
    scheduleSearch();
  } else {
    renderTree();
  }
  syncViewState();
}

elements.archiveTabs.forEach((tab) => {
  tab.addEventListener("click", () => setActiveView(tab.dataset.view));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const current = elements.archiveTabs.indexOf(event.currentTarget);
    const next = elements.archiveTabs.at(
      (current + direction + elements.archiveTabs.length) % elements.archiveTabs.length,
    );
    setActiveView(next.dataset.view);
    next.focus();
  });
});

elements.treeSearch.addEventListener("input", (event) => {
  state.filter = event.currentTarget.value;
  scheduleSearch();
});

elements.treeSearch.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.currentTarget.value = "";
    state.filter = "";
    scheduleSearch();
  }
});

elements.refreshButton.addEventListener("click", () => loadWorkspace({ announce: true }));

elements.themeButton.addEventListener("click", () => {
  themeChoice = effectiveTheme() === "dark" ? "light" : "dark";
  try {
    localStorage.setItem(THEME_KEY, themeChoice);
  } catch {}
  applyTheme();
});

systemDark.addEventListener("change", applyTheme);
elements.mobileBackButton.addEventListener("click", () => {
  document.body.classList.remove("document-open");
  window.requestAnimationFrame(() => elements.treeSearch.focus());
});
elements.saveButton.addEventListener("click", saveFile);
elements.deleteButton.addEventListener("click", deleteFile);

elements.editorInput.addEventListener("input", () => {
  setDirty(elements.editorInput.value !== state.originalContent);
  updateDocumentMeta();
  updateCursorPosition();
  scheduleLineNumbers();
});

elements.editorInput.addEventListener("scroll", () => {
  elements.lineNumbersGutter.scrollTop = elements.editorInput.scrollTop;
}, { passive: true });

elements.lineNumbersButton.addEventListener("click", () => {
  setLineNumbersVisible(!state.showLineNumbers);
});

new ResizeObserver(scheduleLineNumbers).observe(elements.editorInput);
document.fonts.ready.then(scheduleLineNumbers);

["click", "keyup", "select"].forEach((eventName) => {
  elements.editorInput.addEventListener(eventName, updateCursorPosition);
});

elements.modeButtons.forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

elements.conflictDialog.addEventListener("close", () => {
  if (elements.conflictDialog.returnValue === "reload" && state.activeFile) {
    openFile(state.activeFile.path, { force: true });
  }
});

document.addEventListener("keydown", (event) => {
  const modifier = event.metaKey || event.ctrlKey;
  if (modifier && event.key.toLocaleLowerCase() === "s") {
    event.preventDefault();
    saveFile();
  }
  if (modifier && event.key.toLocaleLowerCase() === "k") {
    event.preventDefault();
    elements.treeSearch.focus();
    elements.treeSearch.select();
  }
});

window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

loadWorkspace();
