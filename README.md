### Vitolink: A Viessmann Optolink influxdb logging utility

This software can be used to communicate to a Viessmann Vitotronic via KW2 protocol and log things to influxdb.
It is still under heavy development, please use at your own risk!

### Installation

```
virtualenv --no-site-packages venv
. ./venv/bin/activate
pip install -r requirements.txt
cp defaults.ini.sample defaults.ini
# edit defaults.ini
python vitolink.py
```
