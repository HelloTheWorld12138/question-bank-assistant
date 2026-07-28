import os
import platform
import hashlib
from pathlib import Path


APP_NAME = "题搭子"
APP_VERSION = "1.0.0"
SCHEMA_VERSION = 1

ROOT = Path(__file__).resolve().parent.parent
VAULT = Path(os.getenv("QUESTION_BANK_DATA_DIR", ROOT / "vault")).expanduser().resolve()
QUESTIONS_DIR = VAULT / "题目"
ASSETS_DIR = VAULT / "assets"
DRAFT_ASSETS_DIR = ASSETS_DIR / "_drafts"
INDEX_FILE = VAULT / "index.json"
INDEX_LOCK_FILE = VAULT / ".index.lock"
TRASH_DIR = VAULT / ".trash"
BACKUPS_DIR = VAULT / "backups"
USER_TEMPLATES_DIR = VAULT / "templates"
SETTINGS_FILE = VAULT / "settings.json"
AI_DRAFTS_DIR = VAULT / "ai_drafts"
IMPORT_TASKS_DIR = VAULT / "import_tasks"
EXPORT_DIR = Path(os.getenv("QUESTION_BANK_EXPORT_DIR", ROOT / "exports")).expanduser().resolve()
STATIC_DIR = ROOT / "static"
KNOWLEDGE_FILE = ROOT / "data" / "knowledge.yaml"
LOG_DIR = Path(os.getenv("QUESTION_BANK_LOG_DIR", ROOT / "logs")).expanduser().resolve()
LOCAL_PANDOC = ROOT / "tools" / "pandoc" / "pandoc.exe"
BUNDLED_TEMPLATES_DIR = ROOT / "templates"
OFFICECLI_VERSION = "1.0.142"
OFFICECLI_DIR = ROOT / "tools" / "officecli"


def calculate_source_revision() -> str:
    """Identify the app/static source loaded by the current server process."""
    digest = hashlib.sha256()
    for directory in (ROOT / "app", STATIC_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            if path.suffix.lower() not in {".py", ".html", ".css", ".js", ".mjs"}:
                continue
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


SOURCE_REVISION = calculate_source_revision()


def bundled_officecli_name() -> str:
    machine = platform.machine().lower()
    if os.name == "nt":
        return "officecli-win-arm64.exe" if machine in {"arm64", "aarch64"} else "officecli-win-x64.exe"
    if platform.system() == "Darwin":
        return "officecli-mac-arm64" if machine in {"arm64", "aarch64"} else "officecli-mac-x64"
    return "officecli-linux-arm64" if machine in {"arm64", "aarch64"} else "officecli-linux-x64"


LOCAL_OFFICECLI = OFFICECLI_DIR / bundled_officecli_name()

EXAM_TEMPLATES = {
    "a4_single": {"name": "A4 单栏练习", "filename": "a4_single.docx"},
    "a4_double": {"name": "A4 双栏练习", "filename": "a4_double.docx"},
    "formal_exam": {"name": "正式考试卷", "filename": "formal_exam.docx"},
}


def exam_template_path(template_key: str) -> Path:
    spec = EXAM_TEMPLATES.get(template_key)
    if not spec:
        raise ValueError("未知试卷模板")
    user_template = USER_TEMPLATES_DIR / spec["filename"]
    if user_template.is_file():
        return user_template
    return BUNDLED_TEMPLATES_DIR / spec["filename"]

BLOCKS = {
    "LX": "力学",
    "DX": "电磁学",
    "RX": "热学",
    "GX": "光学",
    "XD": "近代物理",
    "SY": "物理实验",
    "ZH": "物理学史、方法、单位制、常识",
    # CD 仅用于兼容旧题号；新题统一归入 DX（电磁学）。
    "CD": "电磁学",
}

BLOCK_OPTIONS = {
    code: BLOCKS[code]
    for code in ("LX", "DX", "RX", "GX", "XD", "SY", "ZH")
}

BLOCK_NAME_ALIASES = {
    "电学": "电磁学",
    "磁场与电磁感应": "电磁学",
    "实验": "物理实验",
    "综合": "物理学史、方法、单位制、常识",
}


def canonical_block_name(value: str) -> str:
    name = str(value or "").strip()
    return BLOCK_NAME_ALIASES.get(name, name)

TYPES = {
    "JD": "经典题",
    "CX": "创新题",
    "JS": "计算量大",
    "YC": "易错题",
    "YZ": "压轴题",
    "JC": "基础题",
    "MX": "模型题",
}

QUESTION_TYPES = ("选择题", "填空题", "实验题", "计算题", "其他")

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
    ".wmf",
    ".emf",
}
IMPORT_EXTENSIONS = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
