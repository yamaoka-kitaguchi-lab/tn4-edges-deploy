#!/usr/bin/env python3

from pprint import pprint
import argparse
import jinja2
import os
import sys
import time

CURDIR = os.path.dirname(os.path.abspath(__file__))
INVENTORYDIR = os.path.join(CURDIR, "inventories/production")
sys.path.append(INVENTORYDIR)

from netbox import dynamic_inventory


def load_inventories():
  start_at = time.time()
  print("Loading inventories from NetBox, this may take a while...", end=" ", flush=True)
  inventories = dynamic_inventory()
  elapsed_time = round(time.time() - start_at, 1)
  print(f"completed successfully ({elapsed_time}sec)", flush=True)
  return inventories


def render_templates(tpl_path, device_role, inventories, trim_blocks=False):
  loader_base = os.path.join(CURDIR, os.path.dirname(tpl_path))
  tpl_name = os.path.basename(tpl_path)
  env = jinja2.Environment(loader=jinja2.FileSystemLoader(loader_base), trim_blocks=trim_blocks)

  try:
    template = env.get_template(tpl_name)
  except jinja2.exceptions.TemplateNotFound:
    print(f"No such template: {tpl_path}", file=sys.stderr)
    sys.exit(1)

  try:
    hostnames = inventories[device_role]["hosts"]
  except KeyError:
    print(f"No such device role: {device_role}", file=sys.stderr)
    sys.exit(2)

  results = {}
  for hostname in hostnames:
    params = inventories["_meta"]["hostvars"][hostname]
    ip = params["ansible_host"]
    try:
      host = f"{hostname} ({ip})"
      results[host] = template.render(params)
    except Exception as e:
      print(f"An error occurred while rendering {host}. Aborted: {e}", file=sys.stderr)

  return results


def main():
  parser = argparse.ArgumentParser(description="rendering config template reflecting NetBox database")
  parser.add_argument("-t", "--template", required=True, dest="PATH", help="path of the template from (e.g., ./roles/juniper/templates/overwrite.cfg.j2)")
  parser.add_argument("-d", "--device-role", required=True, dest="ROLE", help="device role (e.g., edge-sw)")
  args = parser.parse_args()

  tpl_path = args.PATH.strip("/")
  device_role = args.ROLE.upper()
  inventories = load_inventories()

  results = render_templates(tpl_path, device_role, inventories)
  for host, result in results.items():
    print("\n".join([":"*15, host, ":"*15]))
    print(result, end="\n"*2)


if __name__ == "__main__":
  main()
