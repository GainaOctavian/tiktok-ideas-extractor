import cv2
import numpy as np
import pytest

from pipeline.frames import drop_near_duplicates, extract_frames


def frame(tmp_path, name, img):
    path = tmp_path / name
    cv2.imwrite(str(path), img)
    return path


def blank(value=0, h=200, w=400):
    return np.full((h, w, 3), value, dtype=np.uint8)


def with_text(text, h=200, w=400):
    img = blank()
    cv2.putText(img, text, (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    return img


def test_identical_frames_collapse(tmp_path):
    a = with_text("ADD A PET")
    paths = [frame(tmp_path, f"{i}.png", a) for i in range(3)] + [frame(tmp_path, "3.png", with_text("TRADE"))]
    assert drop_near_duplicates(paths, 0.02) == [paths[0], paths[3]]


def test_small_noise_below_threshold_dropped(tmp_path):
    # compression-like noise spread over the whole frame
    a = with_text("ADD A PET")
    noise = np.random.default_rng(0).integers(-3, 4, a.shape)
    b = np.clip(a.astype(int) + noise, 0, 255).astype(np.uint8)
    paths = [frame(tmp_path, "0.png", a), frame(tmp_path, "1.png", b)]
    assert drop_near_duplicates(paths, 0.02) == [paths[0]]


def test_one_word_change_in_large_static_frame_kept(tmp_path):
    def big(word):
        img = np.zeros((640, 648, 3), dtype=np.uint8)
        cv2.putText(img, word, (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
        return img

    paths = [frame(tmp_path, "0.png", big("ONE")), frame(tmp_path, "1.png", big("TWO"))]
    assert drop_near_duplicates(paths, 0.02) == paths


def test_compares_against_last_kept_frame(tmp_path):
    # slow drift: each step tiny, but the total change since the last kept frame grows past the threshold
    imgs = [blank(v) for v in (0, 3, 6, 9, 12)]
    paths = [frame(tmp_path, f"{i}.png", img) for i, img in enumerate(imgs)]
    kept = drop_near_duplicates(paths, 0.02)
    assert kept == [paths[0], paths[2], paths[4]]


def test_empty_list():
    assert drop_near_duplicates([], 0.02) == []


@pytest.mark.needs_ffmpeg
def test_extract_frames_crops_and_samples(tmp_path, cfg):
    video = tmp_path / "v.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (720, 1280))
    for second, word in enumerate(["ONE", "TWO", "THREE"]):
        img = np.zeros((1280, 720, 3), dtype=np.uint8)
        cv2.putText(img, word, (100, 700), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 8)
        for _ in range(10):
            writer.write(img)
    writer.release()

    out = tmp_path / "frames"
    out.mkdir()
    frames = extract_frames(video, out, cfg)
    assert len(frames) == 3
    for path in frames:
        h, w = cv2.imread(str(path)).shape[:2]
        assert abs(h - 1280 * 0.5) <= 2
        assert abs(w - 720 * 0.9) <= 2


@pytest.mark.needs_ffmpeg
def test_extract_frames_bad_video_raises(tmp_path, cfg):
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"not a video")
    with pytest.raises(RuntimeError):
        extract_frames(video, tmp_path, cfg)
