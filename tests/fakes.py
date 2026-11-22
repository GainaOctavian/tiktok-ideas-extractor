"""Test doubles for yt_dlp.YoutubeDL."""
from pathlib import Path


class FakeYDL:
    """Factory-compatible stand-in: FakeYDL.configure(...) then pass FakeYDL as ydl_factory."""

    info = None
    error = None
    write_ext = "mp4"
    last_opts = None

    def __init__(self, opts):
        type(self).last_opts = opts
        self.opts = opts

    @classmethod
    def configure(cls, info=None, error=None, write_ext="mp4"):
        return type("ConfiguredFakeYDL", (cls,), {"info": info, "error": error, "write_ext": write_ext})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False, **kwargs):
        if self.error:
            raise self.error
        return self.info

    def process_ie_result(self, info, download=True):
        self.download([info])
        return info

    def download(self, urls):
        if self.error:
            raise self.error
        if self.write_ext:
            out = Path(self.opts["outtmpl"].replace("%(ext)s", self.write_ext))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"video")
        return 0
