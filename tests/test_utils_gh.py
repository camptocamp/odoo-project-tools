# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo_tools.utils import gh as gh_utils


def test_parse_github_url():
    url = "https://github.com/OCA/edi/pull/731"
    expected = {
        'upstream': 'OCA',
        'repo_name': 'edi',
        'entity_type': 'pull',
        'entity_id': '731',
    }
    res = gh_utils.parse_github_url(url)
    for k, v in expected.items():
        assert res[k] == v
    uri = "OCA/edi#731"
    res = gh_utils.parse_github_url(uri)
    for k, v in expected.items():
        assert res[k] == v
    uri = "https://github.com/OCA/edi/commit/8f3a3a3bfa6c97984cad7f63e1f288841c4f7eda"
    expected.update(
        {
            "entity_type": "commit",
            "entity_id": "8f3a3a3bfa6c97984cad7f63e1f288841c4f7eda",
        }
    )
    res = gh_utils.parse_github_url(uri)
    for k, v in expected.items():
        assert res[k] == v
