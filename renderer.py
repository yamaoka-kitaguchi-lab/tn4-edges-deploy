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


def render_templates(tpl_path, device_role, inventories, manufacturer=None, trim_blocks=False):
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
    if manufacturer is not None:
      if params["manufacturer"] != manufacturer:
        continue
    try:
      ip = params["ansible_host"]
      host = f"{hostname} ({ip})"
      raw = template.render(params)
    except Exception as e:
      print(f"An error occurred while rendering {host}. Aborted: {e}", file=sys.stderr)
      sys.exit(4)
    else:
      ignore_empty_lines = lambda s: "\n".join([l for l in s.split("\n") if l != ""])
      results[host] = ignore_empty_lines(raw)

  return results


def main():
  parser = argparse.ArgumentParser(description="rendering config template reflecting NetBox database")
  parser.add_argument("-t", "--template", required=True, dest="PATH", help="path of the template from (e.g., ./roles/juniper/templates/overwrite.cfg.j2)")
  parser.add_argument("-d", "--device-role", required=True, dest="ROLE", help="device role (e.g., edge-sw)")
  parser.add_argument("-m", "--manufacturer", required=False, dest="VENDOR", help="manufacturer (e.g., juniper)")
  parser.add_argument("-o", "--output", required=False, dest="DIR_PATH", help="save rendered config if specified")
  args = parser.parse_args()

  tpl_path = args.PATH
  device_role = args.ROLE.upper()
  manufacturer = args.VENDOR
  output_dir = args.DIR_PATH.rstrip("/")
  inventories = load_inventories()

  results = render_templates(tpl_path, device_role, inventories, manufacturer=manufacturer)
  for host, result in results.items():
    print("\n".join([":"*25, host, ":"*25, result]), end="\n"*2)
    if output_dir is not None:
      hostname = host.split()[0]
      with open(f"{output_dir}/{hostname}.cfg", "w") as fd:
        fd.write(result)


if __name__ == "__main__":
  main()
