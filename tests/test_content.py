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


def test_tab_separated_options_are_split_into_one_line_each():
    source = (
        "下列说法正确的是（　　）\n"
        "A．选项一\tB．选项二\tC．选项三\tD．选项四"
    )

    assert normalize_line_breaks(source) == (
        "下列说法正确的是（　　）\n"
        "A．选项一\n"
        "B．选项二\n"
        "C．选项三\n"
        "D．选项四"
    )


def test_repeated_space_options_and_leading_stem_are_split():
    source = "请选择  A. 甲  B. 乙  C. 丙  D. 丁"

    assert normalize_line_breaks(source) == "请选择\nA. 甲\nB. 乙\nC. 丙\nD. 丁"


def test_word_tabs_rewritten_as_single_spaces_still_split_full_option_row():
    source = "A．选项一 B．选项二 C．选项三 D．选项四"

    assert normalize_line_breaks(source) == (
        "A．选项一\nB．选项二\nC．选项三\nD．选项四"
    )


def test_fullwidth_tab_separated_options_are_split():
    source = "Ａ．甲\tＢ．乙\tＣ．丙\tＤ．丁"

    assert normalize_line_breaks(source) == "Ａ．甲\nＢ．乙\nＣ．丙\nＤ．丁"


def test_ordinary_letter_references_are_not_split():
    source = "已知 A、B 两点相距 2 m，且 A 到 C 的距离更短。"

    assert normalize_line_breaks(source) == source


def test_out_of_order_option_markers_are_not_split():
    source = "A．甲\tC．丙\tB．乙"

    assert normalize_line_breaks(source) == source


def test_short_single_space_letter_sequence_is_not_treated_as_option_row():
    source = "A．点和 B．点分别位于斜面两端。"

    assert normalize_line_breaks(source) == source


def test_single_space_physics_variables_are_not_treated_as_options():
    source = "A = 1 B = 2 C = 3 时，系统处于平衡状态。"

    assert normalize_line_breaks(source) == source
