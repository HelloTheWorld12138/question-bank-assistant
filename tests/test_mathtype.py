from __future__ import annotations

import zipfile
from pathlib import Path

from app import mathtype


DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    xmlns:o="urn:schemas-microsoft-com:office:office"
    xmlns:v="urn:schemas-microsoft-com:vml">
  <w:body>
    <w:p>
      <w:r><w:t>由</w:t></w:r>
      <w:r>
        <w:object>
          <v:shape id="_x0000_i1026"><v:imagedata r:id="rIdImage"/></v:shape>
          <o:OLEObject ProgID="Equation.DSMT4" ObjectID="_1" r:id="rIdOle"/>
        </w:object>
      </w:r>
      <w:r><w:t>可得</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
"""

RELATIONSHIPS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage"
      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
      Target="media/formula.wmf"/>
  <Relationship Id="rIdOle"
      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
      Target="embeddings/oleObject1.bin"/>
</Relationships>
"""


def build_mathtype_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", DOCUMENT_XML)
        archive.writestr("word/_rels/document.xml.rels", RELATIONSHIPS_XML)
        archive.writestr("word/embeddings/oleObject1.bin", b"ole")
        archive.writestr("word/media/formula.wmf", b"wmf")


def test_inspect_and_prepare_mathtype_docx(tmp_path):
    source = tmp_path / "source.docx"
    prepared = tmp_path / "prepared.docx"
    build_mathtype_docx(source)

    objects = mathtype.inspect_mathtype_objects(source)

    assert len(objects) == 1
    assert objects[0].marker == "QBMATH000001"
    assert objects[0].ole_target == "word/embeddings/oleObject1.bin"
    assert objects[0].preview_target == "word/media/formula.wmf"
    assert objects[0].display is False

    prepared_objects = mathtype.prepare_docx_for_pandoc(source, prepared)
    with zipfile.ZipFile(prepared) as archive:
        document_xml = archive.read("word/document.xml")
    assert prepared_objects == objects
    assert b"QBMATH000001" in document_xml
    assert b"Equation.DSMT4" not in document_xml


def test_restore_mathtype_formula_as_editable_latex(tmp_path):
    source = tmp_path / "source.docx"
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    build_mathtype_docx(source)
    objects = mathtype.inspect_mathtype_objects(source)

    markdown, summary = mathtype.restore_mathtype_markers(
        "由*QBMATH000001*可得。",
        source,
        objects,
        {"QBMATH000001": r"a = \frac{F}{m}"},
        {},
        draft_dir,
        "draft-1",
    )

    assert markdown == r"由$a = \frac{F}{m}$可得。"
    assert summary["detected"] == 1
    assert summary["converted"] == 1
    assert summary["failed"] == 0
    assert not list(draft_dir.rglob("*"))


def test_failed_mathtype_formula_keeps_preview_for_review(tmp_path):
    source = tmp_path / "source.docx"
    draft_dir = tmp_path / "draft"
    draft_dir.mkdir()
    build_mathtype_docx(source)
    objects = mathtype.inspect_mathtype_objects(source)

    markdown, summary = mathtype.restore_mathtype_markers(
        "由QBMATH000001可得。",
        source,
        objects,
        {},
        {"QBMATH000001": "转换失败"},
        draft_dir,
        "draft-1",
    )

    assert "![公式](/draft-assets/draft-1/formula-fallback/QBMATH000001.wmf)" in markdown
    assert summary["converted"] == 0
    assert summary["failed"] == 1
    assert (draft_dir / "formula-fallback" / "QBMATH000001.wmf").read_bytes() == b"wmf"


def test_latex_function_names_are_normalized():
    assert mathtype._normalize_latex(r"sin\alpha:\sqrt{cos\beta}") == (
        r"\sin\alpha:\sqrt{\cos\beta}"
    )
