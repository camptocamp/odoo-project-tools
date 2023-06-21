# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools.utils import proj as proj_utils

from .common import fake_project_root
from .fixtures import clear_caches  # noqa


def test_get_project_manifest_1():
    with fake_project_root():
        manifest = proj_utils.get_project_manifest()
        expected = {
            'country': 'ch',
            'customer_name': 'ACME Inc.',
            'customer_shortname': 'acme',
            'odoo_aux_langs': 'fr_CH;it_IT',
            'odoo_company_name': 'ACME Inc.',
            'odoo_main_lang': 'de_DE',
            'odoo_version': '14.0',
            'platform_name': 'azure',
            'project_id': '1234',
            'project_name': 'acme_odoo',
            'repo_name': 'acme_odoo',
        }
        for k, v in expected.items():
            assert manifest[k] == v


def test_get_project_manifest_2():
    with fake_project_root(manifest=dict(odoo_version="16.0", project_id="4321")):
        manifest = proj_utils.get_project_manifest()
        expected = {
            'country': 'ch',
            'customer_name': 'ACME Inc.',
            'customer_shortname': 'acme',
            'odoo_aux_langs': 'fr_CH;it_IT',
            'odoo_company_name': 'ACME Inc.',
            'odoo_main_lang': 'de_DE',
            'odoo_version': '16.0',
            'platform_name': 'azure',
            'project_id': '4321',
            'project_name': 'acme_odoo',
            'repo_name': 'acme_odoo',
        }
        for k, v in expected.items():
            assert manifest[k] == v


def test_get_project_manifest_key():
    with fake_project_root():
        assert proj_utils.get_project_manifest_key("project_id") == "1234"
        assert proj_utils.get_project_manifest_key("customer_shortname") == "acme"
