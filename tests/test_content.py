from app.content import normalize_line_breaks


def test_word_option_quotes_become_compact_teacher_lines():
    source = (
        "下列说法正确的是（　　）\n\n"
        "> A．选项一\n"
        ">\n"
        "> B．选项二\n"
        ">\n"
        "> C．选项三"
    )

    assert normalize_line_breaks(source) == (
        "下列说法正确的是（　　）\n"
        "A．选项一\n"
        "B．选项二\n"
        "C．选项三"
    )


def test_single_newline_and_paragraph_break_have_distinct_meanings():
    assert normalize_line_breaks("第一行\n第二行\n\n\n第三段") == (
        "第一行\n第二行\n\n第三段"
    )


def test_image_and_display_blocks_keep_paragraph_boundaries():
    source = (
        "如图所示。\n\n"
        "![题图](../assets/LXJC0001_01.png){width=70%}\n\n"
        "> A．选项一\n>\n> B．选项二"
    )

    assert normalize_line_breaks(source) == (
        "如图所示。\n\n"
        "![题图](../assets/LXJC0001_01.png){width=70%}\n\n"
        "A．选项一\nB．选项二"
    )


def test_raw_fenced_block_is_not_rewritten():
    source = "```{=openxml}\n> A．原始内容\n```"

    assert normalize_line_breaks(source) == source


def test_non_option_blockquote_spacing_is_preserved():
    source = "> 第一段引用\n>\n> 第二段引用"

    assert normalize_line_breaks(source) == source
