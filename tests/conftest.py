import dataclasses
import shutil

import pytest

from pipeline.config import Config


@pytest.fixture
def cfg(tmp_path):
    return dataclasses.replace(Config(), data_dir=tmp_path / "data", work_dir=tmp_path / "work")


def pytest_collection_modifyitems(config, items):
    missing = {
        "needs_ffmpeg": shutil.which("ffmpeg") is None,
        "needs_tesseract": not _tesseract_available(),
    }
    for item in items:
        for marker, absent in missing.items():
            if absent and item.get_closest_marker(marker):
                item.add_marker(pytest.mark.skip(reason=f"{marker}: tool not installed"))


def _tesseract_available():
    try:
        from pipeline.ocr import configure_tesseract
        configure_tesseract(Config())
        return True
    except Exception:
        return False
