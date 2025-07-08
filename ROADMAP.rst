otools-ba run: force image pulling if the docker-compose file is more than 1w old (meaning there has been a new image built since the last use of the tool)

otools-pr test: get the commands to download the database using celebrimbor

otools-pr test: if there is a file `*.pg` in the current directory, and no database dump was provided, and no template exist, propose to use the dump.

otools-pr checkout: add a checkout command to just checkout the source code
