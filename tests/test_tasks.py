# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools.tasks import main


def test_main():
    # Just testing they are not completely broken for now...
    assert main.program
