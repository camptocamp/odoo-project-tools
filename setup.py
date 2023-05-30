#!/usr/bin/env python

from setuptools import setup

with open("README.md") as f:
    readme = f.read()

requirements = [
    "future==0.18.3",
    "invoke==2.0.0",
    "requests==2.25.1",
    "git-aggregator>=1.7.2",
    "git-autoshare>=1.0.0b2",
    "passlib",
    "clipboard==0.0.4",
    "marabunta>=0.10.6",
    "pre-commit",
    "psycopg2-binary>=2.7.6",
    "gitpython",
    "ruamel.yaml>=0.15.66",
    "kaptan==0.5.12",
    "PyYAML==5.4.1",
    "wheel",
    "cookiecutter",
]

test_requirements = []

setup(
    name="odoo-project-tasks",
    use_scm_version=True,
    description="CLI to automate Odoo project tasks with Invoke",
    long_description=readme,
    author="Camptocamp SA",
    author_email="info@camptocamp.com",
    url="https://github.com/camptocamp/odoo-project-tasks",
    packages=["src"],
    entry_points={"console_scripts": ["odoo-tools=tasks.main:program.run"]},
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.7",
    setup_requires=["setuptools_scm"],
    license="MIT license",
    zip_safe=False,
    keywords="odoo-tools",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    test_suite="tests",
    tests_require=test_requirements,
)
