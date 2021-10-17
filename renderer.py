#!/usr/bin/env python3

from jinja2 import Environment
from jinja2 import FileSystemLoader
from pprint import pprint
import argparse
import jinja2
import os
import sys

CURDIR = os.path.dirname(os.path.abspath(__file__))
INVENTORYDIR = os.path.join(CURDIR, "inventories/production")
sys.path.append(INVENTORYDIR)

from netbox import dynamic_inventory

TEMPLATEDIR = os.path.join(CURDIR, "roles")

