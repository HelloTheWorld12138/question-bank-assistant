import logging
from logging.handlers import RotatingFileHandler

from app import config


def configure_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    if any(getattr(handler, "name", "") == "question-bank-file" for handler in root_logger.handlers):
        return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        config.LOG_DIR / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.name = "question-bank-file"
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

