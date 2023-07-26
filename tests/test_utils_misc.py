# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools.utils import misc as misc_utils


def test_parse_ini_key():
    ini = "[avgheader]\nfoo = 1\nbaz = two"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "foo") == "1"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "baz") == "two"


def test_parse_ini_no_header_key():
    ini = "foo = 1\nbaz = two"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "foo") == "1"
    assert misc_utils.get_ini_cfg_key(ini, "avgheader", "baz") == "two"
