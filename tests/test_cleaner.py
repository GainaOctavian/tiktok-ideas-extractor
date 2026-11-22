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


def test_edge_junk_stripped():
    out = clean_lines(
        ["TELL YOUR I", "YOUR CLAUDE,*", "�AGENT TO FIND", "LOWER DETAIL ON 4", "DISTANT OBJECTS, =~", "{TWO FRIENDS JOINING"],
        85,
    )
    assert out == ["TELL YOUR", "YOUR CLAUDE,", "AGENT TO FIND", "LOWER DETAIL ON", "DISTANT OBJECTS,", "TWO FRIENDS JOINING"]


def test_leading_i_and_a_kept():
    assert clean_lines(["I posted it", "A free pet"], 85) == ["I posted it", "A free pet"]


def test_zero_inside_word_read_as_o():
    assert clean_lines(["MORE FRIENDS T0", "ROBL0X GAME", "TOP 10 GAMES"], 85) == [
        "MORE FRIENDS TO", "ROBLOX GAME", "TOP 10 GAMES",
    ]


def test_numbers_next_to_letters_unchanged():
    out = clean_lines(["make $10k a month", "earn 100x more", "games from the 2020s", "the 3D models"], 85)
    assert out == ["make $10k a month", "earn 100x more", "games from the 2020s", "the 3D models"]


def test_money_and_percent_at_line_end_kept():
    assert clean_lines(["it only costs $5", "players grow by 5%"], 85) == ["it only costs $5", "players grow by 5%"]


def test_line_contained_in_recent_line_dropped():
    out = clean_lines(["EVERY 3D MODEL SLOWING", "3D MODEL", "REMOVE UNNECESSARY SHADOWS,", "UNNECESSARY"], 85)
    assert out == ["EVERY 3D MODEL SLOWING", "REMOVE UNNECESSARY SHADOWS,"]


def test_recent_line_contained_in_new_line_replaced():
    out = clean_lines(["FRIENDS JOINING", "YOUR GAME", "TWO FRIENDS JOINING"], 85)
    assert out == ["TWO FRIENDS JOINING", "YOUR GAME"]


def test_progressive_with_ocr_noise_keeps_longest():
    out = clean_lines(["add a dai1y", "add a daily login streak"], 85)
    assert out == ["add a daily login streak"]
