# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import io
from textwrap import dedent

import pytest
from ruamel.yaml import YAML

from odoo_tools.utils.yaml import (
    append_seq_item_with_comments,
    remove_seq_item_with_comments,
)


class TestRemoveSeqItemWithComments:
    @staticmethod
    def _roundtrip(src, value):
        """Load ``src``, remove ``value`` from its top-level ``items`` sequence
        and return the re-dumped document."""
        yaml = YAML()
        data = yaml.load(src)
        remove_seq_item_with_comments(data["items"], value)
        buf = io.StringIO()
        yaml.dump(data, buf)
        return buf.getvalue()

    def test_remove_middle_item_keeps_following_comment(self):
        """Removing an item drops its own (preceding) comment block, not the
        next item's."""
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a
            # comment for c
            - c
            """
        )
        assert result == expected

    def test_remove_last_item_drops_its_comment(self):
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "c")
        expected = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            """
        )
        assert result == expected

    def test_remove_item_without_its_own_comment(self):
        """An item with no preceding comment is removed cleanly, leaving the
        other comments attached to their own items."""
        src = dedent(
            """\
            items:
            - a
            - b
            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a
            # comment for c
            - c
            """
        )
        assert result == expected

    def test_remove_only_commented_item(self):
        """Removing the single commented item also removes its comment block."""
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a
            - c
            """
        )
        assert result == expected

    def test_remove_preserves_multiline_comment_blocks(self):
        """The whole multi-line block above the removed item is dropped, and the
        multi-line block above the survivor is kept verbatim."""
        src = dedent(
            """\
            items:
            - a
            # b line 1
            # b line 2
            - b
            # c line 1
            # c line 2
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a
            # c line 1
            # c line 2
            - c
            """
        )
        assert result == expected

    def test_remove_with_blank_lines_between_comments(self):
        """Blank lines belong to the comment block and travel with it: the
        removed item's leading blank+comment go, the survivor's are kept."""
        src = dedent(
            """\
            items:
            - a

            # comment for b
            - b

            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a

            # comment for c
            - c
            """
        )
        assert result == expected

    def test_remove_keeps_trailing_comment_block(self):
        """A comment block trailing the whole list is not anchored to any item
        and stays put when an earlier item is removed."""
        src = dedent(
            """\
            items:
            - a
            - b
            # trailing block
            """
        )
        result = self._roundtrip(src, "a")
        expected = dedent(
            """\
            items:
            - b
            # trailing block
            """
        )
        assert result == expected

    def test_remove_only_item_with_comment_below(self):
        """Removing the sole item empties the list; a comment that trailed it is
        kept (it survives as the emptied list's leading comment) rather than
        being silently dropped."""
        src = dedent(
            """\
            items:
            - a
            # comment below a
            """
        )
        result = self._roundtrip(src, "a")
        assert result == "items:\n# comment below a\n[]\n"

    def test_remove_absent_value_raises_value_error(self):
        yaml = YAML()
        data = yaml.load("items:\n- a\n- b\n")
        with pytest.raises(ValueError):
            remove_seq_item_with_comments(data["items"], "missing")

    def test_remove_first_item_promotes_next_comment_to_leading(self):
        """Removing the first item drops its own comment and the next item's
        block comment becomes the sequence's leading comment."""
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "a")
        expected = dedent(
            """\
            items:
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        assert result == expected

    def test_remove_first_item_drops_its_own_leading_comment(self):
        """A comment above the first item describes it and is removed with it;
        the next item's comment is promoted to leading."""
        src = dedent(
            """\
            items:
            # leading for a
            - a
            # comment for b
            - b
            """
        )
        result = self._roundtrip(src, "a")
        expected = dedent(
            """\
            items:
            # comment for b
            - b
            """
        )
        assert result == expected

    def test_remove_first_item_clears_leading_when_nothing_follows(self):
        """Removing the only-commented first item leaves the survivor with no
        leading comment."""
        src = dedent(
            """\
            items:
            # leading for a
            - a
            - b
            """
        )
        result = self._roundtrip(src, "a")
        expected = dedent(
            """\
            items:
            - b
            """
        )
        assert result == expected

    def test_remove_non_first_item_keeps_leading_comment(self):
        """A leading comment that describes the first item is untouched when a
        later item is removed."""
        src = dedent(
            """\
            items:
            # leading for a
            - a
            # comment for b
            - b
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            # leading for a
            - a
            """
        )
        assert result == expected

    def test_inline_eol_comments_stay_with_their_item(self):
        """Inline (end-of-line) comments belong to their own item; removing one
        item keeps the others' inline comments, indentation included."""
        src = dedent(
            """\
            items:
            - a  # inline a
            - b  # inline b
            - c  # inline c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a  # inline a
            - c  # inline c
            """
        )
        assert result == expected

    def test_inline_and_block_comments_combined(self):
        """An item may carry both an inline comment and a block comment above
        the next item; each is handled independently on removal."""
        src = dedent(
            """\
            items:
            - a  # inline a
            # block for b
            - b
            - c
            """
        )
        result = self._roundtrip(src, "b")
        expected = dedent(
            """\
            items:
            - a  # inline a
            - c
            """
        )
        assert result == expected


class TestAppendSeqItemWithComments:
    @staticmethod
    def _roundtrip(src, value):
        """Load ``src``, append ``value`` to its top-level ``items`` sequence
        and return the re-dumped document."""
        yaml = YAML()
        data = yaml.load(src)
        append_seq_item_with_comments(data["items"], value)
        buf = io.StringIO()
        yaml.dump(data, buf)
        return buf.getvalue()

    def test_append_after_item_with_block_comment(self):
        """The new item lands at the end, after the previous item's comment
        block -- not in between the block and the item it describes."""
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            """
        )
        result = self._roundtrip(src, "c")
        expected = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            - c
            """
        )
        assert result == expected

    def test_append_to_plain_list(self):
        src = dedent(
            """\
            items:
            - a
            - b
            """
        )
        result = self._roundtrip(src, "c")
        expected = dedent(
            """\
            items:
            - a
            - b
            - c
            """
        )
        assert result == expected

    def test_append_keeps_all_block_comments(self):
        """Every existing comment block stays anchored to its own item."""
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._roundtrip(src, "d")
        expected = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            - d
            """
        )
        assert result == expected

    def test_append_keeps_inline_comments(self):
        """Inline (end-of-line) comments stay with their own item."""
        src = dedent(
            """\
            items:
            - a  # inline a
            - b  # inline b
            """
        )
        result = self._roundtrip(src, "c")
        expected = dedent(
            """\
            items:
            - a  # inline a
            - b  # inline b
            - c
            """
        )
        assert result == expected

    def test_append_preserves_multiline_comment_blocks(self):
        src = dedent(
            """\
            items:
            - a
            # b line 1
            # b line 2
            - b
            """
        )
        result = self._roundtrip(src, "c")
        expected = dedent(
            """\
            items:
            - a
            # b line 1
            # b line 2
            - b
            - c
            """
        )
        assert result == expected


class TestRuamelUpstreamCanary:
    """Canaries for ruamel.yaml ticket #377 (mis-handling of block comments
    when removing a sequence item).

    These exercise *raw* ruamel (``CommentedSeq.remove``), NOT our
    ``remove_seq_item_with_comments`` helper, and assert the result we'd get if
    ruamel handled the comments itself. They are expected to FAIL today, so they
    are marked ``xfail(strict=True)``: the day upstream fixes the bug they flip
    to XPASS, which a strict xfail turns into a suite failure -- our signal to
    drop the custom helper and go back to plain ``seq.remove(...)``.

    (Inline end-of-line comments are intentionally not covered: raw ruamel
    already handles those correctly; only block comments are affected.)

    https://sourceforge.net/p/ruamel-yaml/tickets/377/
    """

    @staticmethod
    def _raw_remove(src, value):
        yaml = YAML()
        data = yaml.load(src)
        data["items"].remove(value)  # raw ruamel, no custom comment handling
        buf = io.StringIO()
        yaml.dump(data, buf)
        return buf.getvalue()

    @pytest.mark.xfail(
        strict=True,
        reason="ruamel #377: raw remove keeps the removed item's block comment "
        "and drops the next item's. When this passes, drop our helper.",
    )
    def test_raw_remove_middle_item_keeps_following_comment(self):
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._raw_remove(src, "b")
        expected = dedent(
            """\
            items:
            - a
            # comment for c
            - c
            """
        )
        assert result == expected

    @pytest.mark.xfail(
        strict=True,
        reason="ruamel #377: raw remove of the first item drops the next item's "
        "block comment instead of promoting it. When this passes, drop our helper.",
    )
    def test_raw_remove_first_item_promotes_next_comment(self):
        src = dedent(
            """\
            items:
            - a
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        result = self._raw_remove(src, "a")
        expected = dedent(
            """\
            items:
            # comment for b
            - b
            # comment for c
            - c
            """
        )
        assert result == expected
