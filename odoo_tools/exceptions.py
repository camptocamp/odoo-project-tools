# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


from click.exceptions import Exit as _Exit


class PathNotFound(IOError):
    pass


class ProjectRootFolderNotFound(Exception):
    pass


class ProjectConfigException(Exception):
    pass


class Exit(_Exit):
    exit_code = 1

    def __init__(self, msg):
        super().__init__(self.exit_code)
        self.message = msg
        print(self.message)


# TODO: manage exceptions globally and homogenously.
# See https://stackoverflow.com/questions/45875930/is-there-a-way-to-handle-exceptions-automatically-with-python-click
