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


def _inline_option_matches(line: str) -> list[re.Match[str]]:
    return list(INLINE_OPTION_MARKER_RE.finditer(line))


def _consecutive_option_orders(matches: list[re.Match[str]]) -> list[int]:
    orders = [_option_order(match.group("label")) for match in matches]
    if any(
        current != previous + 1 for previous, current in zip(orders, orders[1:])
    ):
        return []
    return orders


def _grouped_option_row_orders(line: str) -> list[int]:
    """Return explicit consecutive markers from one row of a two-column layout."""
    matches = _inline_option_matches(line)
    if len(matches) < 2 or line[: matches[0].start()].strip():
        return []
    if any(match.group("suffix").isspace() for match in matches):
        return []
    return _consecutive_option_orders(matches)


def _grouped_option_row_indexes(prepared: list[tuple[str, bool]]) -> set[int]:
    """Find neighboring rows such as “A… B…” followed by “C… D…”."""
    content_indexes = [
        index
        for index, (line, protected) in enumerate(prepared)
        if not protected and line.strip()
    ]
    grouped: set[int] = set()
    for left_index, right_index in zip(content_indexes, content_indexes[1:]):
        # Permit one technical blank line between the two option rows.
        if right_index - left_index > 2:
            continue
        if any(protected for _, protected in prepared[left_index + 1 : right_index]):
            continue
        left_orders = _grouped_option_row_orders(prepared[left_index][0])
        right_orders = _grouped_option_row_orders(prepared[right_index][0])
        combined = left_orders + right_orders
        if (
            left_orders
            and right_orders
            and len(combined) >= 4
            and combined == list(range(len(combined)))
        ):
            grouped.update((left_index, right_index))
    return grouped


def _split_inline_options(line: str, *, grouped_row: bool = False) -> list[str]:
    """Split a tabular A/B/C/D row without touching ordinary prose.

    Word commonly stores several choices in one paragraph separated by tabs.
    Pandoc may preserve those tabs or turn them into spaces. Requiring an
    A-first consecutive sequence prevents phrases such as “A、B 两点” from
    being treated as an option row.
    """
    matches = _inline_option_matches(line)
    if len(matches) < 2:
        return [line]

    orders = _consecutive_option_orders(matches)
    if not orders or (orders[0] != 0 and not grouped_row):
        return [line]
    if grouped_row and any(match.group("suffix").isspace() for match in matches):
        return [line]
    has_clear_separator = any(
        "\t" in match.group("prefix") or len(match.group("prefix")) >= 2
        for match in matches[1:]
    )
    if not grouped_row and not has_clear_separator:
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
        prepared.append((line, False))

    grouped_rows = _grouped_option_row_indexes(prepared)
    expanded: list[tuple[str, bool]] = []
    for index, (line, protected) in enumerate(prepared):
        if protected:
            expanded.append((line, True))
            continue
        expanded.extend(
            (option_line, False)
            for option_line in _split_inline_options(
                line,
                grouped_row=index in grouped_rows,
            )
        )
    prepared = expanded

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
