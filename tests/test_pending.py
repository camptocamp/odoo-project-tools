# Copyright 2026 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import responses

from odoo_tools.cli import pending

from .common import mock_pending_merge_repo_paths

REPO_NAME = "edi-framework"
# The pending-merges template used by the fixture declares these pull requests.
PENDING_PR_NUMBERS = (774, 773, 663, 759)
# Long enough to push the grid past the terminal width set below.
LONG_TITLE = (
    "[19.0][ADD] base_business_document_import_iban: to remove direct "
    "base_iban dependency out of base_business_document_import"
)


def test_show_keeps_state_indicator_when_titles_overflow(project):
    """Long titles must not squeeze the state indicator column out of the grid.

    Rich shrinks the whole grid when it doesn't fit, so a wide title column used
    to collapse the one-char indicator (and the last-updated column) to nothing.
    """
    mock_pending_merge_repo_paths(REPO_NAME)
    with responses.RequestsMock() as mocked_responses:
        for number in PENDING_PR_NUMBERS:
            mocked_responses.add(
                responses.GET,
                f"https://api.github.com/repos/OCA/{REPO_NAME}/pulls/{number}",
                json={
                    "state": "open",
                    "merged": False,
                    "title": LONG_TITLE,
                    "updated_at": "2026-07-01T10:00:00Z",
                },
            )
        result = project.invoke(
            pending.show_pending,
            catch_exceptions=False,
            # Narrow enough that the titles overflow the grid
            env={"COLUMNS": "100", "GITHUB_TOKEN": "fake-token"},
        )
    assert result.exit_code == 0
    rows = [line for line in result.output.splitlines() if line.strip()]
    assert len(rows) == len(PENDING_PR_NUMBERS)
    # Each row keeps its state indicator; the title is ellipsized instead
    for line, number in zip(rows, PENDING_PR_NUMBERS, strict=True):
        assert line.startswith("●"), line
        assert f"OCA/{REPO_NAME}#{number}" in line, line
        assert "…" in line, line


def test_show_no_check_skips_github(project):
    mock_pending_merge_repo_paths(REPO_NAME)
    with responses.RequestsMock():  # would fail on any HTTP call
        result = project.invoke(
            pending.show_pending, ["--no-check"], catch_exceptions=False
        )
    assert result.exit_code == 0
    assert f"OCA/{REPO_NAME}#774" in result.output
