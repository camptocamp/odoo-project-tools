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


def remove_seq_item_with_comments(seq, value):
    """Remove ``value`` from a ruamel ``CommentedSeq`` along with the comments
    that belong to it (its end-of-line comment and the block above it), keeping
    every other item's comments anchored to that item.

    ruamel does not model this directly: ``seq.ca.items[i]`` holds the comment
    printed *after* item ``i`` -- which mixes item ``i``'s end-of-line comment
    with the block comment that precedes item ``i + 1`` -- and the block above
    the first item lives on the sequence's start comment. A plain
    ``seq.remove(value)`` therefore drops the *next* item's comment and leaves
    the removed item's block dangling on the survivor (upstream ticket, no stable
    public API yet: https://sourceforge.net/p/ruamel-yaml/tickets/377/).

    We sidestep that by normalising the stored comments into a per-item model
    (each item's inline comment + the block above it), dropping the removed
    item's entries, then rebuilding ``ca.items`` and the start comment. Inline
    placement is restored from the token column; block indentation rides along
    as leading whitespace inside the token value.
    """
    idx = seq.index(value)  # raises ValueError if absent, like list.remove
    length = len(seq)
    # Normalise: eol[i] = (text, column) of item i's end-of-line comment;
    # above[i] = block printed before item i (above[length] trails the list).
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
    # Drop the item together with its own inline + preceding-block comments.
    # ``above[idx + 1]`` shifts into ``idx``, staying anchored to the survivor.
    del seq[idx]
    eol.pop(idx)
    above.pop(idx)
    # Rebuild ruamel's storage from the model.
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
