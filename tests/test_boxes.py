from pathlib import Path

import pytest

from slidesmith import boxes
from slidesmith.model import Loc
from slidesmith.parser import SourceError

LOC = Loc(Path("x.md"), 1)
SRC = """
grid 4x3   # comment
box a "Stap #1" at 0,0 step=1
box b "B" at 2,1 span=2,1 style=outline
arrow a -> b step=2 label="push"
"""


def test_parse():
    d = boxes.parse(SRC, LOC)
    assert (d.cols, d.rows) == (4, 3)
    assert d.boxes["a"].label == "Stap #1"  # '#' inside quotes is not a comment
    assert d.boxes["b"].span == (2, 1)
    assert d.arrows[0].src == "a" and d.arrows[0].step == 2
    assert boxes.max_step(d) == 2


def test_render_fragments_and_labels():
    svg = boxes.render(boxes.parse(SRC, LOC), {"a": "Step 1"}, "u")
    assert 'data-fragment-index="1"' in svg and 'data-fragment-index="2"' in svg
    assert ">Step 1<" in svg and "Stap #1" not in svg
    assert ">push<" in svg


def test_arrow_to_unknown_box():
    with pytest.raises(SourceError, match="onbekende box"):
        boxes.parse('box a "A" at 0,0\narrow a -> zz', LOC)


def test_error_line_numbers():
    with pytest.raises(SourceError) as e:
        boxes.parse('\nbox a "A" at 0,0\nfoo', LOC)
    assert e.value.loc.line == 4
