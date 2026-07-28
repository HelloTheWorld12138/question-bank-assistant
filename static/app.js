const state = {
  options: null,
  selected: new Set(),
  draftReady: false,
  wordDraftId: "",
  wordDraftImages: [],
  uploadItems: [],
  formulaItems: [],
  approvedFormulaImages: new Set(),
  editingId: "",
  editingImages: [],
  resultItems: new Map(),
  displayLabels: new Map(),
  modelSettings: null,
  modelProviders: [],
  importTask: null,
  assistantRecommendations: [],
  imageEditor: null,
};

const $ = (id) => document.getElementById(id);
const MANUAL_SECTION_IDS = ["questionText", "answerText", "analysisText"];
const EDIT_SECTION_IDS = ["editQuestionText", "editAnswerText", "editAnalysisText"];
const RICH_CONTENT_RE =
  /(!\[[^\]]*\]\([^)]+\)(?:\{[^}\n]*\})?|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$[^$\n]+\$|\\\([^)\n]*\\\))/g;
const INLINE_FORMAT_RE =
  /(<sub>[^<>]*<\/sub>|<sup>[^<>]*<\/sup>|\*\*\*[^*\n]+\*\*\*|___[^_\n]+___|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)/gi;
const METAFILE_RE = /\.(wmf|emf)(?:\?.*)?$/i;
let metafileConverterPromise = null;

const WORKSPACE_VIEWS = new Set([
  "import",
  "manual",
  "library",
  "select",
  "export",
  "settings",
]);
const VIEW_MODULES = {
  import: "entry",
  manual: "entry",
  library: "library",
  settings: "settings",
  select: "export",
  export: "export",
};
const MODULE_DEFAULT_VIEWS = {
  entry: "import",
  library: "library",
  export: "select",
};
const moduleLastView = { ...MODULE_DEFAULT_VIEWS };
let taxonomyMode = "block";

function switchWorkspaceView(requestedView, { updateHash = true } = {}) {
  const view = WORKSPACE_VIEWS.has(requestedView) ? requestedView : "import";
  const module = VIEW_MODULES[view];
  moduleLastView[module] = view;
  for (const section of document.querySelectorAll("[data-workspace-view]")) {
    section.classList.toggle("is-active", section.dataset.workspaceView === view);
  }
  for (const button of document.querySelectorAll(".subtask-nav-item")) {
    button.classList.toggle("is-active", button.dataset.workspaceTarget === view);
  }
  for (const button of document.querySelectorAll(".module-nav-item")) {
    button.classList.toggle("is-active", button.dataset.moduleTarget === module);
  }
  for (const menu of document.querySelectorAll(".subtask-menu")) {
    menu.classList.toggle("is-active", menu.dataset.moduleMenu === module);
  }
  if (updateHash) {
    history.replaceState(null, "", `#${view}`);
  }
  window.scrollTo({ top: 0, behavior: "auto" });
}

function bindWorkspaceNavigation() {
  for (const button of document.querySelectorAll("[data-workspace-target]")) {
    button.addEventListener("click", () => switchWorkspaceView(button.dataset.workspaceTarget));
  }
  for (const button of document.querySelectorAll("[data-module-target]")) {
    button.addEventListener("click", () => {
      const module = button.dataset.moduleTarget;
      switchWorkspaceView(moduleLastView[module] || MODULE_DEFAULT_VIEWS[module]);
    });
  }
  const initialView = window.location.hash.replace("#", "");
  switchWorkspaceView(initialView || "import", { updateHash: false });
}

function appendUnescapedText(container, text) {
  container.appendChild(document.createTextNode(String(text || "").replace(/\\([*_])/g, "$1")));
}

function appendInlineFormattedLine(container, text) {
  const source = String(text || "");
  let lastIndex = 0;
  for (const match of source.matchAll(INLINE_FORMAT_RE)) {
    const index = Number(match.index);
    if (index > 0 && source[index - 1] === "\\") continue;
    appendUnescapedText(container, source.slice(lastIndex, index));
    const token = match[0];
    let element;
    let content;
    if (/^<sub>/i.test(token)) {
      element = document.createElement("sub");
      content = token.slice(5, -6);
    } else if (/^<sup>/i.test(token)) {
      element = document.createElement("sup");
      content = token.slice(5, -6);
    } else if (
      (token.startsWith("***") && token.endsWith("***")) ||
      (token.startsWith("___") && token.endsWith("___"))
    ) {
      element = document.createElement("strong");
      const emphasis = document.createElement("em");
      content = token.slice(3, -3);
      emphasis.textContent = content;
      element.appendChild(emphasis);
      container.appendChild(element);
      lastIndex = index + token.length;
      continue;
    } else if (
      (token.startsWith("**") && token.endsWith("**")) ||
      (token.startsWith("__") && token.endsWith("__"))
    ) {
      element = document.createElement("strong");
      content = token.slice(2, -2);
    } else {
      element = document.createElement("em");
      content = token.slice(1, -1);
    }
    element.textContent = content;
    container.appendChild(element);
    lastIndex = index + token.length;
  }
  appendUnescapedText(container, source.slice(lastIndex));
}

function appendFormattedText(container, text) {
  const lines = String(text || "").split("\n");
  lines.forEach((line, index) => {
    if (index) container.appendChild(document.createElement("br"));
    appendInlineFormattedLine(container, line);
  });
}

function isOptionLine(line) {
  return /^[ \t]*[A-HＡ-Ｈ](?:[．.、:：)）]|\s+)/.test(String(line || ""));
}

function isStandaloneContentBlock(line) {
  return /^\s*(?:!\[[^\]]*\]\([^)]+\)(?:\{[^}\n]*\})?|\$\$|\\\[|\\\])\s*$/.test(
    String(line || ""),
  );
}

function optionOrder(label) {
  const fullwidth = "ＡＢＣＤＥＦＧＨ";
  const fullwidthIndex = fullwidth.indexOf(label);
  if (fullwidthIndex >= 0) return fullwidthIndex;
  return String(label || "").toUpperCase().charCodeAt(0) - "A".charCodeAt(0);
}

function inlineOptionMatches(line) {
  const source = String(line || "");
  const markerPattern =
    /(^|(?:\t+|[ \u00a0]+))([A-HＡ-Ｈ])([．.、:：)）]|\s+)/g;
  return [...source.matchAll(markerPattern)];
}

function consecutiveOptionOrders(matches) {
  const orders = matches.map((match) => optionOrder(match[2]));
  const consecutive = orders
    .slice(1)
    .every((order, index) => order === orders[index] + 1);
  return consecutive ? orders : [];
}

function groupedOptionRowOrders(line) {
  const source = String(line || "");
  const matches = inlineOptionMatches(source);
  if (matches.length < 2 || source.slice(0, matches[0].index).trim()) return [];
  if (matches.some((match) => !match[3].trim())) return [];
  return consecutiveOptionOrders(matches);
}

function groupedOptionRowIndexes(prepared) {
  const contentIndexes = prepared
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !item.protected && item.line.trim())
    .map(({ index }) => index);
  const grouped = new Set();
  contentIndexes.slice(0, -1).forEach((leftIndex, position) => {
    const rightIndex = contentIndexes[position + 1];
    if (rightIndex - leftIndex > 2) return;
    if (prepared.slice(leftIndex + 1, rightIndex).some((item) => item.protected)) return;
    const leftOrders = groupedOptionRowOrders(prepared[leftIndex].line);
    const rightOrders = groupedOptionRowOrders(prepared[rightIndex].line);
    const combined = [...leftOrders, ...rightOrders];
    const completeSequence =
      leftOrders.length &&
      rightOrders.length &&
      combined.length >= 4 &&
      combined.every((order, index) => order === index);
    if (completeSequence) {
      grouped.add(leftIndex);
      grouped.add(rightIndex);
    }
  });
  return grouped;
}

function splitInlineOptions(line, groupedRow = false) {
  const source = String(line || "");
  const matches = inlineOptionMatches(source);
  if (matches.length < 2) return [source];

  const orders = consecutiveOptionOrders(matches);
  if (!orders.length || (orders[0] !== 0 && !groupedRow)) return [source];
  if (groupedRow && matches.some((match) => !match[3].trim())) return [source];
  const hasClearSeparator = matches
    .slice(1)
    .some((match) => match[1].includes("\t") || match[1].length >= 2);
  if (!groupedRow && !hasClearSeparator) {
    const hasExplicitMarkers = matches.every((match) => match[3].trim());
    if (matches.length < 3 || !hasExplicitMarkers) return [source];
  }

  const result = [];
  const leadingText = source.slice(0, matches[0].index).trim();
  if (leadingText) result.push(leadingText);
  matches.forEach((match, index) => {
    const start = match.index + match[1].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : source.length;
    const option = source.slice(start, end).trim();
    if (option) result.push(option);
  });
  return result;
}

function normalizeLineBreaks(value) {
  const source = String(value || "").replace(/\r\n?/g, "\n");
  const prepared = [];
  let inFence = false;
  const rawLines = source.split("\n");
  rawLines.forEach((rawLine, index) => {
    if (/^\s*(```|~~~)/.test(rawLine)) {
      prepared.push({ line: rawLine, protected: true });
      inFence = !inFence;
      return;
    }
    if (inFence) {
      prepared.push({ line: rawLine, protected: true });
      return;
    }
    let line = rawLine.replace(/[ \t]+$/, "");
    if (/^[ \t]*>[ \t]*$/.test(line)) {
      const previousLine =
        [...rawLines.slice(0, index)].reverse().find((candidate) => candidate.trim()) || "";
      const nextLine =
        rawLines.slice(index + 1).find((candidate) => candidate.trim()) || "";
      const quotedOption = /^([ \t]*)>\s*([A-HＡ-Ｈ](?:[．.、:：)）]|\s+).*)$/;
      if (quotedOption.test(previousLine) || quotedOption.test(nextLine)) return;
    }
    line = line.replace(
      /^([ \t]*)>\s*([A-HＡ-Ｈ](?:[．.、:：)）]|\s+).*)$/,
      "$1$2",
    );
    prepared.push({ line, protected: false });
  });

  const groupedRows = groupedOptionRowIndexes(prepared);
  const expanded = [];
  prepared.forEach((item, index) => {
    if (item.protected) {
      expanded.push(item);
      return;
    }
    splitInlineOptions(item.line, groupedRows.has(index)).forEach((optionLine) => {
      expanded.push({ line: optionLine, protected: false });
    });
  });

  const result = [];
  expanded.forEach((item, index) => {
    if (item.protected || item.line.trim()) {
      result.push(item.line);
      return;
    }
    const nextItem = expanded.slice(index + 1).find((candidate) => {
      return candidate.protected || candidate.line.trim();
    });
    const previousLine = [...result].reverse().find((candidate) => candidate.trim()) || "";
    if (
      nextItem &&
      isOptionLine(nextItem.line) &&
      previousLine &&
      !isStandaloneContentBlock(previousLine)
    ) {
      return;
    }
    if (result.length && !result[result.length - 1].trim()) return;
    result.push("");
  });
  return result.join("\n").trim();
}

function normalizeFields(fieldIds) {
  for (const fieldId of fieldIds) {
    const field = $(fieldId);
    if (!field) continue;
    field.value = normalizeLineBreaks(field.value);
  }
}

function uploadItemForToken(token) {
  return state.uploadItems.find((item) => item.token === token);
}

function safePreviewImageUrl(url) {
  const raw = String(url || "").trim();
  if (raw.startsWith("upload-image://")) {
    return uploadItemForToken(raw)?.previewUrl || "";
  }
  if (
    raw.startsWith("/draft-assets/") ||
    raw.startsWith("/assets/") ||
    raw.startsWith("../assets/") ||
    raw.startsWith("./assets/")
  ) {
    return raw;
  }
  return "";
}

async function metafileConverter() {
  if (!metafileConverterPromise) {
    metafileConverterPromise = import("./vendor/emf-converter/index.mjs");
  }
  return metafileConverterPromise;
}

async function convertMetafileUrl(url, filename) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("无法读取旧版图片");
  const buffer = await response.arrayBuffer();
  const converter = await metafileConverter();
  const options = {
    dpiScale: 2,
    maxCanvasDimension: 4096,
    fontFamilyMap: {
      "times new roman": "Times New Roman",
      symbol: "serif",
      "mt extra": "serif",
    },
  };
  const dataUrl = String(filename || url).toLowerCase().includes(".emf")
    ? await converter.convertEmfToDataUrl(buffer, undefined, undefined, options)
    : await converter.convertWmfToDataUrl(buffer, undefined, undefined, options);
  if (!dataUrl) throw new Error("旧版图片转换失败");
  const blob = await (await fetch(dataUrl)).blob();
  const outputName = `${String(filename || "公式").replace(/\.(wmf|emf)$/i, "")}.png`;
  return {
    file: new File([blob], outputName, { type: "image/png" }),
    previewUrl: dataUrl,
    outputName,
  };
}

function replaceAllLiteral(value, replacements) {
  let result = String(value || "");
  for (const [original, replacement] of replacements.entries()) {
    result = result.split(original).join(replacement);
  }
  return result;
}

async function runWithConcurrency(items, limit, handler) {
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      await handler(items[index], index);
    }
  });
  await Promise.all(workers);
}

function clearConvertedWordUploads() {
  for (const item of state.uploadItems.filter((candidate) => candidate.source === "word-conversion")) {
    if (item.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(item.previewUrl);
  }
  state.uploadItems = state.uploadItems.filter((item) => item.source !== "word-conversion");
}

async function normalizeManualMetafiles(data, onProgress = () => {}) {
  const metafiles = (data.images || []).filter((item) => METAFILE_RE.test(item.name || item.url));
  if (!metafiles.length) return { converted: 0, failed: [] };
  clearConvertedWordUploads();
  const formulaUrls = new Set((data.formula_items || []).map((item) => item.url));
  const replacements = new Map();
  const convertedByUrl = new Map();
  const failed = [];
  let finished = 0;
  await runWithConcurrency(metafiles, 4, async (image) => {
    try {
      const converted = await convertMetafileUrl(image.url, image.name);
      const uniquePart = window.crypto?.randomUUID?.() || `${Date.now()}-${finished}`;
      const token = `upload-image://${uniquePart}`;
      const uploadItem = {
        file: converted.file,
        token,
        previewUrl: converted.previewUrl,
        source: "word-conversion",
        autoFormula: formulaUrls.has(image.url),
      };
      state.uploadItems.push(uploadItem);
      replacements.set(image.url, token);
      convertedByUrl.set(image.url, { ...converted, token });
    } catch (error) {
      failed.push(image.name);
    } finally {
      finished += 1;
      onProgress(finished, metafiles.length);
    }
  });

  for (const name of ["markdown", "text_markdown", "raw_markdown"]) {
    if (name in data) data[name] = replaceAllLiteral(data[name], replacements);
  }
  for (const name of ["question", "answer", "analysis"]) {
    if (data.sections && name in data.sections) {
      data.sections[name] = replaceAllLiteral(data.sections[name], replacements);
    }
  }
  data.images = (data.images || []).filter((item) => !convertedByUrl.has(item.url));
  data.formula_items = (data.formula_items || []).map((item) => {
    const converted = convertedByUrl.get(item.url);
    if (!converted) return item;
    return {
      ...item,
      url: converted.token,
      name: converted.outputName,
      relative_path: converted.outputName,
      confirmed: true,
      auto_kept: true,
      ocr_error: "",
    };
  });
  return { converted: convertedByUrl.size, failed };
}

function importTaskMetafiles(task) {
  const items = [];
  for (const draft of task?.drafts || []) {
    for (const image of draft.images || []) {
      if (!METAFILE_RE.test(image.name || image.url)) continue;
      items.push({ draft, image });
    }
  }
  return items;
}

async function normalizeImportTaskMetafiles(task, onProgress = () => {}) {
  const metafiles = importTaskMetafiles(task);
  if (!metafiles.length) return { task, converted: 0, failed: [] };

  const prepared = new Array(metafiles.length);
  const failed = [];
  let preparedCount = 0;
  await runWithConcurrency(metafiles, 4, async (entry, index) => {
    try {
      prepared[index] = {
        entry,
        converted: await convertMetafileUrl(entry.image.url, entry.image.name),
      };
    } catch (error) {
      failed.push(entry.image.name);
    } finally {
      preparedCount += 1;
      onProgress(preparedCount, metafiles.length, "convert");
    }
  });

  const preparedItems = prepared.filter(Boolean);
  let uploadedCount = 0;
  let processedUploads = 0;
  for (const item of preparedItems) {
    const form = new FormData();
    form.append("file", item.converted.file);
    const response = await fetch(
      `/api/import/tasks/${encodeURIComponent(task.id)}` +
        `/drafts/${encodeURIComponent(item.entry.draft.id)}` +
        `/images/${encodeURIComponent(item.entry.image.name)}/replace-metafile`,
      { method: "POST", body: form },
    );
    if (!response.ok) {
      failed.push(item.entry.image.name);
    } else {
      uploadedCount += 1;
    }
    processedUploads += 1;
    onProgress(processedUploads, preparedItems.length, "upload");
  }

  const response = await fetch(`/api/import/tasks/${encodeURIComponent(task.id)}`);
  const reloaded = await response.json();
  return {
    task: response.ok ? reloaded : task,
    converted: uploadedCount,
    failed: Array.from(new Set(failed)),
  };
}

function renderMath(container, latex, displayMode = false) {
  const formula = String(latex || "").trim();
  if (!formula) return false;
  const holder = document.createElement(displayMode ? "div" : "span");
  holder.className = displayMode ? "math-preview display-math" : "math-preview";
  try {
    if (!window.katex) throw new Error("公式预览组件尚未加载");
    window.katex.render(formula, holder, {
      displayMode,
      throwOnError: true,
      strict: "ignore",
      trust: false,
    });
  } catch (error) {
    holder.classList.add("math-error");
    holder.textContent = `公式需检查：${formula}`;
    holder.title = error.message || "公式格式不正确";
  }
  container.appendChild(holder);
  return !holder.classList.contains("math-error");
}

function renderRichPreview(markdown, container, emptyText = "这里会显示排版效果") {
  if (!container) return;
  container.innerHTML = "";
  const source = normalizeLineBreaks(markdown);
  if (!source.trim()) {
    container.classList.add("is-empty");
    container.textContent = emptyText;
    return;
  }
  container.classList.remove("is-empty");
  let lastIndex = 0;
  let previousWasBlock = false;
  for (const match of source.matchAll(RICH_CONTENT_RE)) {
    const token = match[0];
    const isBlock = token.startsWith("![") || token.startsWith("$$") || token.startsWith("\\[");
    let precedingText = source.slice(lastIndex, match.index);
    if (previousWasBlock) precedingText = precedingText.replace(/^\n+/, "");
    if (isBlock) precedingText = precedingText.replace(/\n+$/, "");
    appendFormattedText(container, precedingText);
    if (token.startsWith("![")) {
      const imageMatch = token.match(/^!\[([^\]]*)\]\(([^)]+)\)(?:\{([^}\n]*)\})?$/);
      if (imageMatch) {
        const imageUrl = safePreviewImageUrl(imageMatch[2]);
        const figure = document.createElement("span");
        figure.className = "preview-figure";
        if (imageUrl) {
          const image = document.createElement("img");
          image.src = imageUrl;
          image.alt = imageMatch[1] || "题目图片";
          const widthMatch = String(imageMatch[3] || "").match(
            /width\s*=\s*["']?([0-9.]+)(%|in|cm|mm|px|pt)/,
          );
          if (widthMatch) {
            image.style.width =
              widthMatch[2] === "%"
                ? `${Math.min(100, Number(widthMatch[1]))}%`
                : `${widthMatch[1]}${widthMatch[2]}`;
          }
          image.style.maxWidth = "100%";
          figure.appendChild(image);
        } else {
          figure.textContent = "图片暂时无法预览";
        }
        container.appendChild(figure);
      }
    } else if (token.startsWith("$$")) {
      renderMath(container, token.slice(2, -2), true);
    } else if (token.startsWith("\\[")) {
      renderMath(container, token.slice(2, -2), true);
    } else if (token.startsWith("\\(")) {
      renderMath(container, token.slice(2, -2), false);
    } else {
      renderMath(container, token.slice(1, -1), false);
    }
    lastIndex = Number(match.index) + token.length;
    previousWasBlock = isBlock;
  }
  let trailingText = source.slice(lastIndex);
  if (previousWasBlock) trailingText = trailingText.replace(/^\n+/, "");
  appendFormattedText(container, trailingText);
}

function renderManualPreviews() {
  renderRichPreview($("questionText").value, $("questionPreview"), "题目预览");
  renderRichPreview($("answerText").value, $("answerPreview"), "答案预览");
  renderRichPreview($("analysisText").value, $("analysisPreview"), "解析预览");
}

function renderEditPreviews() {
  renderRichPreview($("editQuestionText").value, $("editQuestionPreview"), "题目预览");
  if ($("editAnswerPreview")) {
    renderRichPreview($("editAnswerText").value, $("editAnswerPreview"), "答案预览");
  }
  if ($("editAnalysisPreview")) {
    renderRichPreview($("editAnalysisText").value, $("editAnalysisPreview"), "解析预览");
  }
}

function insertAtCursor(field, text, selectStartOffset = 0, selectLength = 0) {
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  field.setRangeText(text, start, end, "end");
  field.focus();
  if (selectLength) {
    field.setSelectionRange(start + selectStartOffset, start + selectStartOffset + selectLength);
  }
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertFormula(targetId, mode) {
  const field = $(targetId);
  if (!field) return;
  const selected = field.value.slice(field.selectionStart, field.selectionEnd).trim();
  const sample = selected || (mode === "block" ? "F = ma" : "v = v_0 + at");
  const inserted = mode === "block" ? `\n\n$$\n${sample}\n$$\n\n` : `$${sample}$`;
  const offset = mode === "block" ? 4 : 1;
  insertAtCursor(field, inserted, offset, selected ? 0 : sample.length);
}

function insertImageReference(targetId, url, alt = "题图") {
  const field = $(targetId);
  if (!field) return;
  insertAtCursor(field, `\n\n![${alt}](${url}){width=70%}\n\n`);
}

function removeImageReference(url, fieldIds = MANUAL_SECTION_IDS) {
  const escaped = String(url).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `!\\[[^\\]]*\\]\\(${escaped}\\)(?:\\{[^}\\n]*\\})?`,
    "g",
  );
  for (const fieldId of fieldIds) {
    const field = $(fieldId);
    if (!field) continue;
    field.value = field.value.replace(pattern, "").replace(/\n{3,}/g, "\n\n").trim();
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

function optionElement(value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  return option;
}

function renderTaxonomyList() {
  const holder = $("taxonomyList");
  if (!holder || !state.options) return;
  holder.innerHTML = "";
  const items =
    taxonomyMode === "block"
      ? (state.options.blocks || []).map((item) => item.name)
      : state.options.question_types || [];
  if (taxonomyMode === "type") {
    const allButton = document.createElement("button");
    allButton.type = "button";
    allButton.className = "taxonomy-item";
    allButton.textContent = "全部题型";
    allButton.addEventListener("click", () => applyTaxonomyFilter(""));
    holder.appendChild(allButton);
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "taxonomy-item";
    button.textContent = item;
    button.addEventListener("click", () => applyTaxonomyFilter(item));
    holder.appendChild(button);
  }
}

function applyTaxonomyFilter(value) {
  if (taxonomyMode === "block") {
    $("libraryBlock").value = value;
    $("libraryQuestionType").value = "";
  } else {
    $("libraryQuestionType").value = value;
    $("libraryBlock").value = "";
  }
  switchWorkspaceView("library");
  searchLibraryQuestions();
}

function bindTaxonomyNavigation() {
  for (const button of document.querySelectorAll("[data-taxonomy-mode]")) {
    button.addEventListener("click", () => {
      taxonomyMode = button.dataset.taxonomyMode;
      for (const tab of document.querySelectorAll("[data-taxonomy-mode]")) {
        tab.classList.toggle("is-active", tab === button);
      }
      renderTaxonomyList();
    });
  }
}

function renderSystemStatus() {
  if (!state.options) return;
  const status = $("pandocStatus");
  const wordReady = Boolean(state.options.pandoc);
  const legacyFormulaReady = Boolean(state.options.mathtype?.available);
  const ocrReady = Boolean(state.options.ocr?.available);
  const aiReady = Boolean(state.modelSettings?.enabled);
  status.textContent =
    `Word ${wordReady ? "可用" : "不可用"} · ` +
    `图片识别${ocrReady ? "可用" : "需人工填写"} · ` +
    `旧版公式${legacyFormulaReady ? "可读取" : "保留原图"} · ` +
    `AI 分类${aiReady ? "已启用" : "未启用"}`;
  status.className = `system-status ${wordReady ? "ok" : "warn"}`;
}

async function loadOptions() {
  const response = await fetch("/api/options");
  state.options = await response.json();
  const sidebarVersion = $("sidebarVersion");
  if (sidebarVersion) {
    sidebarVersion.textContent = `题搭子 v${state.options.app_version || "1.0.0"}`;
  }

  for (const block of state.options.blocks) {
    $("blockCode").appendChild(optionElement(block.code, block.name));
    $("searchBlock").appendChild(optionElement(block.name, block.name));
    $("libraryBlock").appendChild(optionElement(block.name, block.name));
    $("editBlock").appendChild(optionElement(block.name, block.name));
  }
  for (const type of state.options.types) {
    $("typeCode").appendChild(optionElement(type.code, type.name));
    $("searchType").appendChild(optionElement(type.name, type.name));
    $("libraryType").appendChild(optionElement(type.name, type.name));
    $("editMainType").appendChild(optionElement(type.name, type.name));
  }
  $("questionType").appendChild(optionElement("", "未指定"));
  $("editQuestionType").appendChild(optionElement("", "未指定"));
  $("batchQuestionType").appendChild(optionElement("", "不修改"));
  for (const questionType of state.options.question_types || []) {
    $("questionType").appendChild(optionElement(questionType, questionType));
    $("searchQuestionType").appendChild(optionElement(questionType, questionType));
    $("libraryQuestionType").appendChild(optionElement(questionType, questionType));
    $("editQuestionType").appendChild(optionElement(questionType, questionType));
    $("batchQuestionType").appendChild(optionElement(questionType, questionType));
  }
  for (const template of state.options.templates || []) {
    const label = template.available ? template.name : `${template.name}（缺失）`;
    const option = optionElement(template.key, label);
    option.disabled = !template.available;
    $("examTemplate").appendChild(option);
  }

  renderTaxonomyList();
  renderSystemStatus();
  $("convertWordBtn").disabled = !state.options.pandoc;
  if (!state.options.pandoc) {
    $("convertWordBtn").title = "当前不能读取 Word，请先完成组件安装。";
  }
}

function mathtypeSummaryText(summary) {
  const detected = Number(summary?.detected || 0);
  const converted = Number(summary?.converted || 0);
  const failed = Number(summary?.failed || 0);
  if (!detected) return "";
  if (!failed) return `已将 ${converted} 个旧版公式转为可编辑公式，请在下方预览中抽查。`;
  return `已转换 ${converted} 个旧版公式；另有 ${failed} 个保留原图，需要重点检查。`;
}

function renderWordFormulaStatus(summary) {
  const holder = $("wordFormulaStatus");
  const message = mathtypeSummaryText(summary);
  holder.textContent = message;
  holder.classList.toggle("hidden", !message);
  holder.classList.toggle("needs-attention", Number(summary?.failed || 0) > 0);
}

function setSaveEnabled() {
  const unresolved = state.formulaItems.some((item) => !item.confirmed);
  $("saveBtn").disabled = !state.draftReady || unresolved;
}

function setUploadItems(fileList) {
  const convertedWordUploads = state.uploadItems.filter(
    (item) => item.source === "word-conversion",
  );
  for (const item of state.uploadItems.filter((candidate) => candidate.source !== "word-conversion")) {
    if (item.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(item.previewUrl);
  }
  const manualUploads = Array.from(fileList || []).map((file, index) => {
    const isImage = file.type.startsWith("image/");
    const uniquePart = window.crypto?.randomUUID?.() || `${Date.now()}-${index}`;
    return {
      file,
      token: isImage ? `upload-image://${uniquePart}` : "",
      previewUrl: isImage ? URL.createObjectURL(file) : "",
      source: "manual",
      autoFormula: false,
    };
  });
  state.uploadItems = convertedWordUploads.concat(manualUploads);
}

function imageLocations(url, fieldIds = MANUAL_SECTION_IDS) {
  const labels = {
    questionText: "题目",
    answerText: "答案",
    analysisText: "解析",
    editQuestionText: "题目",
    editAnswerText: "答案",
    editAnalysisText: "解析",
  };
  const filename = String(url || "").split("?", 1)[0].split("/").pop();
  return fieldIds
    .filter((id) => {
      const value = $(id)?.value || "";
      return value.includes(url) || (filename && value.includes(filename));
    })
    .map((id) => labels[id]);
}

function imageActionButton(label, targetId, url, afterInsert) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost compact";
  button.textContent = label;
  button.addEventListener("click", () => {
    insertImageReference(targetId, url);
    afterInsert?.();
  });
  return button;
}

function imagePreviewCard({
  name,
  url,
  previewUrl,
  onRemove,
  fieldIds = MANUAL_SECTION_IDS,
  onChanged = renderImagePreview,
}) {
  const card = document.createElement("div");
  card.className = "image-preview-card";
  const visual = document.createElement("div");
  visual.className = "image-preview-visual";
  const source = previewUrl || safePreviewImageUrl(url);
  if (source && !source.toLowerCase().includes(".wmf") && !source.toLowerCase().includes(".emf")) {
    const image = document.createElement("img");
    image.src = source;
    image.alt = name || "题目图片";
    visual.appendChild(image);
  } else {
    visual.textContent = name || "图片";
  }
  const info = document.createElement("div");
  info.className = "image-preview-info";
  const title = document.createElement("strong");
  title.textContent = name || "图片";
  const location = document.createElement("span");
  const locations = imageLocations(url, fieldIds);
  location.textContent = locations.length ? `已放入：${locations.join("、")}` : "尚未放入内容";
  const actions = document.createElement("div");
  actions.className = "image-card-actions";
  const targets = fieldIds[0].startsWith("edit")
    ? [
        ["放入题目", "editQuestionText"],
        ["放入答案", "editAnswerText"],
        ["放入解析", "editAnalysisText"],
      ]
    : [
        ["放入题目", "questionText"],
        ["放入答案", "answerText"],
        ["放入解析", "analysisText"],
      ];
  for (const [label, targetId] of targets) {
    actions.appendChild(imageActionButton(label, targetId, url, onChanged));
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost compact danger-text";
  remove.textContent = "移除";
  remove.addEventListener("click", onRemove);
  actions.appendChild(remove);
  info.append(title, location, actions);
  card.append(visual, info);
  return card;
}

function renderImagePreview() {
  const holder = $("imagePreview");
  holder.innerHTML = "";
  const uploads = state.uploadItems.filter((item) => item.previewUrl && !item.autoFormula);
  const formulaImageCount = state.uploadItems.filter((item) => item.autoFormula).length;
  const hasWordImages = state.wordDraftImages.length > 0;
  if (!uploads.length && !hasWordImages && !formulaImageCount) {
    holder.textContent = "没有图片。";
    return;
  }
  if (formulaImageCount) {
    const note = document.createElement("div");
    note.className = "inline-note";
    note.textContent = `已随正文保留 ${formulaImageCount} 张旧版公式图片，无需逐张处理。`;
    holder.appendChild(note);
  }
  for (const image of state.wordDraftImages) {
    holder.appendChild(
      imagePreviewCard({
        name: image.name,
        url: image.url,
        onRemove: () => {
          removeImageReference(image.url);
          state.wordDraftImages = state.wordDraftImages.filter((item) => item !== image);
          state.formulaItems = state.formulaItems.filter((item) => item.url !== image.url);
          state.approvedFormulaImages.delete(image.url);
          renderFormulaPanel();
          renderImagePreview();
        },
      }),
    );
  }
  for (const item of uploads) {
    holder.appendChild(
      imagePreviewCard({
        name: item.file.name,
        url: item.token,
        previewUrl: item.previewUrl,
        onRemove: () => {
          removeImageReference(item.token);
          if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
          state.uploadItems = state.uploadItems.filter((candidate) => candidate !== item);
          renderImagePreview();
        },
      }),
    );
  }
}

function placeUnassignedUploads() {
  for (const item of state.uploadItems) {
    if (!item.previewUrl || item.autoFormula || imageLocations(item.token).length) continue;
    const current = $("questionText").value.trim();
    $("questionText").value =
      `${current}${current ? "\n\n" : ""}![题图](${item.token}){width=70%}`.trim();
  }
  renderManualPreviews();
}

function generateDraft() {
  normalizeFields(MANUAL_SECTION_IDS);
  if (!$("questionText").value.trim()) {
    alert("请先填写题目。");
    return;
  }
  placeUnassignedUploads();
  state.draftReady = true;
  $("draftHint").classList.add("hidden");
  $("reviewArea").classList.remove("hidden");
  setSaveEnabled();
  renderImagePreview();
  renderManualPreviews();
}

function mergeText(current, incoming) {
  const value = (incoming || "").trim();
  if (!value) return current;
  return current.trim() ? `${current.trim()}\n\n${value}` : value;
}

function fillMetadata(metadata) {
  if (!metadata) return;
  const block = metadata["板块"];
  const mainType = metadata["主类型"];
  if (block && state.options) {
    const option = state.options.blocks.find((item) => item.name === block || item.code === block);
    if (option) $("blockCode").value = option.code;
  }
  if (mainType && state.options) {
    const option = state.options.types.find((item) => item.name === mainType || item.code === mainType);
    if (option) $("typeCode").value = option.code;
  }
  if (metadata["难度系数"]) $("difficulty").value = metadata["难度系数"];
  if (metadata["年份"]) $("year").value = metadata["年份"];
  if (metadata["来源"]) $("source").value = metadata["来源"];
  if (metadata["知识点"]) $("knowledgePoints").value = metadataLines(metadata["知识点"]);
  if (metadata["类型"]) $("extraTypes").value = metadataLines(metadata["类型"]);
  if (metadata["备注"]) $("remarks").value = metadata["备注"];
}

function formulaMarkup(latex) {
  const trimmed = String(latex || "").trim().replace(/^\$+|\$+$/g, "");
  return `$${trimmed}$`;
}

function applyFormulaDecision(item, decision, latex = "") {
  if (item.decision === "convert" && item.appliedMarkup) {
    for (const fieldId of item.convertedFields || []) {
      const field = $(fieldId);
      const original = item.originalMarkup?.[fieldId] || `![公式](${item.url}){width=70%}`;
      field.value = field.value.replace(item.appliedMarkup, original);
    }
  }

  state.approvedFormulaImages.delete(item.url);
  item.confirmed = false;
  item.decision = "";
  item.appliedMarkup = "";
  item.convertedFields = [];

  if (decision === "keep") {
    item.decision = "keep";
    item.confirmed = true;
    state.approvedFormulaImages.add(item.url);
  } else if (decision === "convert") {
    const trimmed = String(latex || "").trim();
    if (!trimmed) {
      alert("请先填写公式。");
      return false;
    }
    const escapedUrl = item.url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(
      `!\\[[^\\]]*\\]\\(${escapedUrl}\\)(?:\\{[^}\\n]*\\})?`,
      "g",
    );
    const markup = formulaMarkup(trimmed);
    item.originalMarkup = item.originalMarkup || {};
    for (const fieldId of MANUAL_SECTION_IDS) {
      const field = $(fieldId);
      const original = field.value.match(pattern)?.[0];
      if (!original) continue;
      item.originalMarkup[fieldId] = original;
      field.value = field.value.replace(pattern, markup);
      item.convertedFields.push(fieldId);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    }
    item.decision = "convert";
    item.confirmed = true;
    item.appliedMarkup = markup;
  }
  renderManualPreviews();
  renderImagePreview();
  setSaveEnabled();
  return true;
}

function renderFormulaPanel() {
  const panel = $("formulaPanel");
  const list = $("formulaList");
  list.innerHTML = "";
  const pendingItems = state.formulaItems.filter((item) => !item.auto_kept);
  if (!pendingItems.length) {
    panel.classList.add("hidden");
    setSaveEnabled();
    return;
  }
  panel.classList.remove("hidden");
  for (const item of pendingItems) {
    const row = document.createElement("div");
    row.className = "formula-item";

    const preview = document.createElement("div");
    preview.className = "formula-preview";
    if (item.url && !item.url.toLowerCase().endsWith(".wmf") && !item.url.toLowerCase().endsWith(".emf")) {
      const img = document.createElement("img");
      img.src = item.url;
      img.alt = item.name || "公式图片";
      preview.appendChild(img);
    } else {
      preview.textContent = item.name || "公式图片";
    }

    const editor = document.createElement("div");
    editor.className = "formula-editor";
    const label = document.createElement("label");
    label.textContent = "这张图片可能是公式";
    const textarea = document.createElement("textarea");
    textarea.rows = 3;
    textarea.value = item.latex || "";
    textarea.placeholder = "输入公式，例如：\\frac{v^2}{r}";
    const rendered = document.createElement("div");
    rendered.className = "formula-rendered";
    const updateRendered = () => {
      rendered.innerHTML = "";
      if (textarea.value.trim()) {
        renderMath(rendered, textarea.value.trim().replace(/^\$+|\$+$/g, ""), true);
      } else {
        rendered.textContent = "输入后在这里预览";
        rendered.classList.add("is-empty");
      }
    };
    textarea.addEventListener("input", () => {
      item.latex = textarea.value;
      updateRendered();
      if (item.decision === "convert") {
        if (!textarea.value.trim()) {
          item.confirmed = false;
          setSaveEnabled();
          return;
        }
        const nextMarkup = formulaMarkup(textarea.value);
        for (const fieldId of item.convertedFields || []) {
          const field = $(fieldId);
          field.value = field.value.replace(item.appliedMarkup, nextMarkup);
          field.dispatchEvent(new Event("input", { bubbles: true }));
        }
        item.appliedMarkup = nextMarkup;
        item.confirmed = true;
        setSaveEnabled();
      }
    });
    updateRendered();

    const choices = document.createElement("div");
    choices.className = "formula-choices";
    const convert = document.createElement("button");
    convert.type = "button";
    convert.className = item.decision === "convert" ? "compact" : "secondary compact";
    convert.textContent = item.decision === "convert" ? "已转为公式" : "转为可编辑公式";
    convert.addEventListener("click", () => {
      item.latex = textarea.value;
      if (applyFormulaDecision(item, "convert", item.latex)) renderFormulaPanel();
    });
    const keep = document.createElement("button");
    keep.type = "button";
    keep.className = item.decision === "keep" ? "compact" : "secondary compact";
    keep.textContent = item.decision === "keep" ? "已保留原图" : "保留原图";
    keep.addEventListener("click", () => {
      applyFormulaDecision(item, "keep");
      renderFormulaPanel();
    });
    choices.append(convert, keep);

    const context = document.createElement("div");
    context.className = "formula-context";
    context.textContent = item.context || "";

    editor.appendChild(label);
    editor.appendChild(textarea);
    editor.appendChild(rendered);
    if (item.ocr_error) {
      const error = document.createElement("div");
      error.className = "formula-error";
      error.textContent = "未能自动识别。可手动输入公式，也可保留原图。";
      editor.appendChild(error);
    }
    editor.appendChild(choices);
    editor.appendChild(context);
    row.appendChild(preview);
    row.appendChild(editor);
    list.appendChild(row);
  }
  setSaveEnabled();
}

async function convertWordToMarkdown() {
  if (!(state.options && state.options.pandoc)) {
    alert("当前不能读取 Word，请先完成组件安装。");
    return;
  }
  const input = $("wordConvertFile");
  const file = input.files && input.files[0];
  if (!file) {
    alert("请先选择一个 .docx 文件。");
    return;
  }

  const button = $("convertWordBtn");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "正在读取…";
  renderWordFormulaStatus(null);

  const form = new FormData();
  form.append("file", file);
  let data;
  let metafileResult = { converted: 0, failed: [] };
  try {
    const response = await fetch("/api/convert-docx", { method: "POST", body: form });
    data = await response.json();
    if (!response.ok) {
      alert(data.detail || "读取 Word 失败。");
      return;
    }
    const metafileCount = (data.images || []).filter((item) =>
      METAFILE_RE.test(item.name || item.url),
    ).length;
    if (metafileCount) {
      button.textContent = `正在处理旧版公式（0/${metafileCount}）…`;
      metafileResult = await normalizeManualMetafiles(data, (finished, total) => {
        button.textContent = `正在处理旧版公式（${finished}/${total}）…`;
      });
    } else {
      clearConvertedWordUploads();
    }
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
  if (!data) return;

  const sections = data.sections || {};
  const fallback = data.markdown || "";
  const target = $("convertTarget").value;
  if (target === "questionText") {
    $("questionText").value = normalizeLineBreaks(sections.question || fallback);
    $("answerText").value = normalizeLineBreaks(
      mergeText($("answerText").value, sections.answer || ""),
    );
    $("analysisText").value = normalizeLineBreaks(
      mergeText($("analysisText").value, sections.analysis || ""),
    );
  } else {
    const sectionName = target === "answerText" ? "answer" : "analysis";
    const convertedText = sections[sectionName] || sections.question || data.text_markdown || fallback;
    $(target).value = normalizeLineBreaks(mergeText($(target).value, convertedText));
  }
  fillMetadata(data.metadata || {});

  state.wordDraftId = data.draft_id || "";
  state.wordDraftImages = data.images || [];
  renderWordFormulaStatus(data.mathtype);
  state.formulaItems = (data.formula_items || []).map((item) => ({
    ...item,
    decision: item.auto_kept ? "keep" : "",
    confirmed: Boolean(item.auto_kept || item.confirmed),
    appliedMarkup: "",
    convertedFields: [],
    originalMarkup: {},
  }));
  state.approvedFormulaImages.clear();
  state.draftReady = Boolean($("questionText").value.trim());
  renderImagePreview();
  renderFormulaPanel();
  renderManualPreviews();
  if (state.draftReady) {
    $("draftHint").classList.add("hidden");
    $("reviewArea").classList.remove("hidden");
    setSaveEnabled();
  }

  const warnings = [...(data.warnings || [])];
  if (metafileResult.converted) {
    warnings.push(`已自动转换 ${metafileResult.converted} 张旧版公式或题图，现在可以正常预览和入库。`);
  }
  if (metafileResult.failed.length) {
    warnings.push(`仍有 ${metafileResult.failed.length} 张旧版图片无法转换，请在预览中人工检查。`);
  }
  if (warnings.length) {
    alert(`Word 已读取：\n\n${Array.from(new Set(warnings)).join("\n")}`);
  }
}

function appendFormValue(form, key, value) {
  form.append(key, value == null ? "" : String(value));
}

async function saveQuestion() {
  if (!state.draftReady) return;
  normalizeFields(MANUAL_SECTION_IDS);
  const unresolved = state.formulaItems.filter((item) => !item.confirmed);
  if (unresolved.length) {
    alert(`还有 ${unresolved.length} 张疑似公式图片未处理。`);
    setSaveEnabled();
    return;
  }
  const form = new FormData();
  appendFormValue(form, "block_code", $("blockCode").value);
  appendFormValue(form, "type_code", $("typeCode").value);
  appendFormValue(form, "difficulty", $("difficulty").value);
  appendFormValue(form, "difficulty_coefficient", $("difficulty").value);
  appendFormValue(form, "year", $("year").value);
  appendFormValue(form, "source", $("source").value);
  appendFormValue(form, "question_text", $("questionText").value);
  appendFormValue(form, "answer_text", $("answerText").value);
  appendFormValue(form, "analysis_text", $("analysisText").value);
  appendFormValue(form, "knowledge_points", $("knowledgePoints").value);
  appendFormValue(form, "extra_types", $("extraTypes").value);
  appendFormValue(form, "question_type", $("questionType").value);
  appendFormValue(form, "remarks", $("remarks").value);
  appendFormValue(form, "draft_id", state.wordDraftId);
  appendFormValue(form, "approved_formula_images", JSON.stringify(Array.from(state.approvedFormulaImages)));
  appendFormValue(
    form,
    "upload_image_tokens",
    JSON.stringify(state.uploadItems.map((item) => item.token)),
  );
  for (const item of state.uploadItems) {
    form.append("files", item.file);
  }

  $("saveBtn").disabled = true;
  const response = await fetch("/api/questions", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok) {
    $("saveBtn").disabled = false;
    alert(data.detail || "入库失败");
    return;
  }
  alert(`已入库：${data.id}`);
  state.draftReady = false;
  state.wordDraftId = "";
  state.wordDraftImages = [];
  state.formulaItems = [];
  state.approvedFormulaImages.clear();
  for (const item of state.uploadItems) {
    if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
  }
  state.uploadItems = [];
  $("files").value = "";
  renderFormulaPanel();
  renderImagePreview();
  $("draftHint").classList.remove("hidden");
  $("reviewArea").classList.add("hidden");
  $("saveBtn").disabled = true;
  await refreshQuestionLists();
}

function updateSelectedCount() {
  $("selectedCount").textContent = state.selected.size;
  renderExamSelection();
}

function renderExamSelection() {
  const holder = $("examSelectionList");
  holder.innerHTML = "";
  const ids = Array.from(state.selected);
  if (!ids.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "请先到“选择题目”勾选题目。";
    holder.appendChild(empty);
    return;
  }
  ids.forEach((questionId, index) => {
    const item = state.resultItems.get(questionId) || {};
    const row = document.createElement("div");
    row.className = "exam-selection-item";
    const order = document.createElement("strong");
    order.textContent = String(index + 1);
    const title = document.createElement("span");
    title.appendChild(
      document.createTextNode(`${questionId} · ${item["题型"] || "未指定题型"} · `),
    );
    appendFormattedText(title, item.preview || "");
    const label = document.createElement("input");
    label.value = state.displayLabels.get(questionId) || String(index + 1);
    label.title = "试卷上的展示题号";
    label.setAttribute("aria-label", `${questionId} 的展示题号`);
    label.addEventListener("input", () => state.displayLabels.set(questionId, label.value.trim()));
    const up = document.createElement("button");
    up.type = "button";
    up.className = "ghost compact";
    up.textContent = "上移";
    up.disabled = index === 0;
    up.addEventListener("click", () => moveSelectedQuestion(index, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.className = "ghost compact";
    down.textContent = "下移";
    down.disabled = index === ids.length - 1;
    down.addEventListener("click", () => moveSelectedQuestion(index, 1));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost compact";
    remove.textContent = "移除";
    remove.addEventListener("click", () => {
      state.selected.delete(questionId);
      state.displayLabels.delete(questionId);
      updateSelectedCount();
      searchQuestions();
    });
    row.append(order, title, label, up, down, remove);
    holder.appendChild(row);
  });
}

function moveSelectedQuestion(index, delta) {
  const ids = Array.from(state.selected);
  const target = index + delta;
  if (target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  state.selected = new Set(ids);
  renderExamSelection();
}

function appendQuestionCells(row, item) {
  const values = [
    item.id,
    item["板块"] || "",
    item["主类型"] || "",
    item["难度"] || "",
    item["来源"] || "",
    item.preview || "",
  ];
  for (const [index, value] of values.entries()) {
    const cell = document.createElement("td");
    if (index === 0) cell.className = "question-id-cell";
    if (index === values.length - 1) {
      cell.className = "result-preview";
      renderRichPreview(value, cell, "暂无预览");
    } else {
      cell.textContent = value;
    }
    row.appendChild(cell);
  }
}

function questionActionCell(item) {
  const actionCell = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "action-group";
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "ghost compact";
  editButton.textContent = "查看 / 修改";
  editButton.addEventListener("click", () => openQuestionEditor(item.id));
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "ghost compact";
  copyButton.textContent = "复制";
  copyButton.addEventListener("click", () => copyQuestion(item.id));
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "danger compact";
  deleteButton.textContent = "删除";
  deleteButton.addEventListener("click", () => deleteQuestion(item.id));
  actions.append(editButton, copyButton, deleteButton);
  actionCell.appendChild(actions);
  return actionCell;
}

function renderResults(items) {
  for (const item of items) {
    state.resultItems.set(item.id, item);
  }
  const body = $("resultsBody");
  body.innerHTML = "";
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "没有找到题目。";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  for (const item of items) {
    const row = document.createElement("tr");
    const checkboxCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selected.has(item.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.selected.add(item.id);
        if (!state.displayLabels.has(item.id)) {
          state.displayLabels.set(item.id, String(state.selected.size));
        }
      } else {
        state.selected.delete(item.id);
        state.displayLabels.delete(item.id);
      }
      updateSelectedCount();
    });
    checkboxCell.appendChild(checkbox);
    row.appendChild(checkboxCell);
    appendQuestionCells(row, item);
    body.appendChild(row);
  }
}

function renderLibraryResults(items) {
  for (const item of items) {
    state.resultItems.set(item.id, item);
  }
  const body = $("libraryResultsBody");
  body.innerHTML = "";
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "题库中没有符合条件的题目。";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  for (const item of items) {
    const row = document.createElement("tr");
    appendQuestionCells(row, item);
    row.appendChild(questionActionCell(item));
    body.appendChild(row);
  }
}

async function searchQuestions() {
  const [sortBy, sortOrder] = $("searchSort").value.split(":");
  const params = new URLSearchParams({
    block: $("searchBlock").value,
    main_type: $("searchType").value,
    difficulty: $("searchDifficulty").value,
    year: $("searchYear").value,
    source: $("searchSource").value,
    knowledge: $("searchKnowledge").value,
    question_type: $("searchQuestionType").value,
    query: $("searchQuery").value,
    sort_by: sortBy,
    sort_order: sortOrder,
  });
  const response = await fetch(`/api/questions?${params}`);
  const data = await response.json();
  renderResults(data.items || []);
  updateSelectedCount();
}

async function searchLibraryQuestions() {
  const [sortBy, sortOrder] = $("librarySort").value.split(":");
  const params = new URLSearchParams({
    block: $("libraryBlock").value,
    main_type: $("libraryType").value,
    difficulty: $("libraryDifficulty").value,
    year: $("libraryYear").value,
    source: $("librarySource").value,
    knowledge: $("libraryKnowledge").value,
    question_type: $("libraryQuestionType").value,
    query: $("libraryQuery").value,
    sort_by: sortBy,
    sort_order: sortOrder,
  });
  const response = await fetch(`/api/questions?${params}`);
  const data = await response.json();
  renderLibraryResults(data.items || []);
}

function clearLibrarySearch() {
  for (const id of [
    "libraryQuery",
    "libraryBlock",
    "libraryType",
    "libraryDifficulty",
    "libraryYear",
    "librarySource",
    "libraryKnowledge",
    "libraryQuestionType",
  ]) {
    $(id).value = "";
  }
  $("librarySort").value = "id:asc";
  searchLibraryQuestions();
}

async function refreshQuestionLists() {
  await Promise.all([searchLibraryQuestions(), searchQuestions()]);
}

function renderAssistantRecommendations(data) {
  state.assistantRecommendations = data.items || [];
  const holder = $("assistantRecommendations");
  holder.innerHTML = "";
  $("assistantAddAllBtn").disabled = !state.assistantRecommendations.length;
  const parsed = data.parsed || {};
  const conditions = [
    ...(parsed.blocks || []),
    ...(parsed.types || []),
    ...(parsed.knowledge_points || []),
    ...(parsed.question_types || []),
  ];
  const summary =
    `推荐 ${data.recommended_count || 0} 道 / 候选 ${data.candidate_count || 0} 道` +
    ` · 预计 ${data.estimated_minutes || 0} 分钟` +
    ` · ${data.used_ai ? "模型增强排序" : "本地排序"}` +
    (conditions.length ? ` · 识别条件：${conditions.join("、")}` : "");
  const warnings = (data.warnings || []).length ? `；${data.warnings.join("；")}` : "";
  $("assistantResult").textContent = summary + warnings;

  for (const item of state.assistantRecommendations) {
    state.resultItems.set(item.id, {
      id: item.id,
      "题型": item.question_type,
      preview: item.preview,
    });
    const card = document.createElement("article");
    card.className = "assistant-recommendation-card";
    const heading = document.createElement("div");
    heading.className = "assistant-recommendation-heading";
    const title = document.createElement("strong");
    title.textContent = `${item.id} · ${item.block} · ${item.main_type}`;
    const add = document.createElement("button");
    add.type = "button";
    add.className = "ghost compact";
    add.textContent = state.selected.has(item.id) ? "已在试卷中" : "加入试卷";
    add.disabled = state.selected.has(item.id);
    add.addEventListener("click", () => {
      state.selected.add(item.id);
      if (!state.displayLabels.has(item.id)) state.displayLabels.set(item.id, String(state.selected.size));
      add.textContent = "已在试卷中";
      add.disabled = true;
      updateSelectedCount();
    });
    heading.append(title, add);
    const preview = document.createElement("div");
    preview.className = "assistant-preview";
    appendFormattedText(preview, item.preview || "暂无题目预览");
    const reason = document.createElement("div");
    reason.className = "assistant-reason";
    reason.textContent = `推荐理由：${item.reason}；预计 ${item.estimated_minutes} 分钟`;
    card.append(heading, preview, reason);
    holder.appendChild(card);
  }
}

async function recommendQuestions() {
  const query = $("assistantQuery").value.trim();
  if (!query) {
    alert("请先用一句话描述找题要求。");
    return;
  }
  const useAi = $("assistantUseAi").checked;
  let consent = true;
  if (useAi && state.modelSettings?.cloud) {
    consent = confirm(
      "将把找题要求、候选题的分类信息和题目短预览发送到所选云模型。" +
        "不会发送答案、完整解析或整个题库。是否继续？",
    );
    if (!consent) return;
  }
  $("assistantRecommendBtn").disabled = true;
  $("assistantResult").textContent = "正在找题…";
  const response = await fetch("/api/assistant/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, use_ai: useAi, consent }),
  });
  const data = await response.json();
  $("assistantRecommendBtn").disabled = false;
  if (!response.ok) {
    $("assistantResult").textContent = data.detail || "找题失败";
    return;
  }
  renderAssistantRecommendations(data);
}

function addAllRecommendations() {
  for (const item of state.assistantRecommendations) {
    if (state.selected.has(item.id)) continue;
    state.selected.add(item.id);
    state.displayLabels.set(item.id, String(state.selected.size));
  }
  updateSelectedCount();
  for (const button of $("assistantRecommendations").querySelectorAll("button")) {
    button.textContent = "已在试卷中";
    button.disabled = true;
  }
}

async function exportExam() {
  const mode = document.querySelector("input[name='exportMode']:checked").value;
  const result = $("exportResult");
  result.textContent = "正在生成 Word…";
  const ids = Array.from(state.selected);
  const displayLabels = {};
  ids.forEach((id, index) => {
    displayLabels[id] = state.displayLabels.get(id) || String(index + 1);
  });
  const separate = $("separateDocuments").checked;
  const response = await fetch(separate ? "/api/export-set" : "/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ids,
      mode,
      title: $("examTitle").value.trim() || "试卷",
      template: $("examTemplate").value || "a4_single",
      duration: $("examDuration").value.trim(),
      total_score: $("examTotalScore").value.trim(),
      show_ids: $("showQuestionIds").checked,
      answers_new_page: $("answersNewPage").checked,
      class_name: $("examClassName").value.trim(),
      student_fields: $("studentFields").checked,
      group_by_question_type: $("groupByQuestionType").checked,
      display_labels: displayLabels,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    result.textContent = data.detail || "导出失败";
    return;
  }
  result.innerHTML = "";
  const exportedFiles = data.files || [data];
  for (const exported of exportedFiles) {
    if (exported.docx_created) {
      const wordLink = document.createElement("a");
      wordLink.href = `/download/${encodeURIComponent(exported.exam_docx_filename)}`;
      wordLink.textContent = "下载 Word";
      result.appendChild(wordLink);
    } else if (exported.exam_md_filename) {
      const fallbackLink = document.createElement("a");
      fallbackLink.href = `/download/${encodeURIComponent(exported.exam_md_filename)}`;
      fallbackLink.textContent = "下载备用文件";
      result.appendChild(fallbackLink);
    }
    if (exported.preview_filename) {
      const previewLink = document.createElement("a");
      previewLink.href = `/preview/${encodeURIComponent(exported.preview_filename)}`;
      previewLink.target = "_blank";
      previewLink.rel = "noopener";
      previewLink.textContent = "查看排版";
      result.appendChild(previewLink);
    }
  }
  const summaryData = exportedFiles[0] || {};
  const summary = document.createElement("div");
  const validation = summaryData.validation || {};
  const issueCount = exportedFiles.reduce((total, item) => total + Number((item.issues || {}).count || 0), 0);
  const validationText = validation.performed
    ? validation.ok
      ? issueCount
        ? `已生成，建议检查 ${issueCount} 处排版`
        : "已生成，排版检查通过"
      : "Word 已生成，请打开检查排版"
    : "Word 已生成";
  summary.textContent = separate
    ? `已生成 ${exportedFiles.length} 份 Word · ${summaryData.template_name || "默认样式"}`
    : `${summaryData.template_name || "默认样式"} · ${validationText}`;
  result.appendChild(summary);
  if (summaryData.pandoc_message) {
    const message = document.createElement("div");
    message.textContent = summaryData.pandoc_message;
    result.appendChild(message);
  }
  if (summaryData.office_message) {
    const message = document.createElement("div");
    message.textContent = summaryData.office_message;
    result.appendChild(message);
  }
}

function lines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function metadataLines(value) {
  if (Array.isArray(value)) return value.join("\n");
  return String(value || "");
}

function renderEditingImages() {
  const holder = $("editImageManager");
  holder.innerHTML = "";
  if (!state.editingImages.length) {
    holder.textContent = "这道题没有图片。";
    return;
  }
  for (const filename of state.editingImages) {
    const url = `/assets/${filename}`;
    holder.appendChild(
      imagePreviewCard({
        name: filename,
        url,
        fieldIds: EDIT_SECTION_IDS,
        onChanged: () => {
          renderEditingImages();
          renderEditPreviews();
        },
        onRemove: () => {
          if (!confirm(`移除图片“${filename}”吗？保存后会从题库中删除。`)) return;
          for (const fieldId of EDIT_SECTION_IDS) {
            const field = $(fieldId);
            const pattern = new RegExp(
              `!\\[[^\\]]*\\]\\([^)]*${filename.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[^)]*\\)` +
                `(?:\\{[^}\\n]*\\})?`,
              "g",
            );
            field.value = field.value.replace(pattern, "").replace(/\n{3,}/g, "\n\n").trim();
          }
          state.editingImages = state.editingImages.filter((item) => item !== filename);
          renderEditingImages();
          renderEditPreviews();
        },
      }),
    );
  }
}

async function openQuestionEditor(questionId) {
  const response = await fetch(`/api/questions/${encodeURIComponent(questionId)}`);
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "读取题目失败");
    return;
  }
  const metadata = data.metadata || {};
  const sections = data.sections || {};
  state.editingId = questionId;
  $("editQuestionId").textContent = questionId;
  $("editBlock").value = metadata["板块"] || "";
  $("editMainType").value = metadata["主类型"] || "";
  $("editQuestionType").value = metadata["题型"] || "";
  $("editDifficulty").value = metadata["难度系数"] || "";
  $("editYear").value = metadata["年份"] || "";
  $("editSource").value = metadata["来源"] || "";
  $("editKnowledge").value = metadataLines(metadata["知识点"]);
  $("editTypes").value = metadataLines(metadata["类型"]);
  $("editQuestionText").value = normalizeLineBreaks(sections["题目"] || "");
  $("editAnswerText").value = normalizeLineBreaks(sections["答案"] || "");
  $("editAnalysisText").value = normalizeLineBreaks(sections["解析"] || "");
  $("editRemarks").value = normalizeLineBreaks(sections["备注"] || "");
  state.editingImages = Array.from(metadata["图片"] || []);
  renderEditingImages();
  renderEditPreviews();
  $("editDialog").showModal();
}

async function saveQuestionEdit() {
  if (!state.editingId) return;
  normalizeFields([...EDIT_SECTION_IDS, "editRemarks"]);
  const mainType = $("editMainType").value;
  const typeValues = lines($("editTypes").value);
  if (mainType && !typeValues.includes(mainType)) typeValues.unshift(mainType);
  const response = await fetch(`/api/questions/${encodeURIComponent(state.editingId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metadata: {
        板块: $("editBlock").value,
        主类型: mainType,
        类型: typeValues,
        知识点: lines($("editKnowledge").value),
        难度系数: $("editDifficulty").value.trim(),
        年份: $("editYear").value.trim(),
        来源: $("editSource").value.trim(),
        题型: $("editQuestionType").value,
        图片: state.editingImages,
      },
      sections: {
        题目: $("editQuestionText").value,
        答案: $("editAnswerText").value,
        解析: $("editAnalysisText").value,
        备注: $("editRemarks").value,
      },
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "保存失败");
    return;
  }
  $("editDialog").close();
  state.editingId = "";
  await refreshQuestionLists();
}

async function copyQuestion(questionId) {
  if (!confirm(`复制 ${questionId} 并生成一个新的永久题号吗？`)) return;
  const response = await fetch(`/api/questions/${encodeURIComponent(questionId)}/copy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "复制失败");
    return;
  }
  await refreshQuestionLists();
  alert(`已复制为 ${data.id}，你可以继续编辑新题。`);
  await openQuestionEditor(data.id);
}

function openBatchEditor() {
  if (!state.selected.size) {
    alert("请先勾选要批量修改的题目。");
    return;
  }
  $("batchDialog").showModal();
}

async function saveBatchEdit() {
  const response = await fetch("/api/questions/batch-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ids: Array.from(state.selected),
      add_types: lines($("batchAddTypes").value),
      remove_types: lines($("batchRemoveTypes").value),
      add_knowledge: lines($("batchAddKnowledge").value),
      remove_knowledge: lines($("batchRemoveKnowledge").value),
      question_type: $("batchQuestionType").value,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "批量修改失败");
    return;
  }
  $("batchDialog").close();
  $("batchForm").reset();
  await refreshQuestionLists();
  alert(`已修改 ${data.count} 道题。`);
}

async function deleteQuestion(questionId) {
  if (!confirm(`确定删除题目 ${questionId} 吗？`)) return;
  const response = await fetch(`/api/questions/${encodeURIComponent(questionId)}`, { method: "DELETE" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "删除失败");
    return;
  }
  state.selected.delete(questionId);
  await refreshQuestionLists();
}

function renderMaintenanceList(holder, items, emptyText, buttonText, handler, labeler) {
  holder.innerHTML = "";
  if (!items.length) {
    holder.textContent = emptyText;
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "maintenance-item";
    const label = document.createElement("span");
    label.textContent = labeler(item);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost compact";
    button.textContent = buttonText;
    button.addEventListener("click", () => handler(item));
    row.appendChild(label);
    row.appendChild(button);
    holder.appendChild(row);
  }
}

async function refreshMaintenance() {
  const [trashResponse, backupResponse] = await Promise.all([fetch("/api/trash"), fetch("/api/backups")]);
  const trashData = await trashResponse.json();
  const backupData = await backupResponse.json();
  renderMaintenanceList(
    $("trashList"),
    trashData.items || [],
    "回收站为空。",
    "恢复",
    restoreTrashItem,
    (item) => `${item.question_id} · ${item.deleted_at || ""}`,
  );
  renderMaintenanceList(
    $("backupList"),
    backupData.items || [],
    "还没有备份。",
    "恢复",
    restoreBackupItem,
    (item) => `${item.filename} · ${Math.ceil((item.size || 0) / 1024)} KB`,
  );
}

async function restoreTrashItem(item) {
  const response = await fetch(`/api/trash/${encodeURIComponent(item.trash_id)}/restore`, { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "恢复失败");
    return;
  }
  $("maintenanceResult").textContent = `已恢复题目 ${data.restored}。`;
  await Promise.all([searchQuestions(), refreshMaintenance()]);
}

async function createBackup() {
  const response = await fetch("/api/backups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: "手动备份" }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "备份失败");
    return;
  }
  $("maintenanceResult").textContent = `备份已创建：${data.filename}`;
  await refreshMaintenance();
}

async function restoreBackupItem(item) {
  if (!confirm(`恢复备份 ${item.filename} 将替换当前题库。系统会先自动备份当前数据，是否继续？`)) return;
  const response = await fetch(`/api/backups/${encodeURIComponent(item.filename)}/restore`, { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "备份恢复失败");
    return;
  }
  state.selected.clear();
  $("maintenanceResult").textContent = `已恢复备份；恢复前数据保存在 ${data.safety_backup}。`;
  await Promise.all([searchQuestions(), refreshMaintenance()]);
}

async function checkIntegrity() {
  const response = await fetch("/api/integrity");
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "检查失败");
    return;
  }
  if (data.ok) {
    $("maintenanceResult").textContent = `图片检查通过：${data.existing_count} 张图片均有对应题目。`;
    return;
  }
  $("maintenanceResult").textContent =
    `发现 ${data.missing.length} 张缺失图片、${data.orphaned.length} 张孤立图片。请先备份，再人工核对。`;
}

async function rebuildIndex() {
  if (!confirm("确定扫描现有题目并重新整理题号记录吗？")) return;
  const response = await fetch("/api/index/rebuild", { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "题号记录整理失败");
    return;
  }
  $("maintenanceResult").textContent = `题号记录已整理，共识别 ${Object.keys(data.index || {}).length} 类题号。`;
}

async function restoreDefaultTemplates() {
  if (!confirm("确定用内置模板覆盖数据目录中的三套试卷模板吗？")) return;
  const response = await fetch("/api/templates/restore", { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "模板恢复失败");
    return;
  }
  $("maintenanceResult").textContent = `已恢复默认模板：${(data.restored || []).join("、") || "无需恢复"}`;
}

function importDraftById(draftId) {
  return (state.importTask?.drafts || []).find((item) => item.id === draftId);
}

function bindDraftField(
  element,
  draft,
  field,
  transform = (value) => value,
  onUpdate = () => {},
) {
  element.value = Array.isArray(draft[field]) ? draft[field].join("\n") : String(draft[field] ?? "");
  element.addEventListener("input", () => {
    draft[field] = transform(element.value);
    onUpdate();
  });
  element.addEventListener("change", () => {
    draft[field] = transform(element.value);
    onUpdate();
  });
}

function draftSelect(draft, field, options) {
  const select = document.createElement("select");
  for (const optionInfo of options) {
    select.appendChild(optionElement(optionInfo.value, optionInfo.label));
  }
  bindDraftField(select, draft, field);
  return select;
}

function draftLabel(text, control, wide = false) {
  const label = document.createElement("label");
  if (wide) label.className = "wide";
  label.append(text, control);
  return label;
}

function combinedAnswerAnalysis(draft) {
  const parts = [];
  const answer = normalizeLineBreaks(draft.answer || "").trim();
  const analysis = normalizeLineBreaks(draft.analysis || "").trim();
  if (answer) parts.push(`【答案】${answer}`);
  if (analysis) parts.push(`【解析】\n${analysis}`);
  return parts.join("\n\n");
}

function updateCombinedAnswerAnalysis(draft, value) {
  const normalized = normalizeLineBreaks(value || "").trim();
  const answerMatch = normalized.match(/【\s*答案\s*】([\s\S]*?)(?=【\s*(?:解析|详解)\s*】|$)/);
  const analysisMatch = normalized.match(/【\s*(?:解析|详解)\s*】([\s\S]*)/);
  if (answerMatch || analysisMatch) {
    draft.answer = normalizeLineBreaks(answerMatch?.[1] || "").trim();
    draft.analysis = normalizeLineBreaks(analysisMatch?.[1] || "").trim();
    return;
  }
  draft.answer = "";
  draft.analysis = normalized;
}

function updateImportSelectionControls() {
  const button = $("toggleAllImportDraftsBtn");
  const drafts = (state.importTask?.drafts || []).filter((item) => !item.committed_id);
  const allSelected = drafts.length > 0 && drafts.every((item) => item.confirmed);
  button.disabled = !drafts.length;
  button.textContent = allSelected ? "取消全选" : "全部选中";
  $("commitImportBtn").disabled = !drafts.some((item) => item.confirmed);
}

function toggleAllImportDrafts() {
  const drafts = (state.importTask?.drafts || []).filter((item) => !item.committed_id);
  if (!drafts.length) return;
  const shouldSelect = !drafts.every((item) => item.confirmed);
  for (const draft of drafts) draft.confirmed = shouldSelect;
  renderImportDrafts();
}

function renderImportDrafts() {
  const holder = $("importDrafts");
  holder.innerHTML = "";
  const task = state.importTask;
  if (!task || !(task.drafts || []).length) {
    $("saveImportDraftsBtn").disabled = true;
    updateImportSelectionControls();
    return;
  }
  $("saveImportDraftsBtn").disabled = false;
  updateImportSelectionControls();
  task.drafts.forEach((draft, index) => {
    for (const field of ["question", "answer", "analysis", "remarks"]) {
      if (field in draft) draft[field] = normalizeLineBreaks(draft[field]);
    }
    const card = document.createElement("article");
    card.className = "import-draft-card";
    card.dataset.draftId = draft.id;

    const header = document.createElement("div");
    header.className = "import-draft-header";
    const title = document.createElement("div");
    const numberText = draft.original_number ? `原题 ${draft.original_number}` : "题号待确认";
    title.textContent = `第 ${index + 1} 道 · ${numberText}`;
    const confirmedLabel = document.createElement("label");
    confirmedLabel.className = "confirm-draft";
    const confirmed = document.createElement("input");
    confirmed.type = "checkbox";
    confirmed.checked = Boolean(draft.confirmed);
    confirmed.disabled = Boolean(draft.committed_id);
    confirmed.addEventListener("change", () => {
      draft.confirmed = confirmed.checked;
      updateImportSelectionControls();
    });
    confirmedLabel.append(confirmed, draft.committed_id ? ` 已入库：${draft.committed_id}` : " 内容已核对");
    header.append(title, confirmedLabel);
    card.appendChild(header);

    const metadataGrid = document.createElement("div");
    metadataGrid.className = "grid";
    metadataGrid.append(
      draftLabel(
        "板块",
        draftSelect(
          draft,
          "block_code",
          state.options.blocks.map((item) => ({ value: item.code, label: item.name })),
        ),
      ),
      draftLabel(
        "题目特点",
        draftSelect(
          draft,
          "type_code",
          state.options.types.map((item) => ({ value: item.code, label: item.name })),
        ),
      ),
      draftLabel(
        "题型",
        draftSelect(
          draft,
          "question_type",
          [{ value: "", label: "未指定" }].concat(
            (state.options.question_types || []).map((item) => ({ value: item, label: item })),
          ),
        ),
      ),
    );
    const difficulty = document.createElement("input");
    bindDraftField(difficulty, draft, "difficulty");
    metadataGrid.appendChild(draftLabel("难度", difficulty));
    const year = document.createElement("input");
    bindDraftField(year, draft, "year");
    metadataGrid.appendChild(draftLabel("年份", year));
    const source = document.createElement("input");
    bindDraftField(source, draft, "source");
    metadataGrid.appendChild(draftLabel("来源", source, true));
    const knowledge = document.createElement("textarea");
    knowledge.rows = 2;
    bindDraftField(knowledge, draft, "knowledge_points", lines);
    metadataGrid.appendChild(draftLabel("知识点（每行一个）", knowledge, true));
    const types = document.createElement("textarea");
    types.rows = 2;
    bindDraftField(types, draft, "extra_types", lines);
    metadataGrid.appendChild(draftLabel("附加类型（每行一个）", types, true));
    card.appendChild(metadataGrid);

    const question = document.createElement("textarea");
    question.rows = 8;
    question.className = "import-question-text";
    const questionPreview = document.createElement("div");
    questionPreview.className = "content-preview import-content-preview";
    const answerPreview = document.createElement("div");
    answerPreview.className = "content-preview import-content-preview compact-preview";
    const analysisPreview = document.createElement("div");
    analysisPreview.className = "content-preview import-content-preview compact-preview";
    const updateFullDraftPreview = () => {
      renderRichPreview(draft.question, questionPreview, "暂无题目内容");
      renderRichPreview(draft.answer, answerPreview, "暂无答案");
      renderRichPreview(draft.analysis, analysisPreview, "暂无解析");
    };
    bindDraftField(question, draft, "question", (value) => value, updateFullDraftPreview);
    card.appendChild(draftLabel("题目正文", question));

    const answerAnalysis = document.createElement("textarea");
    answerAnalysis.rows = 9;
    answerAnalysis.value = combinedAnswerAnalysis(draft);
    answerAnalysis.placeholder = "【答案】…\n\n【解析】…";
    answerAnalysis.addEventListener("input", () => {
      updateCombinedAnswerAnalysis(draft, answerAnalysis.value);
      updateFullDraftPreview();
    });
    card.appendChild(draftLabel("答案与解析", answerAnalysis));

    const previewDetails = document.createElement("details");
    previewDetails.className = "draft-preview-details";
    const previewSummary = document.createElement("summary");
    previewSummary.textContent = "查看完整排版效果";
    const previewBody = document.createElement("div");
    previewBody.className = "draft-full-preview";
    for (const [label, preview] of [
      ["题目", questionPreview],
      ["答案", answerPreview],
      ["解析", analysisPreview],
    ]) {
      const section = document.createElement("section");
      section.className = "draft-preview-section";
      const heading = document.createElement("strong");
      heading.textContent = label;
      section.append(heading, preview);
      previewBody.appendChild(section);
    }
    previewDetails.append(previewSummary, previewBody);
    card.appendChild(previewDetails);
    updateFullDraftPreview();

    if ((draft.images || []).length) {
      const images = document.createElement("div");
      images.className = "import-image-list";
      for (const image of draft.images) {
        const imageCard = document.createElement("div");
        imageCard.className = "import-image-card";
        const isMetafile = METAFILE_RE.test(image.name || image.url);
        const preview = isMetafile ? document.createElement("div") : document.createElement("img");
        if (isMetafile) {
          preview.className = "draft-warning";
          preview.textContent = "这张旧版公式图片未能自动转换，请保留原 Word 对照检查。";
        } else {
          preview.src = image.url;
          preview.alt = image.name;
        }
        const buttons = document.createElement("div");
        buttons.className = "action-group";
        for (const [action, label] of [
          ["rotate_left", "左转"],
          ["rotate_right", "右转"],
          ["enhance", image.enhanced ? "取消去阴影" : "去阴影"],
          ["crop", "裁剪"],
          ["perspective", "透视校正"],
          ["reset", "恢复原图"],
          ["delete", "移除"],
        ]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "ghost compact";
          button.textContent = label;
          button.disabled = isMetafile && action !== "delete";
          button.addEventListener("click", () => {
            if (action === "delete" && !confirm("移除这张图片吗？")) return;
            if (action === "crop" || action === "perspective") {
              openImageEditor(draft.id, image, action);
              return;
            }
            processImportImage(draft.id, image.name, action);
          });
          buttons.appendChild(button);
        }
        imageCard.append(preview, buttons);
        images.appendChild(imageCard);
      }
      card.appendChild(images);
    }

    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    if (index > 0) {
      const merge = document.createElement("button");
      merge.type = "button";
      merge.className = "secondary";
      merge.textContent = "与上一题合并";
      merge.addEventListener("click", () => mergeImportDraft(index));
      actions.appendChild(merge);
    }
    const split = document.createElement("button");
    split.type = "button";
    split.className = "secondary";
    split.textContent = "在题目光标处拆分";
    split.addEventListener("click", () => splitImportDraft(draft.id, question.selectionStart));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "移除此草稿";
    remove.addEventListener("click", () => {
      if (!confirm("确定从本次导入任务中移除这道草稿吗？尚未入库的数据将不再显示。")) return;
      state.importTask.drafts.splice(index, 1);
      renderImportDrafts();
    });
    actions.append(split, remove);
    card.appendChild(actions);
    holder.appendChild(card);
  });
}

async function loadImportStatus() {
  const response = await fetch("/api/import/status");
  const data = await response.json();
  if (!response.ok) {
    $("ocrStatus").textContent = data.detail || "读取导入状态失败";
    return;
  }
  $("ocrStatus").textContent = data.ocr?.available
    ? "可识别扫描件和照片"
    : "照片会保留原图，请人工填写文字";
  const list = $("importTaskList");
  list.innerHTML = "";
  for (const item of data.tasks || []) {
    const row = document.createElement("div");
    row.className = "maintenance-item";
    const text = document.createElement("span");
    text.textContent = `${item.source} · ${item.draft_count} 题 · ${item.status}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost compact";
    button.textContent = "继续审核";
    button.addEventListener("click", () => loadImportTask(item.id));
    row.append(text, button);
    list.appendChild(row);
  }
  if (!(data.tasks || []).length) list.textContent = "还没有导入任务。";
}

async function analyzeImportFile() {
  const file = $("batchImportFile").files?.[0];
  if (!file) {
    alert("请先选择题目文件。");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  const answerFile = $("batchAnswerFile").files?.[0];
  if (answerFile) form.append("answer_file", answerFile);
  $("analyzeImportBtn").disabled = true;
  $("importResult").textContent = "正在读取文件并切分题目…";
  try {
    const response = await fetch("/api/import/analyze", { method: "POST", body: form });
    let data = await response.json();
    if (!response.ok) {
      $("importResult").textContent = data.detail || "导入分析失败";
      return;
    }
    const metafileCount = importTaskMetafiles(data).length;
    let conversion = { task: data, converted: 0, failed: [] };
    if (metafileCount) {
      $("importResult").textContent = `正在处理旧版公式和题图（共 ${metafileCount} 张）…`;
      conversion = await normalizeImportTaskMetafiles(data, (finished, total, phase) => {
        $("importResult").textContent =
          phase === "convert"
            ? `正在转换旧版公式和题图（${finished}/${total}）…`
            : `正在保存已转换图片（${finished}/${total}）…`;
      });
      data = conversion.task;
    }
    state.importTask = data;
    const conversionText = conversion.converted
      ? ` 已自动处理 ${conversion.converted} 张旧版公式或题图。`
      : "";
    const formulaText = mathtypeSummaryText(data.mathtype);
    const failedText = conversion.failed.length
      ? ` 仍有 ${conversion.failed.length} 张图片需人工检查。`
      : "";
    $("importResult").textContent =
      `已生成 ${data.drafts?.length || 0} 道待审核草稿。` +
      `${formulaText ? ` ${formulaText}` : ""}${conversionText}${failedText}` +
      " 请逐题核对后再入库。";
    renderImportDrafts();
    await loadImportStatus();
  } catch (error) {
    $("importResult").textContent = `导入失败：${error.message || "请稍后重试"}`;
  } finally {
    $("analyzeImportBtn").disabled = false;
  }
}

async function loadImportTask(taskId, { scrollToCenter = true } = {}) {
  const response = await fetch(`/api/import/tasks/${encodeURIComponent(taskId)}`);
  let data = await response.json();
  if (!response.ok) {
    alert(data.detail || "读取导入任务失败");
    return;
  }
  const metafileCount = importTaskMetafiles(data).length;
  let conversion = { task: data, converted: 0, failed: [] };
  if (metafileCount) {
    $("importResult").textContent = `正在补充处理 ${metafileCount} 张旧版公式或题图…`;
    conversion = await normalizeImportTaskMetafiles(data, (finished, total, phase) => {
      $("importResult").textContent =
        phase === "convert"
          ? `正在转换旧版公式和题图（${finished}/${total}）…`
          : `正在保存已转换图片（${finished}/${total}）…`;
    });
    data = conversion.task;
  }
  state.importTask = data;
  const formulaText = mathtypeSummaryText(data.mathtype);
  $("importResult").textContent =
    `正在继续审核 ${data.source}，任务状态：${data.status}。` +
    (formulaText ? ` ${formulaText}` : "") +
    (conversion.converted ? ` 已补充处理 ${conversion.converted} 张旧版图片。` : "") +
    (conversion.failed.length ? ` 仍有 ${conversion.failed.length} 张需人工检查。` : "");
  renderImportDrafts();
  if (scrollToCenter) {
    document.querySelector(".import-center")?.scrollIntoView({ behavior: "smooth" });
  }
}

async function saveImportDrafts({ quiet = false } = {}) {
  if (!state.importTask) return false;
  const response = await fetch(`/api/import/tasks/${encodeURIComponent(state.importTask.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drafts: state.importTask.drafts }),
  });
  const data = await response.json();
  if (!response.ok) {
    $("importResult").textContent = data.detail || "保存导入草稿失败";
    return false;
  }
  state.importTask = data;
  if (!quiet) $("importResult").textContent = "进度已保存。";
  renderImportDrafts();
  return true;
}

async function commitImportDrafts() {
  if (!state.importTask) return;
  const selectedIds = state.importTask.drafts.filter((item) => item.confirmed && !item.committed_id).map((item) => item.id);
  if (!selectedIds.length) {
    alert("请先核对题目，并勾选“内容已核对”。");
    return;
  }
  if (!confirm(`确定将已核对的 ${selectedIds.length} 道题写入正式题库吗？`)) return;
  $("commitImportBtn").disabled = true;
  const response = await fetch(`/api/import/tasks/${encodeURIComponent(state.importTask.id)}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drafts: state.importTask.drafts, selected_ids: selectedIds }),
  });
  const data = await response.json();
  $("commitImportBtn").disabled = false;
  if (!response.ok) {
    $("importResult").textContent = data.detail || "批量入库失败";
    return;
  }
  $("importResult").textContent = `已入库 ${data.created.length} 道题，任务状态：${data.status}。`;
  await Promise.all([loadImportTask(state.importTask.id), refreshQuestionLists(), loadImportStatus()]);
}

async function mergeImportDraft(index) {
  if (!(await saveImportDrafts({ quiet: true }))) return;
  const first = state.importTask.drafts[index - 1];
  const second = state.importTask.drafts[index];
  const response = await fetch(`/api/import/tasks/${encodeURIComponent(state.importTask.id)}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ first_id: first.id, second_id: second.id }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "合并失败");
    return;
  }
  state.importTask = data;
  renderImportDrafts();
}

async function splitImportDraft(draftId, position) {
  if (!(await saveImportDrafts({ quiet: true }))) return;
  const response = await fetch(
    `/api/import/tasks/${encodeURIComponent(state.importTask.id)}/drafts/${encodeURIComponent(draftId)}/split`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position }),
    },
  );
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "拆分失败");
    return;
  }
  state.importTask = data;
  renderImportDrafts();
}

function captureDraftViewport(draftId) {
  const card = document.querySelector(`[data-draft-id="${CSS.escape(draftId)}"]`);
  return { draftId, top: card?.getBoundingClientRect().top ?? 0, scrollY: window.scrollY };
}

function restoreDraftViewport(anchor) {
  requestAnimationFrame(() => {
    const card = document.querySelector(`[data-draft-id="${CSS.escape(anchor.draftId)}"]`);
    if (!card) {
      window.scrollTo({ top: anchor.scrollY, behavior: "instant" });
      return;
    }
    const difference = card.getBoundingClientRect().top - anchor.top;
    window.scrollBy({ top: difference, behavior: "instant" });
  });
}

async function processImportImage(draftId, imageName, action, changes = {}) {
  const payload = { action, ...changes };
  const anchor = captureDraftViewport(draftId);
  const response = await fetch(
    `/api/import/tasks/${encodeURIComponent(state.importTask.id)}/drafts/${encodeURIComponent(draftId)}` +
      `/images/${encodeURIComponent(imageName)}/process`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "图片处理失败");
    return;
  }
  await loadImportTask(state.importTask.id, { scrollToCenter: false });
  restoreDraftViewport(anchor);
}

function imageEditorDefaults(mode) {
  if (mode === "crop") {
    return { crop: { left: 0.05, top: 0.05, right: 0.95, bottom: 0.95 } };
  }
  return {
    points: [
      [0.04, 0.04],
      [0.96, 0.04],
      [0.96, 0.96],
      [0.04, 0.96],
    ],
  };
}

function drawImageEditor() {
  const editor = state.imageEditor;
  if (!editor?.image?.complete) return;
  const canvas = $("imageEditorCanvas");
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(editor.image, 0, 0, canvas.width, canvas.height);
  context.save();
  context.lineWidth = 3;
  context.strokeStyle = "#10a37f";
  context.fillStyle = "rgba(16, 163, 127, 0.18)";
  if (editor.mode === "crop") {
    const crop = editor.crop;
    const left = crop.left * canvas.width;
    const top = crop.top * canvas.height;
    const width = (crop.right - crop.left) * canvas.width;
    const height = (crop.bottom - crop.top) * canvas.height;
    context.fillStyle = "rgba(16, 24, 32, 0.55)";
    context.beginPath();
    context.rect(0, 0, canvas.width, canvas.height);
    context.rect(left, top, width, height);
    context.fill("evenodd");
    context.strokeRect(left, top, width, height);
  } else {
    const points = editor.points.map(([x, y]) => [x * canvas.width, y * canvas.height]);
    context.beginPath();
    points.forEach(([x, y], index) => {
      if (index) context.lineTo(x, y);
      else context.moveTo(x, y);
    });
    context.closePath();
    context.fill();
    context.stroke();
    for (const [x, y] of points) {
      context.beginPath();
      context.arc(x, y, 9, 0, Math.PI * 2);
      context.fillStyle = "#fff";
      context.fill();
      context.stroke();
    }
  }
  context.restore();
}

function imageEditorPosition(event) {
  const canvas = $("imageEditorCanvas");
  const bounds = canvas.getBoundingClientRect();
  return [
    Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)),
    Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height)),
  ];
}

function resetImageEditorSelection() {
  const editor = state.imageEditor;
  if (!editor) return;
  Object.assign(editor, imageEditorDefaults(editor.mode));
  editor.dragging = null;
  drawImageEditor();
}

function openImageEditor(draftId, image, mode) {
  const source = String(image.url || "").split("?", 1)[0];
  const editorImage = new Image();
  state.imageEditor = {
    draftId,
    imageName: image.name,
    mode,
    image: editorImage,
    dragging: null,
    ...imageEditorDefaults(mode),
  };
  $("imageEditorTitle").textContent = mode === "crop" ? "裁剪图片" : "校正透视";
  $("imageEditorHint").textContent =
    mode === "crop"
      ? "在图片上拖出需要保留的区域。"
      : "拖动四个圆点，对准纸张或题图的四个角。";
  editorImage.addEventListener("load", () => {
    const maxWidth = Math.min(920, Math.max(320, window.innerWidth - 100));
    const maxHeight = Math.min(620, Math.max(280, window.innerHeight - 260));
    const scale = Math.min(maxWidth / editorImage.naturalWidth, maxHeight / editorImage.naturalHeight, 1);
    const canvas = $("imageEditorCanvas");
    canvas.width = Math.max(1, Math.round(editorImage.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(editorImage.naturalHeight * scale));
    drawImageEditor();
  });
  editorImage.addEventListener("error", () => {
    alert("图片预览无法打开，请重新导入这张图片。");
    $("imageEditorDialog").close();
  });
  editorImage.src = `${source}?editor=${Date.now()}`;
  $("imageEditorDialog").showModal();
}

function bindImageEditorEvents() {
  const canvas = $("imageEditorCanvas");
  canvas.addEventListener("pointerdown", (event) => {
    const editor = state.imageEditor;
    if (!editor) return;
    const point = imageEditorPosition(event);
    if (editor.mode === "crop") {
      editor.dragging = { start: point };
      editor.crop = { left: point[0], top: point[1], right: point[0], bottom: point[1] };
    } else {
      let nearest = 0;
      let distance = Number.POSITIVE_INFINITY;
      editor.points.forEach(([x, y], index) => {
        const current = Math.hypot(point[0] - x, point[1] - y);
        if (current < distance) {
          nearest = index;
          distance = current;
        }
      });
      editor.dragging = { pointIndex: nearest };
      editor.points[nearest] = point;
    }
    canvas.setPointerCapture(event.pointerId);
    drawImageEditor();
  });
  canvas.addEventListener("pointermove", (event) => {
    const editor = state.imageEditor;
    if (!editor?.dragging) return;
    const point = imageEditorPosition(event);
    if (editor.mode === "crop") {
      const [startX, startY] = editor.dragging.start;
      editor.crop = {
        left: Math.min(startX, point[0]),
        top: Math.min(startY, point[1]),
        right: Math.max(startX, point[0]),
        bottom: Math.max(startY, point[1]),
      };
    } else {
      editor.points[editor.dragging.pointIndex] = point;
    }
    drawImageEditor();
  });
  const finish = () => {
    if (state.imageEditor) state.imageEditor.dragging = null;
  };
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);
  $("closeImageEditorBtn").addEventListener("click", () => $("imageEditorDialog").close());
  $("resetImageSelectionBtn").addEventListener("click", resetImageEditorSelection);
  $("applyImageEditBtn").addEventListener("click", async () => {
    const editor = state.imageEditor;
    if (!editor) return;
    let changes;
    if (editor.mode === "crop") {
      const crop = editor.crop;
      if (crop.right - crop.left < 0.02 || crop.bottom - crop.top < 0.02) {
        alert("保留区域太小，请重新框选。");
        return;
      }
      changes = { crop };
    } else {
      changes = { perspective: editor.points };
    }
    $("imageEditorDialog").close();
    await processImportImage(editor.draftId, editor.imageName, editor.mode, changes);
    state.imageEditor = null;
  });
}

function renderModelSettings(data) {
  state.modelSettings = data.settings || {};
  state.modelProviders = data.providers || state.modelProviders;
  const providerSelect = $("modelProvider");
  if (!providerSelect.options.length) {
    for (const provider of state.modelProviders) {
      providerSelect.appendChild(optionElement(provider.key, provider.name));
    }
  }
  const settings = state.modelSettings;
  providerSelect.value = settings.provider || "aliyun";
  $("modelName").value = settings.model || "";
  $("modelBaseUrl").value = settings.base_url || "";
  $("modelTimeout").value = settings.timeout_seconds || 45;
  $("modelRetries").value = String(settings.max_retries ?? 2);
  $("modelEnabled").checked = Boolean(settings.enabled);
  $("modelLocalOnly").checked = Boolean(settings.local_only);
  $("modelApiKey").value = "";
  const keyText = settings.cloud
    ? settings.api_key_configured
      ? "访问密钥已安全保存"
      : "尚未填写访问密钥"
    : "本机模型不需要访问密钥";
  $("modelStatus").textContent =
    `${settings.provider_name || "模型服务"} · ${settings.model || "未设置模型"} · ${keyText}` +
    (settings.local_only ? " · 当前不会连接网络" : "");
  $("aiClassifyBtn").disabled = !settings.enabled;
  $("aiClassifyBtn").title = settings.enabled ? "" : "请先在下方启用并保存 AI 辅助设置。";
  renderSystemStatus();
}

async function loadModelSettings() {
  const response = await fetch("/api/models/settings");
  const data = await response.json();
  if (!response.ok) {
    $("modelStatus").textContent = data.detail || "读取模型设置失败";
    return;
  }
  renderModelSettings(data);
}

function selectedProviderSpec() {
  return state.modelProviders.find((item) => item.key === $("modelProvider").value);
}

function applyProviderDefaults() {
  const provider = selectedProviderSpec();
  if (!provider) return;
  $("modelBaseUrl").value = provider.default_base_url || "";
  $("modelName").value = provider.default_model || "";
  $("modelApiKey").placeholder = provider.cloud
    ? "留空表示保持原有密钥"
    : "本机模型不需要填写";
}

function modelSettingsPayload() {
  return {
    provider: $("modelProvider").value,
    base_url: $("modelBaseUrl").value.trim(),
    model: $("modelName").value.trim(),
    api_key: $("modelApiKey").value.trim(),
    enabled: $("modelEnabled").checked,
    local_only: $("modelLocalOnly").checked,
    timeout_seconds: Number($("modelTimeout").value || 45),
    max_retries: Number($("modelRetries").value || 0),
  };
}

async function saveModelSettings({ quiet = false } = {}) {
  const response = await fetch("/api/models/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(modelSettingsPayload()),
  });
  const data = await response.json();
  if (!response.ok) {
    $("modelStatus").textContent = data.detail || "模型设置保存失败";
    return false;
  }
  renderModelSettings(data);
  if (!quiet) $("modelStatus").textContent += " · 设置已保存";
  return true;
}

async function testModelConnection() {
  $("modelStatus").textContent = "正在测试连接……";
  if (!(await saveModelSettings({ quiet: true }))) return;
  const response = await fetch("/api/models/test", { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    $("modelStatus").textContent = data.detail || "连接测试失败";
    return;
  }
  const localHint = data.model_available === false ? "；服务已连接，但本机尚未安装所选模型" : "";
  $("modelStatus").textContent =
    `${data.provider_name} 连接成功，模型 ${data.model}，耗时 ${data.latency_ms} ms${localHint}`;
}

function applyClassificationDraft(draft) {
  const block = state.options.blocks.find((item) => item.name === draft["板块"]);
  const mainType = state.options.types.find((item) => item.name === draft["主类型"]);
  if (block) $("blockCode").value = block.code;
  if (mainType) $("typeCode").value = mainType.code;
  $("questionType").value = draft["题型"] || "";
  $("difficulty").value = draft["难度系数"] ?? "";
  $("knowledgePoints").value = metadataLines(draft["知识点"]);
  $("extraTypes").value = metadataLines(
    (draft["类型"] || []).filter((item) => item !== draft["主类型"]),
  );
}

async function classifyCurrentQuestion() {
  const questionText = $("questionText").value.trim();
  if (!questionText) {
    alert("请先填写题目。");
    return;
  }
  const settings = state.modelSettings || {};
  let consent = true;
  if (settings.cloud) {
    consent = confirm(
      "将把当前题目正文发送到所选云模型进行分类。不会发送答案、解析或整个题库。是否继续？",
    );
    if (!consent) return;
  }
  const resultBox = $("aiClassifyResult");
  resultBox.classList.remove("hidden");
  resultBox.textContent = "正在填写分类…";
  $("aiClassifyBtn").disabled = true;
  const response = await fetch("/api/ai/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_text: questionText, consent }),
  });
  const data = await response.json();
  $("aiClassifyBtn").disabled = false;
  if (!response.ok) {
    resultBox.textContent = data.detail || "自动填写失败，请手动选择分类。";
    return;
  }
  applyClassificationDraft(data.draft || {});
  const draft = data.draft || {};
  const confidence = Math.round(Number(draft["置信度"] || 0) * 100);
  const warnings = Array.isArray(draft["警告"]) && draft["警告"].length
    ? `；需注意：${draft["警告"].join("、")}`
    : "";
  resultBox.textContent =
    `建议已填入检查区（可信度 ${confidence}%）：${draft["理由"] || "请人工检查"}${warnings}。` +
    "点击“确认入库”前仍可修改，AI 不会直接写入正式题库。";
}

function bindEvents() {
  bindTaxonomyNavigation();
  $("draftBtn").addEventListener("click", generateDraft);
  $("convertWordBtn").addEventListener("click", convertWordToMarkdown);
  $("files").addEventListener("change", (event) => {
    setUploadItems(event.target.files);
    renderImagePreview();
  });
  for (const fieldId of MANUAL_SECTION_IDS) {
    $(fieldId).addEventListener("input", () => {
      renderManualPreviews();
      if (!$("reviewArea").classList.contains("hidden")) renderImagePreview();
    });
  }
  for (const fieldId of EDIT_SECTION_IDS) {
    $(fieldId).addEventListener("input", () => {
      renderEditPreviews();
      if ($("editDialog").open) renderEditingImages();
    });
  }
  for (const button of document.querySelectorAll("[data-formula-target]")) {
    button.addEventListener("click", () =>
      insertFormula(button.dataset.formulaTarget, button.dataset.formulaMode || "inline"),
    );
  }
  $("saveBtn").addEventListener("click", saveQuestion);
  $("librarySearchBtn").addEventListener("click", searchLibraryQuestions);
  $("libraryClearBtn").addEventListener("click", clearLibrarySearch);
  $("libraryQuery").addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchLibraryQuestions();
  });
  $("searchBtn").addEventListener("click", searchQuestions);
  $("assistantRecommendBtn").addEventListener("click", recommendQuestions);
  $("assistantAddAllBtn").addEventListener("click", addAllRecommendations);
  $("clearSelectionBtn").addEventListener("click", () => {
    state.selected.clear();
    state.displayLabels.clear();
    updateSelectedCount();
    searchQuestions();
  });
  $("exportBtn").addEventListener("click", exportExam);
  $("closeEditBtn").addEventListener("click", () => $("editDialog").close());
  $("saveEditBtn").addEventListener("click", saveQuestionEdit);
  $("closeBatchBtn").addEventListener("click", () => $("batchDialog").close());
  $("saveBatchBtn").addEventListener("click", saveBatchEdit);
  $("modelProvider").addEventListener("change", applyProviderDefaults);
  $("saveModelBtn").addEventListener("click", () => saveModelSettings());
  $("testModelBtn").addEventListener("click", testModelConnection);
  $("aiClassifyBtn").addEventListener("click", classifyCurrentQuestion);
  $("analyzeImportBtn").addEventListener("click", analyzeImportFile);
  $("saveImportDraftsBtn").addEventListener("click", () => saveImportDrafts());
  $("toggleAllImportDraftsBtn").addEventListener("click", toggleAllImportDrafts);
  $("commitImportBtn").addEventListener("click", commitImportDrafts);
  bindImageEditorEvents();
  renderManualPreviews();
}

bindWorkspaceNavigation();

if (window.location.protocol === "file:") {
  $("directOpenWarning").classList.remove("hidden");
} else {
  loadOptions().then(() => {
    bindEvents();
    refreshQuestionLists();
    loadModelSettings();
    loadImportStatus();
  });
}
