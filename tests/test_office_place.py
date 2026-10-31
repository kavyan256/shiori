"""Word comes back at the same place. A stand-in for Word: no real document is touched."""
from types import SimpleNamespace

import office


def test_word_remembers_the_cursor_and_page():
    selection = SimpleNamespace(Start=420, Information=lambda what: 7 if what == office.WORD_PAGE_NUMBER else 0)
    doc = SimpleNamespace(Windows=lambda n: SimpleNamespace(Selection=selection))
    where = office._where("winword.exe", doc)
    assert where == {"position": 420, "page": 7}
    assert office._describe_where(where) == "page 7"


def test_word_that_does_not_answer_gives_no_place():
    assert office._where("winword.exe", SimpleNamespace()) == {}
