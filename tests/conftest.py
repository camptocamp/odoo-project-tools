# Copyright 2024 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import pytest

from odoo_tools.utils.proj import get_project_manifest


@pytest.fixture(autouse=True)
def clear_caches():
    get_project_manifest.cache_clear()
