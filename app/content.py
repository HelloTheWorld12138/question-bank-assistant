from __future__ import annotations

import re


FENCE_RE = re.compile(r"^\s*(```|~~~)")
QUOTED_OPTION_RE = re.compile(
    r"^(?P<indent>[ \t]*)>\s*(?P<option>[A-HＡ-Ｈ](?:[．.、:：)）]|\s+).*)$"
)
PLAIN_OPTION_RE = re.compile(
    r"^[ \t]*[A-HＡ-Ｈ](?:[．.、:：)）]|\s+)"
)
QUOTE_SPACER_RE = re.compile(r"^[ \t]*>[ \t]*$")
STANDALONE_BLOCK_RE = re.compile(
    r"^\s*(?:!\[[^\]]*\]\([^)]+\)(?:\{[^}\n]*\})?|\$\$|\\\[|\\\])\s*$"
)
INLINE_OPTION_MARKER_RE = re.compile(
    r"(?P<prefix>^|(?:\t+|[ \u00a0]+))"
    r"(?P<label>[A-HＡ-Ｈ])"
    r"(?P<suffix>[．.、:：)）]|\s+)"
)


def _is_option_line(line: str) -> bool:
    return bool(PLAIN_OPTION_RE.match(line))


def _keep_blank_before_option(previous_line: str) -> bool:
    return bool(STANDALONE_BLOCK_RE.match(previous_line))


def _option_order(label: str) -> int:
    fullwidth = "ＡＢＣＤＥＦＧＨ"
    if label in fullwidth:
        return fullwidth.index(label)
    return ord(label.upper()) - ord("A")


def _split_inline_options(line: str) -> list[str]:
    """Split a tabular A/B/C/D row without touching ordinary prose.

    Word commonly stores several choices in one paragraph separated by tabs.
    Pandoc may preserve those tabs or turn them into spaces. Requiring an
    A-first consecutive sequence prevents phrases such as “A、B 两点” from
    being treated as an option row.
    """
    matches = list(INLINE_OPTION_MARKER_RE.finditer(line))
    if len(matches) < 2:
        return [line]

    orders = [_option_order(match.group("label")) for match in matches]
    if orders[0] != 0 or any(
        current != previous + 1 for previous, current in zip(orders, orders[1:])
    ):
        return [line]
    has_clear_separator = any(
        "\t" in match.group("prefix") or len(match.group("prefix")) >= 2
        for match in matches[1:]
    )
    if not has_clear_separator:
        has_explicit_markers = all(
            not match.group("suffix").isspace() for match in matches
        )
        if len(matches) < 3 or not has_explicit_markers:
            return [line]

    result: list[str] = []
    leading_text = line[: matches[0].start()].strip()
    if leading_text:
        result.append(leading_text)

    for index, match in enumerate(matches):
        start = match.start("label")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        option = line[start:end].strip()
        if option:
            result.append(option)
    return result


def normalize_line_breaks(value: str | None) -> str:
    """Give teacher-entered newlines one stable meaning across preview and Word.

    One newline stays a hard line break, one empty line stays a paragraph
    boundary, and Word/Pandoc blockquote syntax around A-D options is removed.
    Fenced code/raw OpenXML blocks are left untouched.
    """
    source = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    prepared: list[tuple[str, bool]] = []
    in_fence = False

    raw_lines = source.split("\n")
    for index, raw_line in enumerate(raw_lines):
        fence = FENCE_RE.match(raw_line)
        if fence:
            prepared.append((raw_line, True))
            in_fence = not in_fence
            continue
        if in_fence:
            prepared.append((raw_line, True))
            continue

        line = raw_line.rstrip()
        if QUOTE_SPACER_RE.fullmatch(line):
            previous_line = next(
                (candidate for candidate in reversed(raw_lines[:index]) if candidate.strip()),
                "",
            )
            next_line = next(
                (candidate for candidate in raw_lines[index + 1 :] if candidate.strip()),
                "",
            )
            if QUOTED_OPTION_RE.match(previous_line) or QUOTED_OPTION_RE.match(next_line):
                continue
        option = QUOTED_OPTION_RE.match(line)
        if option:
            line = f"{option.group('indent')}{option.group('option')}".rstrip()
        prepared.extend((option_line, False) for option_line in _split_inline_options(line))

    result: list[str] = []
    for index, (line, protected) in enumerate(prepared):
        if protected or line.strip():
            result.append(line)
            continue

        next_line = ""
        for candidate, candidate_protected in prepared[index + 1 :]:
            if candidate_protected or candidate.strip():
                next_line = candidate
                break
        previous_line = next((candidate for candidate in reversed(result) if candidate.strip()), "")

        if (
            next_line
            and _is_option_line(next_line)
            and previous_line
            and not _keep_blank_before_option(previous_line)
        ):
            continue
        if result and not result[-1].strip():
            continue
        result.append("")

    return "\n".join(result).strip()
