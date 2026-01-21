from invoke import Collection, Program

from . import (
    lastpass,
    module,
)

tasks_ns = Collection()
tasks_ns.add_collection(Collection.from_module(lastpass))
tasks_ns.add_collection(Collection.from_module(module))
program = Program(namespace=tasks_ns, version="0.1.0")
