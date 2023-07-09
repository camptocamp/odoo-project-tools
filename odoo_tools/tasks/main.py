from invoke import Collection, Program

from . import database, lastpass, module, pr, submodule, translate

tasks_ns = Collection()

tasks_ns.add_collection(database)
tasks_ns.add_collection(lastpass)
tasks_ns.add_collection(module)
tasks_ns.add_collection(pr)
tasks_ns.add_collection(submodule)
tasks_ns.add_collection(translate)

program = Program(namespace=tasks_ns, version="0.1.0")
