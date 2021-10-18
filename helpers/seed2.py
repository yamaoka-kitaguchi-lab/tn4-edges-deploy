#!/usr/bin/env python3
from pprint import pprint
import os
import sys
import re
import json
import yaml

from urllib.parse import urlencode
import requests

from ansible.constants import DEFAULT_VAULT_ID_MATCH
from ansible.parsing.vault import VaultLib
from ansible.parsing.vault import VaultSecret
from ansible.parsing.vault import AnsibleVaultError

from descriptions import load as migration_rule_load
from devices import load as device_load
from vlans import load as vlan_load
from interfaces import load_chassis_interfaces as chassis_interface_load

VAULT_FILE = os.path.join(os.path.dirname(__file__), "../inventories/production/group_vars/all/vault.yml")
VAULT_PASSWORD_FILE = os.path.join(os.path.dirname(__file__), "../.secrets/vault-pass.txt")


class NetBoxClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = netbox_url.rstrip("/") + "/api"
    self.token = netbox_api_token


  def query(self, request_path, data=None, update=False):
    headers = {
      "Authorization": f"Token {self.token}",
      "Content-Type": "application/json",
      "Accept": "application/json; indent=4"
    }
    responses = []
    url = self.api_endpoint + request_path

    if data:
      cnt, limit = 0, 100
      while cnt < len(data):
        d = data[cnt:cnt+limit]
        raw = None
        if update:
          raw = requests.patch(url, json.dumps(d), headers=headers, verify=True)
        else:
          raw = requests.post(url, json.dumps(d), headers=headers, verify=True)
        responses += json.loads(raw.text)
        cnt += limit

    else:
      while url:
        raw = requests.get(url, headers=headers, verify=True)
        res = json.loads(raw.text)
        responses += res["results"]
        url = res["next"]

    return responses


  def get_all_vlans(self):
    return self.query("/ipam/vlans/")


  def get_all_vids(self):
    vlans = self.get_all_vlans()
    return [vlan["vid"] for vlan in vlans]


  def get_vlan_resolve_hints(self):
    hints = {}
    for vlan in self.get_all_vlans():
      hints[vlan["vid"]] = vlan["id"]
    return hints


  def make_vlan_resolver(self):
    hints = self.get_vlan_resolve_hints()
    def resolver(vid):
      try:
        return hints[vid]
      except KeyError:
        return None
    return resolver


  def get_all_ipaddresses(self):
    return self.query("/ipam/ip-addresses/")


  def get_all_ips(self):
    ipaddrs = self.get_all_ipaddresses()
    return [ipaddr["address"] for ipaddr in ipaddrs]


  def get_ip_resolve_hint(self):
    hints = {}
    for ip in self.get_all_ipaddresses():
      hints[ip["address"]] = ip["id"]
    return hints


  def get_all_sitegroups(self):
    return self.query("/dcim/site-groups/")


  def get_all_sitegroupslugs(self):
    sitegroups = self.get_all_sitegroups()
    return [sitegroup["slug"] for sitegroup in sitegroups]


  def get_all_regions(self):
    return self.query("/dcim/regions/")


  def get_all_regionsslug(self):
    regions = self.get_all_regions()
    return [region["slug"] for region in regions]


  def get_all_sites(self):
    self.all_sites = self.query("/dcim/sites/")
    return self.all_sites


  def get_all_siteslugs(self):
    sites = self.get_all_sites()
    return [site["slug"] for site in sites]


  def get_all_devices(self):
    self.all_devices = self.query("/dcim/devices/")
    return self.all_devices


  def get_all_vcs(self):
    self.all_vcs = self.query("/dcim/virtual-chassis/")
    return self.all_vcs


  def lookup_sitegroup(self, site_slug):
    for site in self.get_all_sites():
      if site["slug"] == site_slug:
        return site["group"]["slug"]
    print(f"Unknown site: {site_slug}")
    return None


  def lookup_region(self, site_slug):
    for site in self.get_all_sites():
      if site["slug"] == site_slug:
        return site["region"]["slug"]
    print(f"Unknown site: {site_slug}")
    return None


  def get_all_devicenames(self):
    return [device["name"] for device in self.get_all_devices()]


  def get_device_resolve_hint(self):
    hints = {}
    for device in self.get_all_devices():
      hints[device["name"]] = device["id"]
    return hints


  def get_all_interfaces(self):
    self.all_interfaces = self.query("/dcim/interfaces/")
    return self.all_interfaces


  def get_all_device_interfaces(self, device_id):
    return self.query(f"/dcim/interfaces/?device_id={device_id}")


  def get_interface(self, iid):
    for interface in self.get_all_interfaces():
      if interface["id"] == iid:
        return interface


  def get_interface_resolve_hint(self, vc_mode=False):
    hints = {}
    for interface in self.get_all_interfaces():
      device_name = interface["device"]["name"]
      interface_name = interface["name"]

      if vc_mode:
        r_device_name = re.match("([\w|-]+) \((\d+)\)", device_name)
        if r_device_name is not None:
          device_name = r_device_name.group(1)
          chassis_n = int(r_device_name.group(2))
          if chassis_n > 1 and interface_name == "irb":
            continue

      key = device_name
      subkey = interface_name
      iid = interface["id"]
      try:
        hints[key][subkey] = iid
      except KeyError:
        hints[key] = {subkey: iid}
    return hints


  def get_mgmt_vlanid_resolve_hint(self, vc_mode=False):
    hints = {}
    for device in self.get_all_devices():
      device_name = device["name"]
      if vc_mode:
        r_device_name = re.match("([\w|-]+) \((\d+)\)", device_name)
        if r_device_name is not None:
          if int(r_device_name.group(2)) > 1:
            continue
          device_name = r_device_name.group(1)

      if device["device_role"]["slug"] != "edge-sw":
        continue

      area = self.lookup_sitegroup(device["site"]["slug"])
      if area in ["ookayama-n", "ookayama-w", "midorigaoka"]:
        hints[device_name] = 360
      elif area in ["ookayama-e", "ookayama-s", "ishikawadai", "tamachi"]:
        hints[device_name] = 361
      else:
        hints[device_name] = 362
    return hints


  def get_tokyotech_vlanid_resolve_hint(self, vc_mode=False):
    hints = {}
    for device in self.get_all_devices():
      device_name = device["name"]
      if vc_mode:
        r_device_name = re.match("([\w|-]+) \((\d+)\)", device_name)
        if r_device_name is not None:
          if int(r_device_name.group(2)) > 1:
            continue
          device_name = r_device_name.group(1)

      if device["device_role"]["slug"] != "edge-sw":
        continue

      region = self.lookup_region(device["site"]["slug"])
      if region in ["ookayama", "tamachi"]:
        hints[device_name] = 112
      else:
        hints[device_name] = 113
    return hints


  def get_all_vcs(self):
    return self.query("/dcim/virtual-chassis/")


  def get_all_vcnames(self):
    vcs = self.get_all_vcs()
    return [vc["name"] for vc in vcs]


  def get_vc_id_resolve_hint(self):
    hints = {}
    vcs = self.get_all_vcs()
    for vc in vcs:
      hints[vc["name"]] = vc["id"]
    return hints


  def create_vlans(self, vlans):
    existed_vids = self.get_all_vids()
    data = [
      {
        "vid": vid,
        "name": prop["name"],
        "status": "active",
        "description": prop["description"]
      }
      for vid, prop in vlans.items() if vid not in existed_vids
    ]
    data = list({v["vid"]:v for v in data}.values())
    if data:
      return self.query("/ipam/vlans/", data)
    return


  def create_sitegroups(self, sitegroups):
    existed_sitegroups = self.get_all_sitegroupslugs()
    data = [
      {
        "name": site["sitegroup_name"],
        "slug": site["sitegroup"]
      }
      for site in sitegroups if site["sitegroup"] not in existed_sitegroups
    ]
    data = list({v["slug"]:v for v in data}.values())
    if data:
      return self.query("/dcim/site-groups/", data)
    return


  def create_sites(self, sites):
    existed_sites = self.get_all_siteslugs()
    data = [
      {
        "name": site["site_name"],
        "slug": site["site"],
        "region": {"slug": site["region"]},
        "group": {"slug": site["sitegroup"]},
        "status": "active",
      }
      for site in sites if site["site"] not in existed_sites
    ]
    data = list({v["slug"]:v for v in data}.values())
    if data:
      return self.query("/dcim/sites/", data)
    return


  def create_vcs(self, devices, n_stacked):
    exist_vcs = self.get_all_vcnames()
    data = []
    for device in devices:
      device_name = device["name"]
      device_type = device["device_type"]
      if device_name in exist_vcs:
        continue
      is_vs = device_type in ["ex4300-48mp", "ex4300-32f"] and n_stacked[device_name] > 1
      is_special_vc = device_type in ["ex4300-48mp-32f", "ex4300-48mp-32f-st2"]
      if is_vs or is_special_vc:
        data.append({
          "name": device_name
        })
    if data:
      return self.query("/dcim/virtual-chassis/", data)


  def create_devices(self, devices, n_stacked):
    exist_devices = self.get_all_devicenames()
    data = []

    for device in devices:
      device_name = device["name"]
      device_type = device["device_type"]

      if device_name in exist_devices or f"{device_name} (1)" in exist_devices:
         continue

      # stacked use
      if device_type in ["ex4300-48mp", "ex4300-32f", "qfx5200-32c-32q", "c1000-24p"] and n_stacked[device_name] > 1:
        for n in range(1, n_stacked[device_name]+1):
          data.append({
            "name": f"{device_name} ({n})",
            "device_role": {"slug": "edge-sw"},
            "device_type": {"slug": device_type},
            "region": {"slug": device["region"]},
            "site": {"slug": device["site"]},
            "status": "active",
            "vc_position": n,
            "virtual_chassis": {
              "name": device_name,
            }
          })

      # stacked use (special)
      elif device_type == "ex4300-48mp-32f":
        data.append({
          "name": f"{device_name} (1)",
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": "ex4300-48mp"},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active",
          "vc_position": 1,
          "virtual_chassis": {
            "name": device_name
          }
        })
        data.append({
          "name": f"{device_name} (2)",
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": "ex4300-32f"},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active",
          "vc_position": 2,
          "virtual_chassis": {
            "name": device_name,
          }
        })

      # stacked use (special)
      elif device_type == "ex4300-48mp-32f-st2":
        data.append({
          "name": f"{device_name} (1)",
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": "ex4300-48mp"},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active",
          "vc_position": 1,
          "virtual_chassis": {
            "name": device_name,
          }
        })
        data.append({
          "name": f"{device_name} (2)",
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": "ex4300-32f"},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active",
          "vc_position": 2,
          "virtual_chassis": {
            "name": device_name,
          }
        })
        data.append({
          "name": f"{device_name} (3)",
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": "ex4300-32f"},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active",
          "vc_position": 3,
          "virtual_chassis": {
            "name": device_name,
          }
        })

      # single use
      else:
        data.append({
          "name": device_name,
          "device_role": {"slug": "edge-sw"},
          "device_type": {"slug": device_type},
          "region": {"slug": device["region"]},
          "site": {"slug": device["site"]},
          "status": "active"
        })

    data = list({v["name"]:v for v in data}.values())
    if data:
      return self.query("/dcim/devices/", data)
    return


  def update_vc_masters(self, devices, n_stacked):
    data = []
    vc_ids = self.get_vc_id_resolve_hint()
    for device in devices:
      device_name = device["name"]
      device_type = device["device_type"]
      is_vs = device_type in ["ex4300-48mp", "ex4300-32f", "c1000-24p", "qfx5200-32c-32q"] and n_stacked[device_name] > 1
      is_special_vc = device_type in ["ex4300-48mp-32f", "ex4300-48mp-32f-st2"]
      if is_vs or is_special_vc:
        data.append({
          "id": vc_ids[device_name],
          "master": {"name": f"{device_name} (1)"}
        })
    if data:
      return self.query("/dcim/virtual-chassis/", data, update=True)
    return


  def rename_interfaces(self):
    data = []

    for interface in self.get_all_interfaces():
      if_id = interface["id"]
      if_name = interface["name"]
      device_name = interface["device"]["name"]

      r_device_name = re.match("[\w|-]+ \((\d+)\)", device_name)
      r_if_name = re.match("([ge|mge|et]+)-\d+/(\d+/\d+)", if_name)

      if r_device_name is None or r_if_name is None:
        continue

      chassis_n = int(r_device_name.group(1)) - 1  # 0-based index (juniper rule)
      if_type = r_if_name.group(1)
      if_n = r_if_name.group(2)

      if chassis_n > 0:
        data.append({
          "id": if_id,
          "name": f"{if_type}-{chassis_n}/{if_n}"
        })

    if data:
      return self.query("/dcim/interfaces/", data, update=True)
    return


  def create_and_assign_device_ips(self, devices):
    existed_ips = self.get_all_ips()
    interface_hints = self.get_interface_resolve_hint()
    data = []

    for device in devices:
      if "/".join([device["ipv4"], device["cidr"]]) in existed_ips:
        continue

      device_name = device["name"]
      if device_name not in interface_hints:
        device_name = f"{device_name} (1)"
      irb_id = interface_hints[device_name]["irb"]

      data.append({
        "address": "/".join([device["ipv4"], device["cidr"]]),
        "status": "active",
        "dns_name": ".".join([device["name"], "m.noc.titech.ac.jp"]),
        "assigned_object_type": "dcim.interface",
        "assigned_object_id": irb_id,
        "assigned_object": {
          "id": irb_id
        },
      })

    if data:
      return self.query("/ipam/ip-addresses/", data)
    return


  def set_primary_device_ips(self, devices):
    ip_hints = self.get_ip_resolve_hint()
    device_hints = self.get_device_resolve_hint()
    data = []

    for device in devices:
      device_name = device["name"]
      if device_name not in device_hints:
        device_name = f"{device_name} (1)"
      data.append({
        "id": device_hints[device_name],
        "primary_ip4": ip_hints["/".join([device["ipv4"], device["cidr"]])],
      })

    if data:
      return self.query("/dcim/devices/", data, update=True)
    return


  def create_lag_interfaces(self, lags):
    interface_hints = self.get_interface_resolve_hint()
    data = []

    for hostname, device_lags in lags.items():
      if hostname not in interface_hints:
        hostname = f"{hostname} (1)"
      for ifname, _ in device_lags.items():
        if ifname in interface_hints[hostname].keys():
          continue
        req = {
          "device": {"name": hostname},
          "name": ifname,
          "type": "lag"
        }
        data.append(req)

    if data:
      return self.query("/dcim/interfaces/", data)
    return


  def disable_all_interfaces(self, devices):
    interface_hints = self.get_interface_resolve_hint()
    data = []
    for hostname in [v["name"] for v in devices]:
      if hostname not in interface_hints:
        hostname = f"{hostname} (1)"
      for ifname, iid in interface_hints[hostname].items():
        if ifname == "irb":
          continue
        req = {
          "id": iid,
          "enabled": False,
        }
        data.append(req)
    if data:
      return self.query("/dcim/interfaces/", data, update=True)


  def add_interface_descriptions(self, interfaces):
    interface_hints = self.get_interface_resolve_hint(vc_mode=True)
    data = []
    orphan_vlans = {}

    for hostname, device_interfaces in interfaces.items():
      orphan_vlans[hostname] = []
      for interface, props in device_interfaces.items():
        req = {
          "id": interface_hints[hostname][interface],
          "description": props["description"],
          "enabled": props["enabled"],
          "tags": [],
        }
        data.append(req)
    if data:
      pprint(data)
      #return self.query("/dcim/interfaces/", data, update=True)
    return


def __load_encrypted_secrets():
  with open(VAULT_FILE) as v, open(VAULT_PASSWORD_FILE, "r") as p:
    key = str.encode(p.read().rstrip())
    try:
      vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(key))])
      raw = vault.decrypt(v.read())
      return yaml.load(raw, Loader=yaml.CLoader)
    except AnsibleVaultError as e:
      print("Failed to decrypt the vault. Check your password and try again:", e, file=sys.stderr)
      sys.exit(1)


def migrate_edge(rule, tn4_hostname):
  tn4_interfaces = {}
  for tn4_port, rule_props in rule.items():
    tn4_interfaces[tn4_port] = {
      "description": rule_props["description"],
      "enabled":      rule_props["enabled"]
    }
  return tn4_interfaces


def migrate_all_edges(devices, tn3_stack_info, hosts=[]):
  tn4_all_interfaces = {}
  tn4_all_n_stacked = {}
  migration_rules = migration_rule_load(hosts=hosts)

  for device in devices:
    tn4_hostname = device["name"]
    if hosts and tn4_hostname not in hosts:
      continue
    tn3_hostname = device["tn3_name"]
    tn3_n_stacked = tn3_stack_info[tn3_hostname]
    rule = migration_rules[tn4_hostname]

    tn4_interfaces = migrate_edge(rule, tn4_hostname)
    tn4_all_interfaces[tn4_hostname] = tn4_interfaces
    tn4_all_n_stacked[tn4_hostname] = tn3_n_stacked
  return tn4_all_interfaces, tn4_all_n_stacked


def main():
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])

  vlans = vlan_load()
  devices = device_load(hosts=[])
  hosts = [d["name"] for d in devices]
  sitegroups = [{k: d[k] for k in ["sitegroup_name", "sitegroup"]} for d in devices]
  sites = [{k: d[k] for k in ["region", "sitegroup", "site_name", "site"]} for d in devices]

  #tn3_interfaces, tn3_n_stacked = chassis_interface_load()
  tn3_n_stacked = {
    "noc-gsic-1,2":   2,
    "noc-honkan-1,2": 2,
    "noc-setubi-1":   2,
    "10g-setsubi-1":  1,
    "10g-gsic-1":     2,
  }
  tn4_interfaces, tn4_n_stacked = migrate_all_edges(devices, tn3_n_stacked, hosts=hosts)
  #pprint(tn4_interfaces)
  #sys.exit(0)

  #print("STEP 1 of 12: Create VLANs")
  #res = nb.create_vlans(vlans)
  #if res:
  #  pprint(res)

  #print("STEP 2 of 12: Create site groups")
  #res = nb.create_sitegroups(sitegroups)
  #if res:
  #  pprint(res)

  #print("STEP 3 of 12: Create sites")
  #res = nb.create_sites(sites)
  #if res:
  #  pprint(res)

  #print("STEP 4 of 12: Create VC")
  #res = nb.create_vcs(devices, tn4_n_stacked)
  #if res:
  #  pprint(res)

  #print("STEP 5 of 12: Create devices")
  #res = nb.create_devices(devices, tn4_n_stacked)
  #if res:
  #  pprint(res)

  #print("STEP 6 of 12: Set VC master")
  #res = nb.update_vc_masters(devices, tn4_n_stacked)
  #if res:
  #  pprint(res)

  #print("STEP 7 of 12: Create IP Addresses")
  #res = nb.create_and_assign_device_ips(devices)
  #if res:
  #  pprint(res)

  #print("STEP 8 of 12: Update device addresses")
  #res = nb.set_primary_device_ips(devices)
  #if res:
  #  pprint(res)

  #print("STEP 9 of 12: Rename interfaces")
  #res = nb.rename_interfaces()
  #if res:
  #  pprint(res)

  print("STEP 10 of 12: Disable all interfaces")
  res = nb.disable_all_interfaces(devices)
  if res:
    pprint(res)

  print("STEP 11 of 12: Add interface descriptions")
  res = nb.add_interface_descriptions(tn4_interfaces)
  if res:
    pprint(res)


def develop():
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  pprint(nb.get_interface_resolve_hint(vc_mode=True))


if __name__ == "__main__":
    main()
    #develop()
