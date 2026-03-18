# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from passlib.context import CryptContext

from odoo_tools.utils.password import encrypt, generate


def test_generate_password_default_length():
    password = generate()
    assert len(password) == 40
    assert password.isalnum()


def test_generate_password_custom_length():
    password = generate(length=20)
    assert len(password) == 20


def test_encrypt_password():
    password = "test_password"
    encrypted = encrypt(password)
    assert encrypted.startswith("$pbkdf2-sha512$")
    assert CryptContext(["pbkdf2_sha512"]).verify(password, encrypted)
