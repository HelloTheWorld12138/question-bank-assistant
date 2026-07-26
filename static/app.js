const state = {
  options: null,
  selected: new Set(),
  draftReady: false,
  wordDraftId: "",
  wordDraftImages: [],
  formulaItems: [],
  editingId: "",
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
    $("editBlock").appendChild(optionElement(block.name, block.name));
  }
  for (const type of state.options.types) {
    $("typeCode").appendChild(optionElement(type.code, type.name));
    $("searchType").appendChild(optionElement(type.name, type.name));
    $("editMainType").appendChild(optionElement(type.name, type.name));
  }

  const status = $("pandocStatus");
  const importReady = Boolean(state.options.pandoc);
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
  $("convertWordBtn").disabled = !state.options.pandoc;
  if (!state.options.pandoc) {
    $("convertWordBtn").title = "需要 Pandoc 才能转换 Word；智能整理和公式 OCR 均为可选增强。";
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
  if (metadata["知识点"]) $("knowledgePoints").value = metadataLines(metadata["知识点"]);
  if (metadata["类型"]) $("extraTypes").value = metadataLines(metadata["类型"]);
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
  if (!(state.options && state.options.pandoc)) {
    alert("Word 单题导入需要 Pandoc。智能整理和公式 OCR 均为可选增强。");
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
  const target = $("convertTarget").value;
  if (target === "questionText") {
    $("questionText").value = sections.question || fallback;
    $("answerText").value = mergeText($("answerText").value, sections.answer || "");
    $("analysisText").value = mergeText($("analysisText").value, sections.analysis || "");
  } else {
    const sectionName = target === "answerText" ? "answer" : "analysis";
    const convertedText = sections[sectionName] || sections.question || data.text_markdown || fallback;
    $(target).value = mergeText($(target).value, convertedText);
  }
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
    cell.colSpan = 8;
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
    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "action-group";
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "ghost compact";
    editButton.textContent = "编辑";
    editButton.addEventListener("click", () => openQuestionEditor(item.id));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger compact";
    deleteButton.textContent = "删除";
    deleteButton.addEventListener("click", () => deleteQuestion(item.id));
    actions.appendChild(editButton);
    actions.appendChild(deleteButton);
    actionCell.appendChild(actions);
    row.appendChild(actionCell);
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
    body: JSON.stringify({
      ids: Array.from(state.selected),
      mode,
      title: $("examTitle").value.trim() || "试卷",
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    result.textContent = data.detail || "导出失败";
    return;
  }
  result.innerHTML = "";
  const markdownLink = document.createElement("a");
  markdownLink.href = `/download/${encodeURIComponent(data.exam_md_filename)}`;
  markdownLink.textContent = `下载 ${data.exam_md_filename}`;
  result.appendChild(markdownLink);
  if (data.docx_created) {
    const wordLink = document.createElement("a");
    wordLink.href = `/download/${encodeURIComponent(data.exam_docx_filename)}`;
    wordLink.textContent = `下载 ${data.exam_docx_filename}`;
    result.appendChild(wordLink);
  }
  if (data.pandoc_message) {
    const message = document.createElement("div");
    message.textContent = data.pandoc_message;
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
  $("editDifficulty").value = metadata["难度系数"] || "";
  $("editYear").value = metadata["年份"] || "";
  $("editSource").value = metadata["来源"] || "";
  $("editKnowledge").value = metadataLines(metadata["知识点"]);
  $("editTypes").value = metadataLines(metadata["类型"]);
  $("editQuestionText").value = sections["题目"] || "";
  $("editAnswerText").value = sections["答案"] || "";
  $("editAnalysisText").value = sections["解析"] || "";
  $("editRemarks").value = sections["备注"] || "";
  $("editDialog").showModal();
}

async function saveQuestionEdit() {
  if (!state.editingId) return;
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
  await searchQuestions();
}

async function deleteQuestion(questionId) {
  if (!confirm(`确定将 ${questionId} 移到回收站吗？可以稍后恢复。`)) return;
  const response = await fetch(`/api/questions/${encodeURIComponent(questionId)}`, { method: "DELETE" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "删除失败");
    return;
  }
  state.selected.delete(questionId);
  await Promise.all([searchQuestions(), refreshMaintenance()]);
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
  if (!confirm("确定扫描现有题目并重建编号索引吗？")) return;
  const response = await fetch("/api/index/rebuild", { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "索引修复失败");
    return;
  }
  $("maintenanceResult").textContent = `编号索引已修复，共识别 ${Object.keys(data.index || {}).length} 个编号前缀。`;
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
  $("closeEditBtn").addEventListener("click", () => $("editDialog").close());
  $("saveEditBtn").addEventListener("click", saveQuestionEdit);
  $("refreshMaintenanceBtn").addEventListener("click", refreshMaintenance);
  $("integrityBtn").addEventListener("click", checkIntegrity);
  $("rebuildIndexBtn").addEventListener("click", rebuildIndex);
  $("backupBtn").addEventListener("click", createBackup);
}

loadOptions().then(() => {
  bindEvents();
  searchQuestions();
  refreshMaintenance();
});
