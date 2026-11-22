from pipeline.cleaner import clean_lines


def test_exact_and_near_duplicates_merge():
    out = clean_lines(["let players trade items", "let players trade itens", "let players trade items"], 85)
    assert len(out) == 1


def test_progressive_subtitle_keeps_longest():
    out = clean_lines(["add a daily", "add a daily login", "add a daily login streak"], 85)
    assert out == ["add a daily login streak"]


def test_short_and_letterless_dropped():
    assert clean_lines(["ok", "123 456", "|||", "a b", "free pet"], 85) == ["free pet"]


def test_distinct_lines_kept_in_order():
    assert clean_lines(["add a pet", "trade in lobby"], 85) == ["add a pet", "trade in lobby"]


def test_whitespace_normalized():
    assert clean_lines(["  add   a   pet "], 85) == ["add a pet"]


def test_repeat_of_earlier_line_dropped_later():
    out = clean_lines(["add a pet", "trade in lobby", "add a pet"], 85)
    assert out == ["add a pet", "trade in lobby"]


def test_similar_short_lines_with_different_endings_kept():
    out = clean_lines(["the best part", "the best map"], 85)
    assert out == ["the best part", "the best map"]


def test_ocr_junk_lines_dropped():
    junk = ["n qe", "bl i >", "| wey", "`(Aan", "~ wee", ": ace", "J f A my"]
    assert clean_lines(junk + ["add a pet shop"], 85) == ["add a pet shop"]


def test_mostly_symbols_dropped():
    assert clean_lines(["== 9n what ~~ ||| ;;", "add a pet"], 85) == ["add a pet"]


def test_standalone_pipe_read_as_i():
    assert clean_lines(["| was creating restaurant dishes", "so | posted it"], 85) == [
        "I was creating restaurant dishes",
        "so I posted it",
    ]


def test_progressive_with_persistent_line_in_between():
    frames = [
        "add a daily", "player health bar",
        "add a daily login", "player health bar",
        "add a daily login streak", "player health bar",
    ]
    assert clean_lines(frames, 85) == ["add a daily login streak", "player health bar"]


def test_progressive_with_ocr_noise_keeps_longest():
    out = clean_lines(["add a dai1y", "add a daily login streak"], 85)
    assert out == ["add a daily login streak"]
