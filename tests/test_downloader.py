import dataclasses

import pytest

from pipeline.downloader import DownloadError, PhotoPost, download
from tests.fakes import FakeYDL

URL = "https://www.tiktok.com/@cont/video/1"


def test_download_uses_format_sort_and_returns_file(tmp_path, cfg):
    fake = FakeYDL.configure()
    path = download(URL, tmp_path / "1", cfg, ydl_factory=fake)
    assert path == tmp_path / "1" / "video.mp4"
    assert fake.last_opts["format_sort"] == ["+res:720"]
    assert fake.last_opts["format"] == "b/bv*+ba"


def test_download_min_height_from_config(tmp_path, cfg):
    fake = FakeYDL.configure()
    download(URL, tmp_path / "1", dataclasses.replace(cfg, min_height=1080), ydl_factory=fake)
    assert fake.last_opts["format_sort"] == ["+res:1080"]


def test_yt_dlp_messages_silenced(tmp_path, cfg, capsys):
    fake = FakeYDL.configure()
    download(URL, tmp_path / "1", cfg, ydl_factory=fake)
    logger = fake.last_opts["logger"]
    for level in ("debug", "info", "warning", "error"):
        getattr(logger, level)("ERROR: noisy")
    assert capsys.readouterr() == ("", "")


AUDIO_ONLY = {"id": "1", "formats": [{"format_id": "audio", "vcodec": "none", "acodec": "mp3"}]}
WITH_VIDEO = {
    "id": "1",
    "formats": [
        {"format_id": "audio", "vcodec": "none", "acodec": "mp3"},
        {"format_id": "h264_720p", "vcodec": "h264", "acodec": "aac", "height": 1280},
    ],
}


def test_photo_post_detected_without_downloading(tmp_path, cfg):
    with pytest.raises(PhotoPost):
        download(URL, tmp_path / "1", cfg, ydl_factory=FakeYDL.configure(info=AUDIO_ONLY))
    assert list((tmp_path / "1").glob("*")) == []


def test_video_post_downloaded(tmp_path, cfg):
    path = download(URL, tmp_path / "1", cfg, ydl_factory=FakeYDL.configure(info=WITH_VIDEO))
    assert path.name == "video.mp4"


def test_photo_post_is_not_a_download_error():
    assert not issubclass(PhotoPost, DownloadError)


def test_download_failure(tmp_path, cfg):
    with pytest.raises(DownloadError, match="403"):
        download(URL, tmp_path / "1", cfg, ydl_factory=FakeYDL.configure(error=Exception("HTTP 403")))


def test_download_without_output_file(tmp_path, cfg):
    with pytest.raises(DownloadError):
        download(URL, tmp_path / "1", cfg, ydl_factory=FakeYDL.configure(write_ext=None))


def test_download_ignores_partial_files(tmp_path, cfg):
    dest = tmp_path / "1"
    dest.mkdir()
    (dest / "video.mp4.part").write_bytes(b"x")
    with pytest.raises(DownloadError):
        download(URL, dest, cfg, ydl_factory=FakeYDL.configure(write_ext=None))
