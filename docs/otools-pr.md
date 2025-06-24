# otools-pr

`otools-pr` is a helper tool for testing pull requests, hiding some of the tricky command line commands.


## Installing

Please refer to the "Installing" section of the (otools-ba)[otools-ba.md] page.

## Configuration


### Celebrimbor

You need to be able to download a database dump of the project to your laptop. This is done with the `celebrimbor_cli` command line utility. If it is not installed, you can run:

    pipx install -f git+ssh://git@github.com/camptocamp/celebrimbor-cli#egg=celebrimbor_cli`
    mkdir -p ~/.config/celebrimbor-cli

If you have the lastpass client installed, you can run:

    lpass sync
    lpass show --notes 5553291744224198495 > ~/.config/celebrimbor-cli/platforms.conf

Otherwise, open your [lastpass vault](https://lastpass.com/vault/), look for "Celebrimbor CLI configuration parameters". In a shell, type:

    gnome-text-editor ~/.config/celebrimbor-cli/platforms.conf

Then in the window that opens, copy paste the content of the note, save and exit the text editor.

### Github

You will need to have git installed and configured on your workstation:

    sudo apt install git

Normally, the setup should have been taken care of during your onboarding. If not check with your mentor to get this fixed before you go on.

### Git autoshare

If you start working a lot with projects, having git autoshare installed and configured will save you a tremendous amount of time.

    pipx install git-autoshare
    if [ ! -e ~/.config/git-autoshare/repos.yml ]
    then
    cat << EOF > ~/.config/git-autoshare/repos.yml
    github.com:
    odoo:
        orgs:
            - odoo
            - camptocamp
    enterprise:
        orgs:
            - odoo
            - camptocamp
        private: True
    EOF
    fi
    git autoshare-prefetch --quiet &


## Testing a PR

### Project checkout

We are almost there!

First get the source code of the project of your customer, it should be something like:

    cd work/projects
    git clone git@github.com:camptocamp/customername_odoo  # change this with the real name
    cd customer_odoo
    otools-submodule update
    docker compose build odoo

### Getting a database dump

Then download a database dump of the project, this could be:

    # Swiss platform
    celebrimbor_cli -p ch download -e prod -c customername  # change with the real name
    # French platform
    celebrimbor_cli -p fr download -e prod -c customername  # change with the real name

This will, after some time, get you a file. To get the name of the file, use:

    ls -rt *.pg | tail -1

### Testing the pull request

The developers have made a pull request, which is at https://github.com/camptocamp/customername_odoo/pull/1234 The important for is the number of the PR, here "1234". If you want to test the PR using the dump you just downloaded, you can run:

    otools-pr test --database-dump nameofthedump.pg 1234

Then you can point your browser to http://localhost:8069/web and start testing.

### Special cases: large databases

If the database dump is large, and restoring it takes ages, and you need to restart your test from scratch multiple time and waiting is driving you crazy, you can use this trick. On the first time, run:

    otools-pr test --create-template --database-dump nameofthedump.pg 1234

This will create a "template database" and clone it for you to run your tests. Then if you want to start again with the same dump, just run:

    otools-pr test 1234

The tool will find the template and use it to recreate the test database.

This cannot be used for enormous database because it doubles the disk usage. Yes you know which project I mean;

### Special cases: migrations

When a customer project is under migration, the `master` branch of the project will be used for the production, but you will want to test a Pull Request targeting a different branch. Check with the dev team what the name of the migration branch is. Let's assume it is `mig-18.0` for the example below. You will need to use the `--base-branch` option to pass the name of the migration branch:

    otools-pr test --base-branch mig-18.0 --database-dump nameofthedump.pg 1234

(of course you will also need to use a database dump from the migration lab or the integration, not from the production).

## Cleaning up

When you are done testing, cleanup by running:

    otools-pr clean 1234
