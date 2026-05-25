import pytest
from homeassistant import EntityIndex, Match, Ambiguous, NotFound

STATES = [
    {"entity_id": "light.living_room", "attributes": {"friendly_name": "Living Room"}},
    {"entity_id": "light.bedroom", "attributes": {"friendly_name": "Bedroom Light"}},
    {"entity_id": "light.kitchen_lamp", "attributes": {"friendly_name": "Kitchen Lamp"}},
    {"entity_id": "cover.blinds_main", "attributes": {"friendly_name": "Main Blinds"}},
    {"entity_id": "scene.party_mode", "attributes": {"friendly_name": "Party Mode"}},
]


@pytest.fixture
def index():
    idx = EntityIndex()
    idx.build(STATES)
    return idx


def test_exact_friendly_name(index):
    assert index.resolve("light", "Living Room") == Match("light.living_room")


def test_exact_short_id(index):
    assert index.resolve("light", "bedroom") == Match("light.bedroom")


def test_case_insensitive(index):
    assert index.resolve("light", "LIVING ROOM") == Match("light.living_room")


def test_prefix_match(index):
    assert index.resolve("light", "kitchen") == Match("light.kitchen_lamp")


def test_substring_match(index):
    # "iving" is a substring (not prefix) that uniquely matches light.living_room
    assert index.resolve("light", "iving") == Match("light.living_room")


def test_ambiguous_returns_candidates(index):
    # "room" is a substring of "living room" (friendly) and "bedroom" (short id)
    result = index.resolve("light", "room")
    assert isinstance(result, Ambiguous)
    assert len(result.candidates) >= 2
    assert all("light." in c for c in result.candidates)


def test_not_found(index):
    assert index.resolve("light", "xyznotexist") == NotFound()


def test_unknown_domain_not_found(index):
    assert index.resolve("switch", "lamp") == NotFound()


def test_other_domain_resolves(index):
    assert index.resolve("cover", "blinds") == Match("cover.blinds_main")


def test_list_domain_returns_entity_ids(index):
    ids = index.list_domain("light")
    assert len(ids) == 3
    assert "light.living_room" in ids


def test_list_domain_respects_limit(index):
    ids = index.list_domain("light", limit=2)
    assert len(ids) == 2


def test_list_domain_empty(index):
    assert index.list_domain("switch") == []


def test_build_ignores_malformed_entity_id():
    idx = EntityIndex()
    idx.build([{"entity_id": "nodomainhere", "attributes": {}}])
    assert idx.list_domain("nodomainhere") == []
