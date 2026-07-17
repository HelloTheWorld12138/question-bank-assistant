const state = {
  options: null,
  selected: new Set(),
  draftReady: false,
  wordDraftId: "",
  wordDraftImages: [],
  formulaItems: [],
};

const $ = (id) => document.getElementById(id);

function optionElement(value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  return option;
}

async function loadOptions() {
  const response = await fetch("/api/options");
  state.options = await response.json();

  for (const block of state.options.blocks) {
    $("blockCode").appendChild(optionElement(block.code, block.name));
    $("searchBlock").appendChild(optionElement(block.name, block.name));
  }
  for (const type of state.options.types) {
    $("typeCode").appendChild(optionElement(type.code, type.name));
    $("searchType").appendChild(optionElement(type.name, type.name));
  }

  const status = $("pandocStatus");
  const importReady = Boolean(state.options.pandoc && state.options.agent && state.options.formula_ocr);
  if (state.options.pandoc) {
    const parts = ["已检测到 Pandoc"];
    parts.push(state.options.agent ? "本地 agent" : "未检测到本地 agent");
    parts.push(state.options.formula_ocr ? "公式 OCR" : "未检测到公式 OCR");
    status.textContent = parts.join(" / ");
    status.classList.add(importReady ? "ok" : "warn");
  } else {
    status.textContent = "未检测到 Pandoc，仅能生成 exam.md";
    status.classList.add("warn");
  }
  $("convertWordBtn").disabled = !importReady;
  if (!importReady) {
    $("convertWordBtn").title = "需要同时接入 Pandoc、本地 opencode agent 和本地公式 OCR 后才能使用 Word 单题导入。";
  }
}

function setSaveEnabled() {
  const unresolved = state.formulaItems.some((item) => !item.confirmed);
  $("saveBtn").disabled = !state.draftReady || unresolved;
}

function renderImagePreview() {
  const holder = $("imagePreview");
  holder.innerHTML = "";
  const files = Array.from($("files").files || []);
  const images = files.filter((file) => file.type.startsWith("image/"));
  const hasWordImages = state.wordDraftImages.length > 0;
  if (!images.length && !hasWordImages) {
    holder.textContent = "未选择图片。Word/PDF 附件会随题号保存，但不写入图片列表。";
    return;
  }
  for (const image of state.wordDraftImages) {
    if (image.url && !image.url.toLowerCase().endsWith(".wmf") && !image.url.toLowerCase().endsWith(".emf")) {
      const img = document.createElement("img");
      img.src = image.url;
      img.alt = image.name;
      holder.appendChild(img);
    } else {
      const chip = document.createElement("span");
      chip.className = "file-chip";
      chip.textContent = image.name || "媒体文件";
      holder.appendChild(chip);
    }
  }
  for (const file of images) {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    holder.appendChild(img);
  }
}

function generateDraft() {
  if (!$("questionText").value.trim()) {
    alert("请先填写题目正文。");
    return;
  }
  state.draftReady = true;
  $("draftHint").classList.add("hidden");
  $("reviewArea").classList.remove("hidden");
  setSaveEnabled();
  renderImagePreview();
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
  if (metadata["知识点"]) $("knowledgePoints").value = metadata["知识点"];
  if (metadata["类型"]) $("extraTypes").value = metadata["类型"];
  if (metadata["备注"]) $("remarks").value = metadata["备注"];
}

function replaceFormulaLink(url, latex) {
  const trimmed = (latex || "").trim();
  if (!trimmed) return;
  const escaped = trimmed.startsWith("$") ? trimmed : `$${trimmed}$`;
  for (const id of ["questionText", "answerText", "analysisText"]) {
    const field = $(id);
    field.value = field.value.split(`](${url})`).join(`](${url})`);
    const pattern = new RegExp(`!\\[[^\\]]*\\]\\(${url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\)`, "g");
    field.value = field.value.replace(pattern, escaped);
  }
}

function renderFormulaPanel() {
  const panel = $("formulaPanel");
  const list = $("formulaList");
  list.innerHTML = "";
  if (!state.formulaItems.length) {
    panel.classList.add("hidden");
    setSaveEnabled();
    return;
  }
  panel.classList.remove("hidden");
  for (const item of state.formulaItems) {
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
    label.textContent = item.reason || "疑似公式图片";
    const textarea = document.createElement("textarea");
    textarea.rows = 3;
    textarea.value = item.latex || "";
    textarea.placeholder = item.ocr_error || "填写或修正 LaTeX，例如 \\frac{a}{b}";
    textarea.addEventListener("input", () => {
      item.latex = textarea.value;
      item.confirmed = false;
      checkbox.checked = false;
      setSaveEnabled();
    });

    const checkboxLabel = document.createElement("label");
    checkboxLabel.className = "formula-confirm";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = item.confirmed;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked && !textarea.value.trim()) {
        checkbox.checked = false;
        alert("请先填写 LaTeX，再确认这个公式。");
        return;
      }
      item.confirmed = checkbox.checked;
      item.latex = textarea.value;
      if (item.confirmed) replaceFormulaLink(item.url, item.latex);
      setSaveEnabled();
    });
    checkboxLabel.appendChild(checkbox);
    checkboxLabel.append("确认并替换为可编辑公式");

    const context = document.createElement("div");
    context.className = "formula-context";
    context.textContent = item.context || "";

    editor.appendChild(label);
    editor.appendChild(textarea);
    if (item.ocr_error) {
      const error = document.createElement("div");
      error.className = "formula-error";
      error.textContent = item.ocr_error;
      editor.appendChild(error);
    }
    editor.appendChild(checkboxLabel);
    editor.appendChild(context);
    row.appendChild(preview);
    row.appendChild(editor);
    list.appendChild(row);
  }
  setSaveEnabled();
}

async function convertWordToMarkdown() {
  if (!(state.options && state.options.pandoc && state.options.agent && state.options.formula_ocr)) {
    alert("Word 单题导入需要先接入本地 opencode agent 和本地公式 OCR。");
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
  button.textContent = "转换中...";

  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/convert-docx", { method: "POST", body: form });
  const data = await response.json();

  button.disabled = false;
  button.textContent = originalText;

  if (!response.ok) {
    alert(data.detail || "Word 转 Markdown 失败。");
    return;
  }

  const sections = data.sections || {};
  const fallback = data.markdown || "";
  $("questionText").value = sections.question || fallback;
  $("answerText").value = sections.answer || "";
  $("analysisText").value = sections.analysis || "";
  fillMetadata(data.metadata || {});

  state.wordDraftId = data.draft_id || "";
  state.wordDraftImages = data.images || [];
  state.formulaItems = data.formula_items || [];
  state.draftReady = Boolean($("questionText").value.trim());
  renderImagePreview();
  renderFormulaPanel();
  if (state.draftReady) {
    $("draftHint").classList.add("hidden");
    $("reviewArea").classList.remove("hidden");
    setSaveEnabled();
  }

  const warnings = data.warnings || [];
  if (warnings.length) {
    alert(`Word 已转换，但需要人工检查：\n\n${warnings.join("\n")}`);
  }
}

function appendFormValue(form, key, value) {
  form.append(key, value == null ? "" : String(value));
}

async function saveQuestion() {
  if (!state.draftReady) return;
  const unresolved = state.formulaItems.filter((item) => !item.confirmed);
  if (unresolved.length) {
    alert(`还有 ${unresolved.length} 个疑似公式图片没有确认，不能入库。`);
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
  appendFormValue(form, "remarks", $("remarks").value);
  appendFormValue(form, "draft_id", state.wordDraftId);
  for (const file of $("files").files) {
    form.append("files", file);
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
  renderFormulaPanel();
  $("draftHint").classList.remove("hidden");
  $("reviewArea").classList.add("hidden");
  $("saveBtn").disabled = true;
  await searchQuestions();
}

function updateSelectedCount() {
  $("selectedCount").textContent = state.selected.size;
}

function renderResults(items) {
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
      if (checkbox.checked) state.selected.add(item.id);
      else state.selected.delete(item.id);
      updateSelectedCount();
    });
    checkboxCell.appendChild(checkbox);

    const values = [
      item.id,
      item["板块"] || "",
      item["主类型"] || "",
      item["难度"] || "",
      item["来源"] || "",
      item.preview || "",
    ];
    row.appendChild(checkboxCell);
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
}

async function searchQuestions() {
  const params = new URLSearchParams({
    block: $("searchBlock").value,
    main_type: $("searchType").value,
    difficulty: $("searchDifficulty").value,
    year: $("searchYear").value,
    source: $("searchSource").value,
    knowledge: $("searchKnowledge").value,
  });
  const response = await fetch(`/api/questions?${params}`);
  const data = await response.json();
  renderResults(data.items || []);
  updateSelectedCount();
}

async function exportExam() {
  const mode = document.querySelector("input[name='exportMode']:checked").value;
  const result = $("exportResult");
  result.textContent = "正在生成...";
  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: Array.from(state.selected), mode }),
  });
  const data = await response.json();
  if (!response.ok) {
    result.textContent = data.detail || "导出失败";
    return;
  }
  const links = [`<a href="/download/exam.md">下载 exam.md</a>`];
  if (data.docx_created) {
    links.push(`<a href="/download/exam.docx">下载 exam.docx</a>`);
  }
  const message = data.pandoc_message ? `<div>${data.pandoc_message}</div>` : "";
  result.innerHTML = `${links.join("　")}${message}`;
}

function bindEvents() {
  $("draftBtn").addEventListener("click", generateDraft);
  $("convertWordBtn").addEventListener("click", convertWordToMarkdown);
  $("files").addEventListener("change", renderImagePreview);
  $("saveBtn").addEventListener("click", saveQuestion);
  $("searchBtn").addEventListener("click", searchQuestions);
  $("clearSelectionBtn").addEventListener("click", () => {
    state.selected.clear();
    updateSelectedCount();
    searchQuestions();
  });
  $("exportBtn").addEventListener("click", exportExam);
}

loadOptions().then(() => {
  bindEvents();
  searchQuestions();
});
