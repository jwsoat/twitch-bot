from auth import is_allowed


def test_exact_match():
    assert is_allowed("dylanwech", {"dylanwech"})


def test_case_insensitive_input():
    assert is_allowed("DylanWech", {"dylanwech"})


def test_case_insensitive_stored_upper():
    assert is_allowed("directorynetworks", {"DIRECTORYNETWORKS"})


def test_multiple_users():
    allowed = {"directorynetworks", "jwsoatmedia", "dylanwech", "directorynetwork"}
    assert is_allowed("JwsoatMedia", allowed)


def test_blocked_unknown():
    assert not is_allowed("randomviewer", {"dylanwech"})


def test_empty_allowlist_blocks_all():
    assert not is_allowed("dylanwech", set())
