from __future__ import annotations

import stat
import zipfile

import pytest

from backend.app.core.errors import AppError
from backend.app.core.security import ZipLimits, extract_zip_safe, safe_resolve, sanitize_filename, sanitize_public_text, validate_image


def test_filename_and_containment_are_windows_safe(tmp_path, make_image):
    assert sanitize_filename("../病患:影像?.JPG") == "病患_影像_.jpg"
    assert sanitize_filename("CON.jpg").startswith("_")
    with pytest.raises(AppError) as caught:
        safe_resolve(tmp_path, "..", "escape.jpg")
    assert caught.value.code == "UNSAFE_PATH"
    assert "C:\\" not in sanitize_public_text(r"failed at C:\\private\\patient\\image.jpg")

    image = tmp_path / "影像.jpg"
    image.write_bytes(make_image())
    info = validate_image(image, 1_000_000)
    assert (info.format, info.width, info.height) == ("JPEG", 32, 24)


@pytest.mark.parametrize("member", ["../evil.jpg", "/evil.jpg", "C:/evil.jpg", "safe/../../evil.jpg"])
def test_zip_slip_is_rejected(tmp_path, member, make_image):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(member, make_image())
    with pytest.raises(AppError) as caught:
        extract_zip_safe(archive, tmp_path / "out", ZipLimits(), {".jpg"})
    assert caught.value.code == "UNSAFE_ARCHIVE"


def test_zip_symlink_and_bomb_ratio_are_rejected(tmp_path):
    symlink_zip = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link.jpg")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink_zip, "w") as output:
        output.writestr(info, "target")
    with pytest.raises(AppError) as caught:
        extract_zip_safe(symlink_zip, tmp_path / "links", ZipLimits(), {".jpg"})
    assert caught.value.code == "UNSAFE_ARCHIVE"

    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("large.jpg", b"0" * 100_000)
    with pytest.raises(AppError) as caught:
        extract_zip_safe(bomb, tmp_path / "bomb", ZipLimits(max_ratio=2), {".jpg"})
    assert caught.value.code == "ARCHIVE_RATIO_EXCEEDED"
