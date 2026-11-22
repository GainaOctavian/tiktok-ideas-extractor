import dataclasses

import pytest

from pipeline.lister import ListingError, list_clips, normalize_account
from tests.fakes import FakeYDL


@pytest.mark.parametrize(
    "raw",
    ["@Cont", "cont", " cont ", "https://www.tiktok.com/@cont", "https://www.tiktok.com/@cont/video/1?lang=en"],
)
def test_normalize_account_forms(raw):
    assert normalize_account(raw) == "cont"


@pytest.mark.parametrize("raw", ["bad name!", "", "@", "https://example.com/@cont"])
def test_normalize_account_rejects(raw):
    with pytest.raises(ValueError):
        normalize_account(raw)


def test_list_clips_maps_entries(cfg):
    info = {
        "entries": [
            {"id": 7301234567890, "url": "https://www.tiktok.com/@cont/video/7301234567890", "title": "a", "timestamp": 1795651200},
            {"id": "7301234567999", "title": "b", "upload_date": "20261120"},
            {"id": "7301234567000"},
        ]
    }
    clips = list_clips("cont", cfg, ydl_factory=FakeYDL.configure(info=info))
    assert [c.id for c in clips] == ["7301234567890", "7301234567999", "7301234567000"]
    assert clips[0].published == "2026-11-26"
    assert clips[1].published == "2026-11-20"
    assert clips[1].url == "https://www.tiktok.com/@cont/video/7301234567999"
    assert clips[2].published is None and clips[2].title is None


def test_list_clips_requests_profile_without_download(cfg):
    fake = FakeYDL.configure(info={"entries": [{"id": "1"}]})
    list_clips("cont", cfg, ydl_factory=fake)
    assert fake.last_opts["extract_flat"] == "in_playlist"
    assert fake.last_opts["skip_download"] is True
    assert "cookiesfrombrowser" not in fake.last_opts


@pytest.mark.parametrize("fake", [FakeYDL.configure(error=Exception("HTTP 403")), FakeYDL.configure(info={"entries": []})])
def test_list_clips_errors_become_listing_error(cfg, fake):
    with pytest.raises(ListingError, match="pip install -U yt-dlp"):
        list_clips("cont", cfg, ydl_factory=fake)


def test_impersonation_target_passed(cfg):
    fake = FakeYDL.configure(info={"entries": [{"id": "1"}]})
    list_clips("cont", cfg, ydl_factory=fake)
    assert str(fake.last_opts["impersonate"]) == "chrome"


def test_impersonation_can_be_disabled(cfg):
    fake = FakeYDL.configure(info={"entries": [{"id": "1"}]})
    list_clips("cont", dataclasses.replace(cfg, impersonate=None), ydl_factory=fake)
    assert "impersonate" not in fake.last_opts


def test_cookies_option_passed(cfg):
    fake = FakeYDL.configure(info={"entries": [{"id": "1"}]})
    list_clips("cont", dataclasses.replace(cfg, cookies_from_browser="chrome"), ydl_factory=fake)
    assert fake.last_opts["cookiesfrombrowser"] == ("chrome",)
