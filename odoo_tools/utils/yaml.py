# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import Path

# TODO: do we really need this to edit such files?
from ruamel.yaml import YAML
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken

yaml = YAML()


def yaml_load(stream):
    return yaml.load(stream)


def yaml_dump(data, fileob):
    yaml.dump(data, fileob)


def _comment_token(value, column=0):
    return CommentToken(value, CommentMark(column), None)


def _set_seq_start_comment(seq, leading):
    """(Re)set the block comment that precedes a sequence's first item."""
    comment = seq.ca.comment
    if comment and comment[1]:
        # When ``seq`` is a value in a mapping, this pre-comment list is the very
        # same object as the parent map's slot, so mutating it in place updates
        # both. An empty-value token clears it without breaking the block style.
        comment[1][:] = [_comment_token(leading or "")]
    elif leading:
        token = _comment_token(leading)
        if comment:
            comment[1] = [token]
        else:
            seq.ca.comment = [None, [token]]


def _normalize_seq_comments(seq):
    """Normalise a ruamel ``CommentedSeq``'s stored comments into a per-item
    model and return ``(eol, above)``.

    ``eol[i]`` is ``(text, column)`` of item ``i``'s end-of-line comment;
    ``above[i]`` is the block printed before item ``i`` (``above[length]``
    trails the whole list). This sidesteps ruamel's storage where
    ``seq.ca.items[i]`` holds the comment printed *after* item ``i`` -- mixing
    item ``i``'s end-of-line comment with the block that precedes item ``i + 1``
    -- and the block above the first item lives on the sequence's start comment.
    """
    length = len(seq)
    eol = [None] * length
    above = [None] * (length + 1)
    for i, entry in seq.ca.items.items():
        token = entry[0] if entry else None
        if token is None:
            continue
        head, _, rest = token.value.partition("\n")
        if head.strip():
            eol[i] = (head + "\n", token.start_mark.column)
        if rest:
            above[i + 1] = rest
    start = seq.ca.comment
    if start and start[1]:
        above[0] = "".join(token.value for token in start[1] if token is not None)
    return eol, above


def _rebuild_seq_comments(seq, eol, above):
    """Rebuild ``seq.ca.items`` and the start comment from the per-item model
    produced by :func:`_normalize_seq_comments`. Inline placement is restored
    from the token column; block indentation rides along as leading whitespace
    inside the token value.
    """
    seq.ca.items.clear()
    _set_seq_start_comment(seq, above[0])
    for i in range(len(seq)):
        inline, block = eol[i], above[i + 1]
        if inline and block:
            token = _comment_token(inline[0] + block, inline[1])
        elif inline:
            token = _comment_token(inline[0], inline[1])
        elif block:
            token = _comment_token("\n" + block)
        else:
            continue
        seq.ca.items[i] = [token, None, None, None]


def remove_seq_item_with_comments(seq, value):
    """Remove ``value`` from a ruamel ``CommentedSeq`` along with the comments
    that belong to it (its end-of-line comment and the block above it), keeping
    every other item's comments anchored to that item.

    ruamel does not model this directly (see :func:`_normalize_seq_comments`): a
    plain ``seq.remove(value)`` drops the *next* item's comment and leaves the
    removed item's block dangling on the survivor (upstream ticket, no stable
    public API yet: https://sourceforge.net/p/ruamel-yaml/tickets/377/).

    We sidestep that by normalising the stored comments into a per-item model,
    dropping the removed item's entries, then rebuilding ``ca.items`` and the
    start comment.
    """
    idx = seq.index(value)  # raises ValueError if absent, like list.remove
    eol, above = _normalize_seq_comments(seq)
    # Drop the item together with its own inline + preceding-block comments.
    # ``above[idx + 1]`` shifts into ``idx``, staying anchored to the survivor.
    del seq[idx]
    eol.pop(idx)
    above.pop(idx)
    _rebuild_seq_comments(seq, eol, above)


def sequence_item_indent(depth=1):
    """Whitespace prefix that lines a comment up with a block-sequence's item
    dashes, for a sequence nested ``depth`` mapping levels under the document
    root (pending-merges files use depth 1).

    Derived from the shared dumper's configuration so it tracks whatever
    indentation the items are rendered with rather than hardcoding a column.
    """
    return " " * (depth * (yaml.map_indent or 2) + (yaml.sequence_dash_offset or 0))


def append_seq_item_with_comments(seq, value, comment=None, comment_indent=""):
    """Append ``value`` to the end of a ruamel ``CommentedSeq`` keeping every
    existing item's comments anchored to that item.

    A plain ``seq.append(value)`` would leave any block comment that trailed the
    list dangling before the new item; normalising and rebuilding keeps that
    block attached to the previously-last item so the new line lands cleanly at
    the end.

    ``comment`` is an optional list of plain text lines (no ``#``) to print as a
    block *above* the appended item; each is rendered as
    ``{comment_indent}# {line}``. ``comment_indent`` should line the comment up
    with the rendered list items (see :func:`sequence_item_indent`).
    """
    eol, above = _normalize_seq_comments(seq)
    length = len(seq)  # index the appended item will occupy
    seq.append(value)
    eol.append(None)  # new last item: no end-of-line comment
    if comment:
        block = "".join(
            f"{comment_indent}# {line.replace(chr(10), ' ')}\n" for line in comment
        )
        # ``above[length]`` is the block printed before the new last item.
        above[length] = (above[length] or "") + block
    above.append(None)  # new trailing slot: empty
    _rebuild_seq_comments(seq, eol, above)


def update_yml_file(path, new_data, main_key=None):
    # preservation of indentation
    yaml.indent(mapping=2, sequence=4, offset=2)

    yml_path = Path(path)
    data = yaml_load(yml_path.read_text()) or {}
    if main_key:
        data[main_key].update(new_data)
    else:
        data.update(new_data)

    with yml_path.open("w") as fobj:
        yaml.dump(data, fobj)
