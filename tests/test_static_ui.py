from app import config


def test_teacher_ui_uses_three_task_modules():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert html.count('class="module-nav-item') == 3
    assert "<strong>录入题库</strong>" in html
    assert "<strong>查看题库</strong>" in html
    assert "<strong>导出题目</strong>" in html
    assert 'data-workspace-target="home"' not in html


def test_secondary_tasks_are_grouped_under_their_modules():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")

    for task in ("批量导入", "录入单题", "浏览与修改", "系统设置", "选择题目", "组卷并导出"):
        assert task in html
    assert 'data-module-menu="entry"' in html
    assert 'data-module-menu="library"' in html
    assert 'data-module-menu="export"' in html
    assert 'data-workspace-view="maintenance"' not in html
    assert "题库备份" not in html


def test_sidebar_exposes_two_question_bank_taxonomies_and_settings_shortcut():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'data-taxonomy-mode="block"' in html
    assert 'data-taxonomy-mode="type"' in html
    assert 'id="taxonomyList"' in html
    assert 'class="header-settings" data-workspace-target="settings"' in html
    assert "function renderTaxonomyList()" in javascript
    assert 'switchWorkspaceView("library")' in javascript


def test_secondary_navigation_is_in_header_and_footer_shows_product_status():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")

    header_start = html.index('<header class="app-header">')
    header_end = html.index("</header>", header_start)
    header = html[header_start:header_end]
    sidebar_start = html.index('<div class="navigation-shell">')
    sidebar_end = html.index('<main class="layout">', sidebar_start)
    sidebar = html[sidebar_start:sidebar_end]

    assert 'class="header-workspace-nav subtask-nav"' in header
    assert 'data-module-menu="entry"' in header
    assert 'data-module-menu="entry"' not in sidebar
    assert "题库已就绪" in header
    assert "题库状态正常" in sidebar
    assert 'id="sidebarVersion"' in sidebar
    assert 'aria-label="用户 Helios"' not in header
    library_menu = header.split('data-module-menu="library"', 1)[1].split("</div>", 1)[0]
    assert 'data-workspace-target="settings"' not in library_menu
    assert 'settings: "settings"' in javascript


def test_import_review_can_select_all_pending_drafts():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="toggleAllImportDraftsBtn"' in html
    assert "function toggleAllImportDrafts()" in javascript


def test_import_defaults_to_mechanics_in_manual_and_batch_review():
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")
    routes = (config.ROOT / "app" / "api" / "routes.py").read_text(encoding="utf-8")

    assert '$("blockCode").value = state.options.default_block_code || "LX"' in javascript
    assert "draft.block_code = state.options.default_block_code || \"LX\"" in javascript
    assert '"default_block_code": config.DEFAULT_BLOCK_CODE' in routes


def test_teacher_import_fields_enforce_word_and_image_roles():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")
    stylesheet = (config.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    desktop = (config.ROOT / "desktop.py").read_text(encoding="utf-8")

    assert 'id="batchImportFile" type="file" accept=".docx"' in html
    assert 'id="batchAnswerFile" type="file" accept=".docx"' in html
    assert "旧版 .doc 请先在 Word 中另存为 .docx" in html
    assert "题目图片（可多选）" in html
    assert 'id="manualImageWorkspace"' in html
    assert "图片调整" in html
    assert 'id="files" type="file" multiple accept="image/*"' in html
    assert "从 Word 自动整理题目" in html
    assert 'id="convertTarget"' not in html
    assert 'class="import-source-grid"' in html
    assert 'class="word-convert-field"' in html
    assert 'class="content-field question-workbench"' in html
    assert 'const MATHTYPE_FALLBACK_RE = /^QBMATH' in javascript
    assert "formulaNames.has(name) || MATHTYPE_FALLBACK_RE.test(name)" in javascript
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "—" not in html + javascript + stylesheet
    assert 'role="status" aria-live="polite"' in html
    assert 'setAttribute("aria-selected", String(active))' in javascript
    assert "wordLink.download = exported.exam_docx_filename" in javascript
    assert "fallbackLink.download = exported.exam_md_filename" in javascript
    assert 'webview.settings["ALLOW_DOWNLOADS"] = True' in desktop
    assert "--font-ui: 14px" in stylesheet
    assert "button.secondary:disabled" in stylesheet
    assert "color: #465761" in stylesheet


def test_manual_image_picker_appends_each_selection():
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")
    function_source = javascript.split("function setUploadItems(fileList)", 1)[1].split(
        "\n}\n\nfunction imageLocations",
        1,
    )[0]

    assert "state.uploadItems.push(...manualUploads);" in function_source
    assert '$(\"files\").value = \"\";' in function_source
    assert "state.uploadItems = convertedWordUploads.concat(manualUploads);" not in function_source
    assert "URL.revokeObjectURL" not in function_source
    assert 'fetch("/api/images/process"' in javascript
    assert "function manualImageActions(item)" in javascript
    assert "processedBeforeEnhance" in javascript
    assert "preserveEnhance" in javascript
    for label in ("左转", "右转", "去阴影", "裁剪", "透视校正", "恢复原图"):
        assert label in javascript


def test_import_review_uses_one_full_preview_without_confidence_banner():
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "识别可信度" not in javascript
    assert 'previewSummary.textContent = "查看完整排版效果"' in javascript
    assert '["题目", questionPreview]' in javascript
    assert '["答案", answerPreview]' in javascript
    assert '["解析", analysisPreview]' in javascript


def test_library_and_export_use_matching_question_filters():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")

    for suffix in (
        "Query",
        "Block",
        "Type",
        "Difficulty",
        "Year",
        "Source",
        "Knowledge",
        "QuestionType",
        "Sort",
    ):
        assert f'id="library{suffix}"' in html
        assert f'id="search{suffix}"' in html
    assert 'id="libraryResultsList"' in html
    assert 'id="resultsList"' in html
    assert html.count('class="question-filter-panel"') == 2


def test_question_catalog_replaces_ai_recommendation_and_table_rows():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")
    stylesheet = (config.ROOT / "static" / "style.css").read_text(encoding="utf-8")

    removed_content = html + javascript
    assert "按组卷要求找题" not in removed_content
    assert "assistantRecommendBtn" not in removed_content
    assert "assistantAddAllBtn" not in removed_content
    assert "libraryResultsBody" not in removed_content
    assert "resultsBody" not in removed_content
    assert "function createQuestionCard(item, mode)" in javascript
    assert 'question.setAttribute("aria-expanded", "false")' in javascript
    assert 'questionSolutionSection("答案"' in javascript
    assert 'questionSolutionSection("解析"' in javascript
    assert ".question-card-question" in stylesheet
    assert ".question-solution[hidden]" in stylesheet
