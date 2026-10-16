from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import unicodedata
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .errors import AppError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png"}
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class ImageInfo:
    format: str
    mime_type: str
    width: int
    height: int


@dataclass(frozen=True)
class ZipLimits:
    max_entries: int = 10_000
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_entry_bytes: int = 512 * 1024 * 1024
    max_ratio: float = 100.0


def sanitize_filename(filename: str, fallback: str = "file") -> str:
    name = unicodedata.normalize("NFKC", Path(filename.replace("\\", "/")).name)
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", name).strip(" .")
    if not name:
        name = fallback
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    stem = stem[:160].rstrip(" .") or fallback
    suffix = re.sub(r"[^a-zA-Z0-9.]", "", suffix)[:16]
    return f"{stem}{suffix}"


def sanitize_public_text(value: str) -> str:
    """Remove local absolute paths before a value is returned to a browser."""
    value = re.sub(r"(?i)\b[A-Z]:[\\/][^\r\n\"']+", "<path>", value)
    value = re.sub(r"(?<![A-Za-z0-9:])/(?:[^\s/]+/)+[^\s\"']*", "<path>", value)
    return value


def sanitize_public_json(value):
    if isinstance(value, str):
        return sanitize_public_text(value)
    if isinstance(value, dict):
        return {str(key): sanitize_public_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_public_json(item) for item in value]
    return value


def safe_resolve(root: Path, *parts: str | os.PathLike[str]) -> Path:
    root = Path(root).resolve()
    candidate = root.joinpath(*(str(part) for part in parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(400, "UNSAFE_PATH", "檔案路徑超出允許範圍。") from exc
    return candidate


def relative_path(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError as exc:
        raise AppError(500, "INVALID_STORED_PATH", "儲存路徑設定錯誤。") from exc


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def save_upload_file(upload, destination: Path, max_bytes: int) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
    size = 0
    digest = hashlib.sha256()
    try:
        with temporary.open("xb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(413, "UPLOAD_TOO_LARGE", "上傳檔案超過大小限制。")
                digest.update(chunk)
                handle.write(chunk)
        os.replace(temporary, destination)
        return size, digest.hexdigest()
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        await upload.close()


def validate_image(path: Path, max_pixels: int) -> ImageInfo:
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                fmt = (image.format or "").upper()
                width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise AppError(422, "INVALID_IMAGE", "檔案不是有效或安全的影像。") from exc
    if fmt not in {"JPEG", "PNG"}:
        raise AppError(422, "UNSUPPORTED_IMAGE", "僅支援 JPEG 與 PNG 影像。")
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise AppError(422, "IMAGE_DIMENSIONS_INVALID", "影像尺寸不符合限制。")
    return ImageInfo(fmt, "image/jpeg" if fmt == "JPEG" else "image/png", width, height)


def _safe_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    raw = info.filename.replace("\\", "/")
    if "\x00" in raw or raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw):
        raise AppError(422, "UNSAFE_ARCHIVE", "ZIP 內含不安全路徑。")
    path = PurePosixPath(raw)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise AppError(422, "UNSAFE_ARCHIVE", "ZIP 內含不安全路徑。")
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise AppError(422, "UNSAFE_ARCHIVE", "ZIP 不允許符號連結。")
    file_type = stat.S_IFMT(mode)
    if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise AppError(422, "UNSAFE_ARCHIVE", "ZIP 內含不支援的特殊檔案。")
    if info.flag_bits & 0x1:
        raise AppError(422, "ENCRYPTED_ARCHIVE", "不支援加密 ZIP。")
    return path


def inspect_zip(path: Path, limits: ZipLimits) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise AppError(422, "INVALID_ARCHIVE", "ZIP 檔案無法讀取。") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise AppError(413, "ARCHIVE_TOO_MANY_FILES", "ZIP 檔案數量超過限制。")
        total = 0
        result = []
        for info in infos:
            member = _safe_zip_member(info)
            if info.is_dir():
                continue
            total += info.file_size
            if info.file_size > limits.max_entry_bytes or total > limits.max_total_bytes:
                raise AppError(413, "ARCHIVE_TOO_LARGE", "ZIP 解壓縮後大小超過限制。")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_ratio:
                raise AppError(413, "ARCHIVE_RATIO_EXCEEDED", "ZIP 壓縮比例異常。")
            result.append((info, member))
        return result


def extract_zip_safe(path: Path, destination: Path, limits: ZipLimits, allowed_extensions: Iterable[str] | None = None) -> list[Path]:
    members = inspect_zip(path, limits)
    allowed = {ext.lower() for ext in allowed_extensions} if allowed_extensions else None
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(path) as archive:
        targets: set[Path] = set()
        for info, member in members:
            if allowed is not None and PurePosixPath(member).suffix.lower() not in allowed:
                continue
            safe_parts = [sanitize_filename(part, "item") for part in member.parts]
            target = safe_resolve(destination, *safe_parts)
            if target in targets or target.exists():
                raise AppError(422, "ARCHIVE_PATH_COLLISION", "ZIP 內含重複或衝突的檔名。")
            targets.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
            try:
                with archive.open(info) as source, temporary.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        if written > info.file_size or written > limits.max_entry_bytes:
                            raise AppError(413, "ARCHIVE_TOO_LARGE", "ZIP 項目大小超過限制。")
                        output.write(chunk)
                os.replace(temporary, target)
                extracted.append(target)
            finally:
                temporary.unlink(missing_ok=True)
    return extracted


def remove_tree_contained(path: Path, root: Path) -> None:
    target = safe_resolve(root, relative_path(path, root))
    if target == Path(root).resolve():
        raise AppError(500, "UNSAFE_DELETE", "拒絕刪除根目錄。")
    if target.exists():
        # Containment is checked above using normal resolved paths. Windows
        # needs extended syntax for descendants that exceed MAX_PATH after a
        # managed job is renamed into the (longer) temporary deletion folder.
        # Do not change global OS settings or silently ignore cleanup failures.
        value = str(target)
        if os.name == "nt" and not value.startswith("\\\\?\\"):
            value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
        shutil.rmtree(value)
