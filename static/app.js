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
  modelSettings: null,
  modelProviders: [],
  importTask: null,
  assistantRecommendations: [],
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
  for (const item of items) {
    state.resultItems.set(item.id, item);
  }
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
    add.textContent = state.selected.has(item.id) ? "已在试卷中" : "加入组卷";
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
    preview.textContent = item.preview || "暂无题目预览";
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
      "将把找题要求和本地筛选后的候选题元数据、题目短预览发送到所选云模型。" +
        "不会发送答案、完整解析或整个题库。是否继续？",
    );
    if (!consent) return;
  }
  $("assistantRecommendBtn").disabled = true;
  $("assistantResult").textContent = "正在本机解析要求并筛选候选题……";
  const response = await fetch("/api/assistant/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, use_ai: useAi, consent }),
  });
  const data = await response.json();
  $("assistantRecommendBtn").disabled = false;
  if (!response.ok) {
    $("assistantResult").textContent = data.detail || "智能找题失败";
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

function importDraftById(draftId) {
  return (state.importTask?.drafts || []).find((item) => item.id === draftId);
}

function bindDraftField(element, draft, field, transform = (value) => value) {
  element.value = Array.isArray(draft[field]) ? draft[field].join("\n") : String(draft[field] ?? "");
  element.addEventListener("input", () => {
    draft[field] = transform(element.value);
  });
  element.addEventListener("change", () => {
    draft[field] = transform(element.value);
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

function renderImportDrafts() {
  const holder = $("importDrafts");
  holder.innerHTML = "";
  const task = state.importTask;
  if (!task || !(task.drafts || []).length) {
    $("saveImportDraftsBtn").disabled = true;
    $("commitImportBtn").disabled = true;
    return;
  }
  $("saveImportDraftsBtn").disabled = false;
  $("commitImportBtn").disabled = false;
  task.drafts.forEach((draft, index) => {
    const card = document.createElement("article");
    card.className = `import-draft-card${draft.requires_attention ? " needs-attention" : ""}`;
    card.dataset.draftId = draft.id;

    const header = document.createElement("div");
    header.className = "import-draft-header";
    const title = document.createElement("div");
    const confidence = Math.round(Number(draft.confidence || 0) * 100);
    const numberText = draft.original_number ? `原题号 ${draft.original_number}` : "未识别原题号";
    title.textContent = `草稿 ${index + 1} · ${numberText} · 第 ${draft.page || 1} 页 · 置信度 ${confidence}%`;
    const confirmedLabel = document.createElement("label");
    confirmedLabel.className = "confirm-draft";
    const confirmed = document.createElement("input");
    confirmed.type = "checkbox";
    confirmed.checked = Boolean(draft.confirmed);
    confirmed.disabled = Boolean(draft.committed_id);
    confirmed.addEventListener("change", () => {
      draft.confirmed = confirmed.checked;
    });
    confirmedLabel.append(confirmed, draft.committed_id ? ` 已入库：${draft.committed_id}` : " 已对照原文核对");
    header.append(title, confirmedLabel);
    card.appendChild(header);

    if ((draft.warnings || []).length) {
      const warning = document.createElement("div");
      warning.className = "draft-warning";
      warning.textContent = draft.warnings.join("；");
      card.appendChild(warning);
    }

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
        "主类型",
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
    metadataGrid.appendChild(draftLabel("难度系数", difficulty));
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
    bindDraftField(question, draft, "question");
    card.appendChild(draftLabel("题目正文", question));

    const answerGrid = document.createElement("div");
    answerGrid.className = "two-col";
    const answer = document.createElement("textarea");
    answer.rows = 5;
    bindDraftField(answer, draft, "answer");
    const analysis = document.createElement("textarea");
    analysis.rows = 5;
    bindDraftField(analysis, draft, "analysis");
    answerGrid.append(draftLabel("答案", answer), draftLabel("解析", analysis));
    card.appendChild(answerGrid);

    if ((draft.images || []).length) {
      const images = document.createElement("div");
      images.className = "import-image-list";
      for (const image of draft.images) {
        const imageCard = document.createElement("div");
        imageCard.className = "import-image-card";
        const preview = document.createElement("img");
        preview.src = image.url;
        preview.alt = image.name;
        const buttons = document.createElement("div");
        buttons.className = "action-group";
        for (const [action, label] of [
          ["rotate_left", "左转"],
          ["rotate_right", "右转"],
          ["enhance", "去阴影增强"],
          ["crop", "裁剪"],
          ["perspective", "透视校正"],
        ]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "ghost compact";
          button.textContent = label;
          button.addEventListener("click", () => processImportImage(draft.id, image.name, action));
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
  $("ocrStatus").textContent = data.ocr?.message || "未检测到 OCR";
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
  $("importResult").textContent = "正在提取文字、图片并切分题目，请稍候……";
  const response = await fetch("/api/import/analyze", { method: "POST", body: form });
  const data = await response.json();
  $("analyzeImportBtn").disabled = false;
  if (!response.ok) {
    $("importResult").textContent = data.detail || "导入分析失败";
    return;
  }
  state.importTask = data;
  $("importResult").textContent =
    `已生成 ${data.drafts?.length || 0} 道待审核草稿。请逐题对照原文，勾选“已核对”后再入库。`;
  renderImportDrafts();
  await loadImportStatus();
}

async function loadImportTask(taskId) {
  const response = await fetch(`/api/import/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json();
  if (!response.ok) {
    alert(data.detail || "读取导入任务失败");
    return;
  }
  state.importTask = data;
  $("importResult").textContent = `正在继续审核 ${data.source}，任务状态：${data.status}。`;
  renderImportDrafts();
  document.querySelector(".import-center")?.scrollIntoView({ behavior: "smooth" });
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
  if (!quiet) $("importResult").textContent = "审核草稿已保存，尚未写入正式题库。";
  renderImportDrafts();
  return true;
}

async function commitImportDrafts() {
  if (!state.importTask) return;
  const selectedIds = state.importTask.drafts.filter((item) => item.confirmed && !item.committed_id).map((item) => item.id);
  if (!selectedIds.length) {
    alert("请先逐题核对并勾选“已对照原文核对”。");
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
  await Promise.all([loadImportTask(state.importTask.id), searchQuestions(), loadImportStatus()]);
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

async function processImportImage(draftId, imageName, action) {
  let payload = { action };
  if (action === "crop") {
    const raw = prompt("输入保留范围：左,上,右,下（百分比），例如 5,5,95,95", "5,5,95,95");
    if (!raw) return;
    const values = raw.split(/[,，]/).map((item) => Number(item.trim()) / 100);
    if (values.length !== 4 || values.some((item) => !Number.isFinite(item))) {
      alert("裁剪范围格式不正确。");
      return;
    }
    payload.crop = { left: values[0], top: values[1], right: values[2], bottom: values[3] };
  }
  if (action === "perspective") {
    const raw = prompt(
      "输入左上、右上、右下、左下四点的 x,y 百分比，例如 2,3;98,2;97,98;3,97",
      "2,3;98,2;97,98;3,97",
    );
    if (!raw) return;
    const corners = raw.split(";").map((point) => point.split(/[,，]/).map((item) => Number(item.trim()) / 100));
    if (corners.length !== 4 || corners.some((point) => point.length !== 2 || point.some((item) => !Number.isFinite(item)))) {
      alert("透视角点格式不正确。");
      return;
    }
    payload.perspective = corners;
  }
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
  await loadImportTask(state.importTask.id);
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
      ? "API Key 已安全保存"
      : "尚未保存 API Key"
    : "本地模型不需要 API Key";
  $("modelStatus").textContent =
    `${settings.provider_name || "模型服务"} · ${settings.model || "未设置模型"} · ${keyText}` +
    (settings.local_only ? " · 当前禁止连接云模型" : "");
  $("aiClassifyBtn").disabled = !settings.enabled;
  $("aiClassifyBtn").title = settings.enabled ? "" : "请先在下方启用并保存 AI 辅助设置。";
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
    ? "留空表示保持原有 Key"
    : "本地模型不需要填写";
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
    alert("请先填写题目正文。");
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
  resultBox.textContent = "正在生成分类建议……";
  $("aiClassifyBtn").disabled = true;
  const response = await fetch("/api/ai/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_text: questionText, consent }),
  });
  const data = await response.json();
  $("aiClassifyBtn").disabled = false;
  if (!response.ok) {
    resultBox.textContent = data.detail || "AI 分类失败；你仍可手动填写并入库。";
    return;
  }
  applyClassificationDraft(data.draft || {});
  const draft = data.draft || {};
  const confidence = Math.round(Number(draft["置信度"] || 0) * 100);
  const warnings = Array.isArray(draft["警告"]) && draft["警告"].length
    ? `；需注意：${draft["警告"].join("、")}`
    : "";
  resultBox.textContent =
    `建议已填入审核区（置信度 ${confidence}%）：${draft["理由"] || "请人工检查"}${warnings}。` +
    "点击“确认入库”前仍可修改，AI 不会直接写入正式题库。";
}

function bindEvents() {
  $("draftBtn").addEventListener("click", generateDraft);
  $("convertWordBtn").addEventListener("click", convertWordToMarkdown);
  $("files").addEventListener("change", renderImagePreview);
  $("saveBtn").addEventListener("click", saveQuestion);
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
  $("batchEditBtn").addEventListener("click", openBatchEditor);
  $("closeBatchBtn").addEventListener("click", () => $("batchDialog").close());
  $("saveBatchBtn").addEventListener("click", saveBatchEdit);
  $("refreshMaintenanceBtn").addEventListener("click", refreshMaintenance);
  $("integrityBtn").addEventListener("click", checkIntegrity);
  $("rebuildIndexBtn").addEventListener("click", rebuildIndex);
  $("restoreTemplatesBtn").addEventListener("click", restoreDefaultTemplates);
  $("backupBtn").addEventListener("click", createBackup);
  $("modelProvider").addEventListener("change", applyProviderDefaults);
  $("saveModelBtn").addEventListener("click", () => saveModelSettings());
  $("testModelBtn").addEventListener("click", testModelConnection);
  $("aiClassifyBtn").addEventListener("click", classifyCurrentQuestion);
  $("analyzeImportBtn").addEventListener("click", analyzeImportFile);
  $("saveImportDraftsBtn").addEventListener("click", () => saveImportDrafts());
  $("commitImportBtn").addEventListener("click", commitImportDrafts);
}

loadOptions().then(() => {
  bindEvents();
  searchQuestions();
  refreshMaintenance();
  loadModelSettings();
  loadImportStatus();
});
