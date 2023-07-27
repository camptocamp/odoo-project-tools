#### Odoo Project Tasks


#### Installation


```
pip install --user https://github.com/camptocamp/odoo-project-tools/archive/refs/heads/master.tar.gz"


## Project conversion

Go to the root of the project, and 

* run otools-project init
* start a local instance with a copy of the production database
* run `otools-conversion -i localhost -p 80 -d odoodb`

You will get prompted for the admin password (should be `admin` if you
are running locally in DEV mode.

The script will move things around, figure out which OCA addons are installed
on your instance, and when done display a message about what further manual
steps are required, and what you need to check for.
