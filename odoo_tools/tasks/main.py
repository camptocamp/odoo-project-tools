from invoke import Collection, Program

from . import (
    database,
    lastpass,
    module,
    # submodule,
    translate,
)

tasks_ns = Collection()

tasks_ns.add_collection(database)
tasks_ns.add_collection(lastpass)
tasks_ns.add_collection(module)
tasks_ns.add_collection(translate)
# tasks_ns.add_collection(submodule)
program = Program(namespace=tasks_ns, version="0.1.0")
