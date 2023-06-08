# This code comes from business-cloud-template, if you fix something here,
# please consider fixing it there too.


import fileinput
import random
import string
from collections import namedtuple
from datetime import date
from subprocess import PIPE, Popen

from invoke import task
from passlib.context import CryptContext

from ..utils.os_exec import has_exec
from .common import build_path, exit_msg

SHARED_C2C_FOLDER_PREFIX = "Shared-C2C-Odoo-External/"
ODOO_PROJECT_URL = "https://{}.odoo.camptocamp.{{cookiecutter.country}}"

LastpassEntry = namedtuple("LastpassEntry", "location name username comment")


def make_lp_entry(env, shortname, name, username="", location="", comment=""):
    name = "[odoo-{}] {}".format(env, shortname)
    return LastpassEntry(
        location=location, name=name, username=username, comment=comment
    )


def put_lp_pwd(project, lp_entry, password):
    """Store password on LP."""
    if not has_exec("lpass"):
        msg = (
            "** ERROR : LastPass CLI is not available"
            "please create the entry manually. **"
        )
        exit_msg(msg)
        return
    project_folder = "{}{}/".format(SHARED_C2C_FOLDER_PREFIX, project)
    entry_name = "{}{}\n".format(project_folder, lp_entry.name)
    # Synchronize with LPass server, in order to catch permission issues
    command = ["lpass", "add", "--non-interactive", "--sync=now", entry_name]
    p = Popen(command, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    _input = format_lastpass_entry(project, lp_entry, password, for_cli=True)
    out, err = p.communicate(_input.encode("utf-8"))
    return p, out, err


def format_lastpass_entry(project, lp_entry, password, for_cli=False):
    project_folder = "{}{}/".format(SHARED_C2C_FOLDER_PREFIX, project)
    # this is the format expected by the lastpass CLI,
    # do not change
    entry = ("URL: {}\nUsername: {}\nPassword: {}\nNotes:\n{}\n").format(
        lp_entry.location, lp_entry.username, password, lp_entry.comment
    )
    if for_cli:
        entry = "Name: {}{}\n".format(project_folder, lp_entry.name) + entry
    else:
        entry = "Folder: {}\nName: {}\n".format(project_folder, lp_entry.name) + entry
    return entry


def gen_password(pass_len=40):
    pwd = "".join(random.choices(string.ascii_letters, None, k=pass_len))
    print("\nAdmin password:\n{}\n".format(pwd))
    return pwd


def encrypt_password(pwd):
    pwd_encrypted = CryptContext(["pbkdf2_sha512"]).encrypt(pwd)
    print("Encrypted admin password :\n{}\n".format(pwd_encrypted))
    return pwd_encrypted


def change_admin_pwd(pwd_encrypted):
    placeholder = "__GENERATED_ADMIN_PASSWORD__"
    # TODO: change depending on new structure
    # use root_path to get root project directory
    pre_file = build_path("odoo/songs/install/pre.py")

    with fileinput.FileInput(pre_file, inplace=True) as file:
        for line in file:
            print(line.replace(placeholder, pwd_encrypted), end="")


def send_pwd_to_lp(pwd, username="admin"):
    """Store generated pwds on LP and print them."""
    project_name = "{{cookiecutter.project_name}}"
    shortname = "{{cookiecutter.customer_shortname}}"
    name = shortname
    locations = [
        ("prod", ODOO_PROJECT_URL.format(name)),
        ("integration", ODOO_PROJECT_URL.format("integration." + name)),
    ]
    comment = "Created automatically on {:%d.%m.%Y}".format(date.today())
    for env, location in locations:
        entry = make_lp_entry(env, shortname, name, username, location, comment)
        formatted = format_lastpass_entry(project_name, entry, pwd, for_cli=True)
        for line in formatted.splitlines():
            print("  ", line)
        proc, out, err = put_lp_pwd(project_name, entry, pwd)
        if proc.returncode != 0:
            print(
                "\n  ",
                "** ERROR during the storing in LastPass, "
                "please create the entry "
                "manually. **\n{}\n{}".format(out, err),
            )
            return
        print(
            "\n  ",
            "** This entry has been automatically created in LastPass for you. **",
        )
        print("\n  -------------------------------\n")


def generate_admin_pwd_and_put_to_lastpass():
    """Generate a random admin password push this on Lastpass.

    The password is generate after one hash is created and put in :
    odoo/songs/install/pre.py
    Finally the password is push to Lastpass on the right folder
    """
    pwd = gen_password()
    pwd_encrypted = encrypt_password(pwd)
    change_admin_pwd(pwd_encrypted)
    try:
        send_pwd_to_lp(pwd)
    except Exception as exept:
        print(exept)


@task(name="gen-admin-pwd")
def generate_admin_pwd(ctx):
    """Generate a random admin password.
    And initialize it into songs if not set yet
    only if in songs/install/pre.py :
    ctx.env.user.password_crypt =  '__GENERATED_ADMIN_PASSWORD__'

    The password is generate after one hash is created and put in :
    odoo/songs/install/pre.py
    """
    pwd = gen_password()
    pwd_encrypted = encrypt_password(pwd)
    change_admin_pwd(pwd_encrypted)


@task(name="send-admin-pwd-to-lpass")
def send_admin_pwd_to_lpass(ctx):
    """Push admin password this on Lastpass."""
    pwd = gen_password()
    pwd_encrypted = encrypt_password(pwd)
    change_admin_pwd(pwd_encrypted)
    try:
        send_pwd_to_lp(pwd)
    except Exception as exept:
        print(exept)
