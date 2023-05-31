# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from pathlib import PosixPath

FIXTURES_PATH = PosixPath(__file__).parent / "fixtures"

def get_fixture_path(fname):
    return FIXTURES_PATH / fname


def get_fixture(fname):
    with open(get_fixture_path(fname), "r") as fd:
        return fd.read()
