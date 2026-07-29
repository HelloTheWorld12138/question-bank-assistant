from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

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

ALTERNATE_PREFIX_DOCUMENT_XML = DOCUMENT_XML.replace("<w:", "<doc:").replace(
    "</w:", "</doc:"
).replace("xmlns:w=", "xmlns:doc=").replace(
    'ProgID="Equation.DSMT4"', 'ProgID="Equation.DSMT4.0"'
)
IGNORABLE_NAMESPACE_DOCUMENT_XML = DOCUMENT_XML.replace(
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"\n'
    '    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"\n'
    '    xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"\n'
    '    mc:Ignorable="w14"',
)


def build_mathtype_docx(
    path: Path,
    *,
    document_xml: str = DOCUMENT_XML,
    relationships_xml: str = RELATIONSHIPS_XML,
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", relationships_xml)
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


def test_mathtype_detection_accepts_real_world_progid_and_xml_prefix_variants(tmp_path):
    source = tmp_path / "variant.docx"
    prepared = tmp_path / "prepared.docx"
    relationships = RELATIONSHIPS_XML.replace(
        'Target="embeddings/oleObject1.bin"',
        'Target="/word/embeddings/oleObject1.bin"',
    )
    build_mathtype_docx(
        source,
        document_xml=ALTERNATE_PREFIX_DOCUMENT_XML,
        relationships_xml=relationships,
    )

    objects = mathtype.prepare_docx_for_pandoc(source, prepared)

    assert len(objects) == 1
    assert objects[0].prog_id == "Equation.DSMT4.0"
    assert objects[0].ole_target == "word/embeddings/oleObject1.bin"
    with zipfile.ZipFile(prepared) as archive:
        prepared_xml = archive.read("word/document.xml")
    assert b"QBMATH000001" in prepared_xml
    assert b"Equation.DSMT4.0" not in prepared_xml


def test_mathtype_preprocessing_preserves_unused_compatibility_namespaces(tmp_path):
    source = tmp_path / "compatibility.docx"
    prepared = tmp_path / "prepared.docx"
    build_mathtype_docx(source, document_xml=IGNORABLE_NAMESPACE_DOCUMENT_XML)

    mathtype.prepare_docx_for_pandoc(source, prepared)

    with zipfile.ZipFile(prepared) as archive:
        prepared_xml = archive.read("word/document.xml")
    assert b'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' in prepared_xml
    assert b'mc:Ignorable="w14"' in prepared_xml
    assert b"QBMATH000001" in prepared_xml


def test_mathtype_status_requires_a_working_converter_runtime(monkeypatch):
    mathtype._converter_runtime_status.cache_clear()
    monkeypatch.setattr(
        mathtype,
        "_converter_runtime_status",
        lambda: (False, "公式转换依赖不完整"),
    )

    status = mathtype.mathtype_status()

    assert status["available"] is False
    assert "依赖不完整" in status["message"]


def test_large_mathtype_batch_uses_stdin_manifest(monkeypatch, tmp_path):
    objects = [
        mathtype.MathTypeObject(
            marker=f"QBMATH{index:06d}",
            prog_id="Equation.DSMT4",
            object_id=f"_{index}",
            ole_target=f"word/embeddings/oleObject{index}.bin",
            preview_target=f"word/media/formula{index}.wmf",
            display=False,
        )
        for index in range(1, 401)
    ]
    captured = {}

    monkeypatch.setattr(mathtype, "find_ruby", lambda: "ruby")
    monkeypatch.setattr(
        mathtype,
        "mathtype_status",
        lambda: {"available": True, "message": "可读取旧版 MathType 公式"},
    )
    monkeypatch.setattr(
        mathtype,
        "_extract_ole_objects",
        lambda source, items, destination: {
            item.marker: destination / f"{item.marker}.bin" for item in items
        },
    )
    monkeypatch.setattr(mathtype, "_vendor_rubylib", lambda runtime_dir: "vendor-ruby")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        manifest = json.loads(kwargs["input"])
        encoded = base64.b64encode(b"<math><mi>x</mi></math>").decode("ascii")
        stdout = "\n".join(
            json.dumps({"id": marker, "ok": True, "mathml": encoded})
            for marker in manifest
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(mathtype.subprocess, "run", fake_run)

    converted, failures = mathtype.convert_ole_objects_to_mathml(
        tmp_path / "large.docx",
        objects,
    )

    assert captured["command"] == ["ruby", str(mathtype.CONVERTER_SCRIPT), "--stdin-json"]
    manifest = json.loads(captured["input"])
    assert len(manifest) == 400
    assert set(manifest) == {item.marker for item in objects}
    assert len(converted) == 400
    assert failures == {}


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
