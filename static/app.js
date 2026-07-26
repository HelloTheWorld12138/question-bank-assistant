const state = {
  options: null,
  selected: new Set(),
  draftReady: false,
  wordDraftId: "",
  wordDraftImages: [],
  formulaItems: [],
  editingId: "",
  resultItems: new Map(),
  displayLabels: new Map(),
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
  $("questionType").appendChild(optionElement("", "未指定"));
  $("editQuestionType").appendChild(optionElement("", "未指定"));
  $("batchQuestionType").appendChild(optionElement("", "不修改"));
  for (const questionType of state.options.question_types || []) {
    $("questionType").appendChild(optionElement(questionType, questionType));
    $("searchQuestionType").appendChild(optionElement(questionType, questionType));
    $("editQuestionType").appendChild(optionElement(questionType, questionType));
    $("batchQuestionType").appendChild(optionElement(questionType, questionType));
  }
  for (const template of state.options.templates || []) {
    const label = template.available ? template.name : `${template.name}（缺失）`;
    const option = optionElement(template.key, label);
    option.disabled = !template.available;
    $("examTemplate").appendChild(option);
  }

  const status = $("pandocStatus");
  const importReady = Boolean(state.options.pandoc);
  if (state.options.pandoc) {
    const parts = ["已检测到 Pandoc"];
    const officeStatus = state.options.officecli || {};
    parts.push(officeStatus.available ? `OfficeCLI ${officeStatus.version || ""}`.trim() : "未检测到 OfficeCLI");
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
  appendFormValue(form, "question_type", $("questionType").value);
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
  renderExamSelection();
}

function renderExamSelection() {
  const holder = $("examSelectionList");
  holder.innerHTML = "";
  const ids = Array.from(state.selected);
  if (!ids.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "请先在上方搜索并勾选题目。";
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
    title.textContent = `${questionId} · ${item["题型"] || "未指定题型"} · ${item.preview || ""}`;
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

function renderResults(items) {
  state.resultItems = new Map(items.map((item) => [item.id, item]));
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
    actions.appendChild(editButton);
    actions.appendChild(copyButton);
    actions.appendChild(deleteButton);
    actionCell.appendChild(actions);
    row.appendChild(actionCell);
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

async function exportExam() {
  const mode = document.querySelector("input[name='exportMode']:checked").value;
  const result = $("exportResult");
  result.textContent = "正在生成...";
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
    const markdownLink = document.createElement("a");
    markdownLink.href = `/download/${encodeURIComponent(exported.exam_md_filename)}`;
    markdownLink.textContent = `下载 ${exported.exam_md_filename}`;
    result.appendChild(markdownLink);
    if (exported.docx_created) {
      const wordLink = document.createElement("a");
      wordLink.href = `/download/${encodeURIComponent(exported.exam_docx_filename)}`;
      wordLink.textContent = `下载 ${exported.exam_docx_filename}`;
      result.appendChild(wordLink);
    }
    if (exported.preview_filename) {
      const previewLink = document.createElement("a");
      previewLink.href = `/preview/${encodeURIComponent(exported.preview_filename)}`;
      previewLink.target = "_blank";
      previewLink.rel = "noopener";
      previewLink.textContent = `预览 ${exported.kind || "Word"}`;
      result.appendChild(previewLink);
    }
  }
  const summaryData = exportedFiles[0] || {};
  const summary = document.createElement("div");
  const validation = summaryData.validation || {};
  const issueCount = exportedFiles.reduce((total, item) => total + Number((item.issues || {}).count || 0), 0);
  const validationText = validation.performed
    ? validation.ok
      ? `结构校验通过，发现 ${issueCount} 个版式问题`
      : "结构校验未通过"
    : "未执行 OfficeCLI 结构校验";
  summary.textContent = separate
    ? `已分别生成 ${exportedFiles.length} 份文件 · ${summaryData.template_name || "默认模板"} · 共发现 ${issueCount} 个版式问题`
    : `${summaryData.template_name || "默认模板"} · ${summaryData.engine || "markdown"} · ${validationText}`;
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
        题型: $("editQuestionType").value,
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
  await searchQuestions();
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
  await searchQuestions();
  alert(`已修改 ${data.count} 道题。`);
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

function bindEvents() {
  $("draftBtn").addEventListener("click", generateDraft);
  $("convertWordBtn").addEventListener("click", convertWordToMarkdown);
  $("files").addEventListener("change", renderImagePreview);
  $("saveBtn").addEventListener("click", saveQuestion);
  $("searchBtn").addEventListener("click", searchQuestions);
  $("clearSelectionBtn").addEventListener("click", () => {
    state.selected.clear();
    state.displayLabels.clear();
    updateSelectedCount();
    searchQuestions();
  });
  $("exportBtn").addEventListener("click", exportExam);
  $("closeEditBtn").addEventListener("click", () => $("editDialog").close());
  $("saveEditBtn").addEventListener("click", saveQuestionEdit);
  $("batchEditBtn").addEventListener("click", openBatchEditor);
  $("closeBatchBtn").addEventListener("click", () => $("batchDialog").close());
  $("saveBatchBtn").addEventListener("click", saveBatchEdit);
  $("refreshMaintenanceBtn").addEventListener("click", refreshMaintenance);
  $("integrityBtn").addEventListener("click", checkIntegrity);
  $("rebuildIndexBtn").addEventListener("click", rebuildIndex);
  $("restoreTemplatesBtn").addEventListener("click", restoreDefaultTemplates);
  $("backupBtn").addEventListener("click", createBackup);
}

loadOptions().then(() => {
  bindEvents();
  searchQuestions();
  refreshMaintenance();
});
