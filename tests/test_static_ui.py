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


def test_teacher_import_fields_enforce_word_and_image_roles():
    html = (config.ROOT / "static" / "index.html").read_text(encoding="utf-8")
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")
    stylesheet = (config.ROOT / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="batchImportFile" type="file" accept=".docx"' in html
    assert 'id="batchAnswerFile" type="file" accept=".docx"' in html
    assert "仅支持 .docx Word 文件，不支持 PDF。" in html
    assert "题目图片（可不选）" in html
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


def test_import_review_uses_one_full_preview_without_confidence_banner():
    javascript = (config.ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "识别可信度" not in javascript
    assert 'previewSummary.textContent = "查看完整排版效果"' in javascript
    assert '["题目", questionPreview]' in javascript
    assert '["答案", answerPreview]' in javascript
    assert '["解析", analysisPreview]' in javascript
