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



def main():
  parser = argparse.ArgumentParser(description="Rendering config template reflecting NetBox database")
  parser.add_argument("-t", "--template", dest="tpl_path", help="Path of template (e.g., juniper/overwrite.cfg.j2)")
  args = parser.parse_args()

  tpl_path = os.path.join(TEMPLATEDIR, args.tpl_path)
  print(tpl_path)


if __name__ == "__main__":
  main()