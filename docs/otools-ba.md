# otools-ba

`otools-ba` is a  part of the odoo project tools set designed to to help non technical persons manage the complexity of some of the tricky command lines that are needed to work with our odoo projects.

Please report issues and feature requests on https://github.com/camptocamp/odoo-project-tools/issues

## installing

otools-ba is installed together with the rest of odoo-project-tools. The easiest way is to use pipx as an installer. If that command is not available on your laptop, you can run:

    sudo apt update
    sudo apt install pipx

This is only needed once.

Then

    pipx install  -f  git+https://github.com/camptocamp/odoo-project-tools.git


Run a quick test:

    otools-ba  --help

This should print a help summary such as:

    Usage: otools-ba [OPTIONS] COMMAND [ARGS]...

    Options:
    --help  Show this message and exit.

    Commands:
    run  Run a standard odoo version locally, for a customer demo or...


If you get an error message such as:

    otools-ba: command not found

Then you need to perform a simple operation to fix the configuration:

    echo -e '\nexport PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc


Then logout of your session and reauthenticate for the configuration to be taken into account.

## Commands


There are (or will be) different commands available. You can get a list of all the commands by running in a shell:

    odools-ba --help

For a given command, using `otools-ba commandname --help` will give you a short summary.


### otools-ba run

The first command available is `otools-ba run`. That command can be used to start an Odoo Enterprise version with version starting from 14.0 to the latest stable release.

The simplest way to use it is to pass the version number on the command line. So to start Odoo 15.0 you can run:

    otools-ba run 15.0

This will download a docker image for the specified version (depending on the speed of your connection, this can take a few minutes the first time), and then start the instance, and when the instance is ready, launch a web browser connected to the instance.

When you are done, you can shut down the instance by typing `Ctrl-c` in the terminal from which you started `otools-ba`.  This will terminate the Odoo. The database is kept on your laptop. If you restart the same version, you will get the data you configured back again.

If you want to start with a fresh empty database, you can pass the `--empty-db` option:

    otools-ba run --empty-db 15.0

This will drop any previously existing database for 15.0 and create a new one.

If you want to work on two versions in parallel, to compare them, you will need to use a custom port on one of the instances. The default port is `8080`, but you can set a different one with the `--port` option, like this:

    otools-ba run --port 8081 16.0

As a final note, the images used are updated on a regular basis with the latest version of the source code of Odoo. In order to preserve bandwidth, `otools-ba run` will reuse an image it has already downloaded. If you want to refresh the image, you can use the `--force-image-pull` option:

    otools-ba run --force-image-pull 16.0
