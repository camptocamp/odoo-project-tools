# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import random
import string

from passlib.context import CryptContext


def generate(length=40):
    """Generate a random password of the given length."""
    return "".join(random.choices(string.ascii_letters, k=length))


def encrypt(password):
    """Encrypt a password using pbkdf2_sha512."""
    return CryptContext(["pbkdf2_sha512"]).hash(password)
