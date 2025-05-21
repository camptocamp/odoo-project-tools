0.10.1 (2025-05-21)
+++++++++++++++++++

**Bugfixes**

* otools-project: fix local checkout automated tests
* Fix tests broken by change introduced in click 8.2.1

0.10.0 (2025-05-21)
+++++++++++++++++++

**Features and Improvements**

* New tool otools-ba run <odooversion>

  This tool can be used to run a vanilla Odoo, through the new docker images.

  ```
  $ otools-ba run --help
  Usage: otools-ba run [OPTIONS] [VERSION]

    Run a standard odoo version locally, for a demo or

  Options:
    --empty-db / --no-empty-db      force recreation of an empty database.
                                    Otherwise a previously created database for
                                    that version can be reused.
    -p, --port INTEGER              The network port on which you will need to
                                    connect to access odoo.
    --force-image-pull / --no-force-image-pull
                                    Force pulling updated image
    --help                          Show this message and exit.
  ```
* new command otools-ba

  This command contains tools crafted to help functional people work, possibly
  not directly on a project, without having to bother with knowing tons of
  command line tools.
* Use git autoshare in command otools-project checkout-local-odoo

**Bugfixes**

* otools-addon add: filter by odoo series
  Without the patch, adding or upgrading an odoo addon would always get
  the latest version, which could result in adding an addon meant for odoo
  17 on a project using odoo 15.
* otools-conversion: fix an issue preventing more than 1 addon in a given external-src subdirectory from being added to the requirements of the project.
* crash of otools-project checkout-local-odoo on second run of the command
* otools-conversion: don't crash if odoorpc is not installed (esp. allow to call otools-conversion --help in that configuration)
* otools-conversion: stage some missed out files created / modified during the conversion process

**Documentation**

* improve the --help option output on the different tools
* otools-conversion: improve the documented process in the project README file to mention when pre-commit should be enabled.
* otools-conversion: document how to configure the CI with Github Actions on the project

0.9.0 (2023-08-19)
++++++++++++++++++

**Features and Improvements**

* cli.add_pending: aggregate by default
* utils.pending_merge.add_pending: aggregate by default
* Add pending.aggregate cli
* cli.pending.show_prs: allow to filter and purge
*
* utils.misc: add generic parse_ini_cfg
* utils.proj: add get_current_version
* utils.ui: add echo
* Add utils.marabunta
* tests.make_fake_project_root setup version file too
* utils.misc: add SmartDict
* project.init: allow pass version
* project.init: gen proj specific .bumpversion.cfg

**Bugfixes**

* utils.req: fix replace_requirement output
* utils.pkg: fix has_pending_merge
* utils.pending_merge: fix aggregator init
* utils.pending_merge: fix ui
* Fix utils.pypi: do not break if not found
* utils.pkg: misc fixes
* utils.req: fix dev req path
* Convert delete submodules storage

**Remove**

* Drop obsolete tasks.submodule

**Documentation**

* cli.release: add todo

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.8.0 (2023-08-18)
++++++++++++++++++

**Features and Improvements**

* Add conversion script for template v2
* utils.ui: improve echo
* Update templates/.proj.v2.cfg
* utils.req: add make_requirement_line_for_proj_fork
* utils.proj: improve get_current_version
* utils.misc: add generic parse_ini_cfg
* utils.proj: add get_current_version
* utils.ui: add echo
* Add utils.marabunta
* tests.make_fake_project_root setup version file too
* utils.misc: add SmartDict
* project.init: allow pass version
* project.init: gen proj specific .bumpversion.cfg

**Bugfixes**

* Fix utils.pending_merge.show_prs
* Convert: misc imp
* cli.project: misc fix/imp
*

**Remove**

* Tasks: get rid of cookiecutter_context func

**Documentation**

* Update mig readme

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.7.0 (2023-07-27)
++++++++++++++++++

**Features and Improvements**

* Add addon.print_requirement cli
* Add pending.show cli
* utils.pypi: improve odoo_name_to_pkg_name
* utils.req: add make_requirement_line_for_proj_fork
* utils.proj: improve get_current_version
* utils.misc: add generic parse_ini_cfg
* utils.proj: add get_current_version
* utils.ui: add echo
* Add utils.marabunta
* tests.make_fake_project_root setup version file too
* utils.misc: add SmartDict
* project.init: allow pass version
* project.init: gen proj specific .bumpversion.cfg

**Bugfixes**

* Rename c2c_git_remote to company_git_remote
* utils.pypi: fix odoo pkg name version handling
* Finish cleanup of obsolete tasks.common
* utils.pending_merge: drop dead code
* utils.pending_merge: draft aggregator api
* Adapt tasks.submodule

**Remove**

* Tasks: get rid of cookiecutter_context func

**Documentation**

* Add TODO for exceptions

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.6.0 (2023-07-26)
++++++++++++++++++

**Features and Improvements**

* Setup bumpversion
* Setup towncrier
* Add otools-release
* Make test mock_pending_merge_repo_paths re-usable
* Make root project cfg configurable
* utils.misc: add generic parse_ini_cfg
* utils.proj: add get_current_version
* utils.ui: add echo
* Add utils.marabunta
* tests.make_fake_project_root setup version file too
* utils.misc: add SmartDict
* project.init: allow pass version
* project.init: gen proj specific .bumpversion.cfg

**Bugfixes**

* Cleanup pinned dependencies
* Cleanup PyYAML usage
* Finish cleanup of obsolete tasks.common
* utils.pending_merge: drop dead code
* utils.pending_merge: draft aggregator api
* Adapt tasks.submodule

**Remove**

* Tasks: get rid of cookiecutter_context func

**Documentation**

* Add TODO for exceptions

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.5.0 (2023-06-21)
++++++++++++++++++

**Features and Improvements**

* Add addon add-pending
* Add utils.pending_merge
* tasks.submodule: refactor pending merge handling
* utils.req: add editable mode
* Add utils.ui
* Add exceptions.Exit
* Add exceptions.PathNotFound
* Add utils.config
* Tests: add fake_project_root ctx manager
* Add otools-addon.add
* Add tests.common.make_fake_project_root
* Add pypi and requirements utils

**Bugfixes**

* Fix README installation
* Fix req.replace_requirement for editable
* utils.pending_merge: fix api_url
* utils.pending_merge: drop dead code
* utils.pending_merge: draft aggregator api
* Adapt tasks.submodule

**Remove**

* Tasks: get rid of cookiecutter_context func

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.4.0 (2023-06-21)
++++++++++++++++++

**Features and Improvements**

* Improve tests.common
* Add common test fixture to clean cache
* utils.pkg: improve class
* utils.req: add editable mode
* Add utils.ui
* Add exceptions.Exit
* Add exceptions.PathNotFound
* Add utils.config
* Tests: add fake_project_root ctx manager
* Add otools-addon.add
* Add tests.common.make_fake_project_root
* Add pypi and requirements utils

**Bugfixes**

* Fix utils.yaml w/ empty file
* utils.req: fix get_addon_requirement
* Fix utils.path.build_path: always return path obj
* tasks: drop obsolete common

**Remove**

* Tasks: get rid of cookiecutter_context func

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.3.0 (2023-06-21)
++++++++++++++++++

**Features and Improvements**

* Test utils.gh.parse_github_url
* Test utils.path.build_path
* utils.path.root_path: return path obj
* tasks.submodule: allow show_prs to purge by state
* Add utils.proj
* Add utils.path.get_root_marker
* Add utils.os_exec

**Bugfixes**

* Fix requirements-parser dependency
* tasks.pr: fix pr tasks print msg

**Remove**

* Tasks: get rid of cookiecutter_context func

**Build**

* Apply pre-commit to tests too
* Show test coverage


0.2.0 (2023-06-05)
++++++++++++++++++

**Features and Improvements**

* Improve addon.add
* Add Package utils
* Add otools-addon.add
* Add tests.common.make_fake_project_root
* Add pypi and requirements utils


0.1.0 (2023-05-31)
++++++++++++++++++

**Features and Improvements**

* Add project init
