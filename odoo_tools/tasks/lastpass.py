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

from ..utils import ui
from ..utils.os_exec import has_exec
from ..utils.path import build_path

SHARED_C2C_FOLDER_PREFIX = "Shared-C2C-Odoo-External/"
ODOO_PROJECT_URL = "https://{}.odoo.camptocamp.{{cookiecutter.country}}"

LastpassEntry = namedtuple("LastpassEntry", "location name username comment")


def make_lp_entry(env, shortname, name, username="", location="", comment=""):
    name = f"[odoo-{env}] {shortname}"
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
        ui.exit_msg(msg)
        return
    project_folder = f"{SHARED_C2C_FOLDER_PREFIX}{project}/"
    entry_name = f"{project_folder}{lp_entry.name}\n"
    # Synchronize with LPass server, in order to catch permission issues
    command = ["lpass", "add", "--non-interactive", "--sync=now", entry_name]
    p = Popen(command, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    _input = format_lastpass_entry(project, lp_entry, password, for_cli=True)
    out, err = p.communicate(_input.encode("utf-8"))
    return p, out, err


def format_lastpass_entry(project, lp_entry, password, for_cli=False):
    project_folder = f"{SHARED_C2C_FOLDER_PREFIX}{project}/"
    # this is the format expected by the lastpass CLI,
    # do not change
    entry = f"URL: {lp_entry.location}\nUsername: {lp_entry.username}\nPassword: {password}\nNotes:\n{lp_entry.comment}\n"
    if for_cli:
        entry = f"Name: {project_folder}{lp_entry.name}\n" + entry
    else:
        entry = f"Folder: {project_folder}\nName: {lp_entry.name}\n" + entry
    return entry


def gen_password(pass_len=40):
    pwd = "".join(random.choices(string.ascii_letters, None, k=pass_len))
    print(f"\nAdmin password:\n{pwd}\n")
    return pwd


def encrypt_password(pwd):
    pwd_encrypted = CryptContext(["pbkdf2_sha512"]).encrypt(pwd)
    print(f"Encrypted admin password :\n{pwd_encrypted}\n")
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
    comment = f"Created automatically on {date.today():%d.%m.%Y}"
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
                f"manually. **\n{out}\n{err}",
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
    except Exception as e:
        print(e)


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
    except Exception as e:
        print(e)
