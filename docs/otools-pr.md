# otools-pr

`otools-pr` is a helper tool for testing pull requests, hiding some of the tricky command line commands.


## Installing

Please refer to the "Installing" section of the [otools-ba](otools-ba.md) page.

## The lazy way

Instead of (or in addition to) using `otools-pr`, you can also access an odoo instance running on someone else's computer.

For this, you and that other person should be on the same local network (both at the office, or both on the VPN).

Kindly as that other person to start odoo, and then ask for his/her IP address and for the odoo port.
 - IP address can be retrieved with `ip -4 a` (the interface should be `ppp0` if on the VPN);
 - The Odoo port usually is 8069, but it might vary depending on practices.

With those information, you should be able to connect to an odoo instance from your browser with that url `http://<IP ADDRESS>:<ODOO PORT>`.


## Configuration

### Git and Github

You will need to have git installed and configured on your workstation:

    sudo apt install git

Normally, the setup should have been taken care of during your onboarding. If not check with your mentor to get this fixed before you go on.

To check if this setup was done you can run:

    git clone --depth 1 git@github.com:camptocamp/celebrimbor-cli

If everything goes well, you can clean up the created directory:

    rm -rf celebrimbor-cli

However, if you have an error message saying you don't have permission, then there are some parts of the configuration of your workstation that is missing. This is beyond this document's scope, get in touch with the helpdesk for assistance.

### Celebrimbor

You need to be able to download a database dump of the project to your laptop. This is done with the `celebrimbor_cli` command line utility. If it is not installed, you can run:

    mkdir -p ~/.config/celebrimbor-cli
    pipx install -f git+ssh://git@github.com/camptocamp/celebrimbor-cli#egg=celebrimbor_cli


Open your [lastpass vault](https://lastpass.com/vault/), look for "Celebrimbor CLI configuration parameters". In a shell, type:

    gnome-text-editor ~/.config/celebrimbor-cli/platforms.conf

Then in the window that opens, copy paste the content of the note, save and exit the text editor.



### Git autoshare

If you start working a lot with projects, having git autoshare installed and configured will save you a tremendous amount of time.

    pipx install git-autoshare
    if [ ! -e ~/.config/git-autoshare/repos.yml ]
    then
    mkdir -p ~/.config/git-autoshare
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

First get the source code of the project of your customer. Different things depend on the name of the customer, so you can create a variable to help you in copy-pasting the commands:

    export CUSTOMER=customername

Then:

    cd work/projects
    git clone git@github.com:camptocamp/${CUSTOMER}_odoo  # change this with the real name
    cd ${CUSTOMER}_odoo
    otools-submodule update
    docker compose build odoo



### Getting a database dump

Then download a database dump of the project. The command depends on the platform (CH or FR) of your project.

**⚠️ Important**

Most of the time, the name of the customer on the hosting platform and on the github project are the same, but not always. In the commands below, we use the same variable `CUSTOMER` for the name of the project on the platform as in the name of the project. If you get errors, it can be because the names are different. Ask a dev in your team, they will be able to help.


For the Swiss platform:


    celebrimbor_cli -p ch download -e prod -c ${CUSTOMER}  # change with the real name

For the French platform:

    celebrimbor_cli -p fr download -e prod -c ${CUSTOMER}  # change with the real name

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
