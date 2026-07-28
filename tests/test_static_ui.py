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

    for task in ("批量导入", "录入单题", "题库列表", "题库维护", "系统设置", "组卷并导出"):
        assert task in html
    assert 'data-module-menu="entry"' in html
    assert 'data-module-menu="library"' in html
    assert 'data-module-menu="export"' in html
