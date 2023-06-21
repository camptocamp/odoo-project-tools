import pytest

from odoo_tools.utils.proj import get_project_manifest


@pytest.fixture(autouse=True)
def clear_caches():
    get_project_manifest.cache_clear()
