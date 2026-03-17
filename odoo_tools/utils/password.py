# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets
import string

from passlib.context import CryptContext


def generate(length=40):
    """Generate a random password of the given length."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def encrypt(password):
    """Encrypt a password using pbkdf2_sha512."""
    return CryptContext(["pbkdf2_sha512"]).hash(password)
