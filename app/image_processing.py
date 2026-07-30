from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.errors import AppError


def preprocess_image(
    source: Path,
    target: Path,
    *,
    rotation: float = 0,
    crop: dict[str, Any] | None = None,
    perspective: list[list[float]] | None = None,
    enhance: bool = False,
) -> dict[str, int]:
    try:
        image = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    except (OSError, ValueError) as exc:
        raise AppError("图片无法读取或格式不受支持。") from exc
    if rotation:
        image = image.rotate(-float(rotation), expand=True, fillcolor="white")
    if crop:
        values = [
            float(crop.get(key, default))
            for key, default in (
                ("left", 0),
                ("top", 0),
                ("right", 1),
                ("bottom", 1),
            )
        ]
        left, top, right, bottom = values
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise AppError("裁剪范围应位于图片内部。")
        image = image.crop(
            (
                round(left * image.width),
                round(top * image.height),
                round(right * image.width),
                round(bottom * image.height),
            )
        )
    if perspective:
        if len(perspective) != 4 or any(len(point) != 2 for point in perspective):
            raise AppError("透视校正需要四个角点。")
        points = [(float(x), float(y)) for x, y in perspective]
        if all(0 <= value <= 1 for point in points for value in point):
            points = [(x * image.width, y * image.height) for x, y in points]
        top_left, top_right, bottom_right, bottom_left = points
        width = max(
            1,
            round(
                max(
                    math.dist(top_left, top_right),
                    math.dist(bottom_left, bottom_right),
                )
            ),
        )
        height = max(
            1,
            round(
                max(
                    math.dist(top_left, bottom_left),
                    math.dist(top_right, bottom_right),
                )
            ),
        )
        image = image.transform(
            (width, height),
            Image.Transform.QUAD,
            data=(
                top_left[0],
                top_left[1],
                bottom_left[0],
                bottom_left[1],
                bottom_right[0],
                bottom_right[1],
                top_right[0],
                top_right[1],
            ),
            resample=Image.Resampling.BICUBIC,
        )
    if enhance:
        grayscale = ImageOps.grayscale(image)
        grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
        grayscale = grayscale.filter(ImageFilter.MedianFilter(size=3))
        grayscale = ImageEnhance.Contrast(grayscale).enhance(1.25)
        image = grayscale.convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    output_formats = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    output_format = output_formats.get(target.suffix.lower())
    if output_format is None:
        raise AppError("该图片格式不能执行旋转、裁剪或增强，请先转换为 PNG。")
    temporary = target.with_name(f".{target.stem}.{uuid.uuid4().hex}{target.suffix.lower()}")
    save_options = {"quality": 95} if output_format in {"JPEG", "WEBP"} else {}
    if output_format == "PNG":
        save_options["optimize"] = True
    image.save(temporary, format=output_format, **save_options)
    temporary.replace(target)
    return {"width": image.width, "height": image.height}
