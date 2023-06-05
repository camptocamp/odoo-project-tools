# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import re


def parse_github_url(entity_spec):
    # "entity" is either a PR, commit or a branch
    # TODO: input validation

    # check if it's in a custom pull format // nmspc/repo#pull
    custom_parts = re.match(r"([\w-]+)/([\w-]+)#(\d+)", entity_spec)
    if custom_parts:
        entity_type = "pull"
        upstream, repo_name, entity_id = custom_parts.groups()
    else:
        # this is meant to be an web link then
        # Example:
        # https://github.com/namespace/repo/pull/1234/files#diff-deadbeef
        # parts 0, 1 and 2  /    p3   / p4 / p5 / p6 | part to trim
        #                    ========= ==== ==== ====
        # as we're not interested in parts 7 and beyond, we're just trimming it
        # this is done to allow passing link w/ trailing garbage to this task
        try:
            upstream, repo_name, entity_type, entity_id = entity_spec.split("/")[3:7]
        except ValueError:
            msg = (
                "Could not parse: {}.\n"
                "Accept formats are either:\n"
                "* Full PR URL: https://github.com/user/repo/pull/1234/files#diff-deadbeef\n"
                "* Short PR ref: user/repo#pull-request-id"
                "* Cherry-pick URL: https://github.com/user/repo/[tree]/<commit SHA>"
            ).format(entity_spec)
            raise ValueError(msg)

    # force uppercase in OCA upstream name:
    # otherwise `oca` and `OCA` are treated as different namespaces
    if upstream.lower() == "oca":
        upstream = "OCA"

    return {
        "upstream": upstream,
        "repo_name": repo_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }
