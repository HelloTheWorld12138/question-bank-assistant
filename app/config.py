import os
from pathlib import Path


APP_NAME = "高中物理题库助手"
APP_VERSION = "0.2.0-dev"
SCHEMA_VERSION = 1

ROOT = Path(__file__).resolve().parent.parent
VAULT = Path(os.getenv("QUESTION_BANK_DATA_DIR", ROOT / "vault")).expanduser().resolve()
QUESTIONS_DIR = VAULT / "题目"
ASSETS_DIR = VAULT / "assets"
DRAFT_ASSETS_DIR = ASSETS_DIR / "_drafts"
INDEX_FILE = VAULT / "index.json"
EXPORT_DIR = Path(os.getenv("QUESTION_BANK_EXPORT_DIR", ROOT / "exports")).expanduser().resolve()
STATIC_DIR = ROOT / "static"
LOG_DIR = Path(os.getenv("QUESTION_BANK_LOG_DIR", ROOT / "logs")).expanduser().resolve()
LOCAL_PANDOC = ROOT / "tools" / "pandoc" / "pandoc.exe"

BLOCKS = {
    "LX": "力学",
    "DX": "电学",
    "CD": "磁场与电磁感应",
    "GX": "光学",
    "RX": "热学",
    "XD": "近代物理",
    "SY": "实验",
    "ZH": "综合",
}

TYPES = {
    "JD": "经典题",
    "CX": "创新题",
    "JS": "计算量大",
    "YC": "易错题",
    "YZ": "压轴题",
    "JC": "基础题",
    "MX": "模型题",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".wmf", ".emf"}

