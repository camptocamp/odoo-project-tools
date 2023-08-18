#### Odoo Project Tasks


#### Installation


```
pip install --user https://github.com/camptocamp/odoo-project-tools/archive/refs/heads/master.tar.gz"


## Project conversion

Go to the root of the project, and 

* run sync from Vincent's fork of odoo-template?

    invoke project.sync --fork vrenaville/odoo-template --version mig_to_core 

* init project at v1

    PROJ_TMPL_VER=1 otools-project init

  stage new files and commit
    
    git commit -m "Init proj v1"

  You can always reset hard to this commit when trying the conversion to v2 ;)

* Install conversion tools

    pip install odoo-project-tools[convert]  # FIXME no released pkg yet


* start a local instance with a copy of the production database
* Run conversion

    CONV_ADMIN_PWD=admin otools-conversion -p 8069

The script will move things around, figure out which OCA addons are installed
on your instance, and when done display a message about what further manual
steps are required, and what you need to check for.

Stage all changes and commit `g ci -m "Convert to proj v2"`