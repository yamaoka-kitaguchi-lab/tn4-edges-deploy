#!/usr/bin/env python3
from pprint import pprint
import os
import sys
import json
import yaml

from urllib.parse import urlencode
import requests

from ansible.constants import DEFAULT_VAULT_ID_MATCH
from ansible.parsing.vault import VaultLib
from ansible.parsing.vault import VaultSecret
from ansible.parsing.vault import AnsibleVaultError

from migrate import make_port_converter
from devices import load as device_load
from vlans import load as vlan_load
from interfaces import load_interfaces as interface_load

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
  
  def get_all_sitegroups(self):
    return self.query("/dcim/site-groups/")
  
  def get_all_sitegroupslugs(self):
    sitegroups = self.get_all_sitegroups()
    return [sitegroup["slug"] for sitegroup in sitegroups]
  
  def get_all_sites(self):
    return self.query("/dcim/sites/")
  
  def get_all_siteslugs(self):
    sites = self.get_all_sites()
    return [site["slug"] for site in sites]
  
  def get_all_devices(self):
    return self.query("/dcim/devices/")
  
  def get_all_devicenames(self):
    devices = self.get_all_devices()
    return [device["name"] for device in devices]
  
  def get_all_interfaces(self):
    return self.query("/dcim/interfaces/")
  
  def get_interface_resolve_hint(self):
    hints = {}
    for interface in self.get_all_interfaces():
      key = interface["device"]["name"]
      subkey = interface["name"]
      iid = interface["id"]
      try:
        hints[key][subkey] = iid
      except KeyError:
        hints[key] = {subkey: iid}
    return hints
  
  def get_all_vcs(self):
    return self.query("/dcim/virtual-chassis/")
  
  def get_all_vcnames(self):
    vcs = self.get_all_vcs()
    pprint(vcs)
    return [vc["name"] for vc in vcs]
  
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

  def create_devices(self, devices):
    existed_devices = self.get_all_devicenames()
    data = [
      {
        "name": device["name"],
        "device_role": {"slug": "edge-sw"},
        "device_type": {"slug": device["device_type"]},
        "region": {"slug": device["region"]},
        "site": {"slug": device["site"]},
        "status": "active"
      }
      for device in devices if device["name"] not in existed_devices
    ]
    data = list({v["name"]:v for v in data}.values())
    if data:
      return self.query("/dcim/devices/", data)
    return

  def disable_all_interfaces(self, devices):
    interface_hints = self.get_interface_resolve_hint()
    data = []
    for hostname in [v["name"] for v in devices]:
      for iid in interface_hints[hostname].values():
        req = {
          "id": iid,
          "enabled": False,
        }
        data.append(req)
    if data:
      return self.query("/dcim/interfaces/", data, update=True)

  def update_interfaces(self, interfaces):
    interface_hints = self.get_interface_resolve_hint()
    vlan_resolver = self.make_vlan_resolver()
    data = []
    for hostname, device_interfaces in interfaces.items():
      orphan_vlans = []
      for interface, props in device_interfaces.items():
        if props["mode"] == "NONE":
          continue
        req = {
          "id": interface_hints[hostname][interface],
          "enabled": True,
          "description": props["description"]
        }
        if props["mode"] == "ACCESS":
          vid = vlan_resolver(props["untagged"])  # Convert VLAN ID to NetBox VLAN UNIQUE ID
          if vid is None:
            orphan_vlans.append(props["untagged"])
          req["mode"] = "access"
          req["untagged_vlan"] = vid
        if props["mode"] == "TRUNK":
          vids = []
          for vlanid in props["tagged"]:
            vid = vlan_resolver(vlanid)
            if vid is None:
              orphan_vlans.append(vlanid)
            else:
              vids.append(vid)
          req["mode"] = "tagged"
          req["tagged_vlans"] = vids
        data.append(req)
      if orphan_vlans:
        with open(f"orphan-vlans.json", "w") as fd:
          json.dump({hostname: orphan_vlans}, fd, indent=2)
    if data:
      return self.query("/dcim/interfaces/", data, update=True)
    return


def __load_encrypted_secrets():
  with open(VAULT_FILE) as v, open(VAULT_PASSWORD_FILE, "r") as p:
    key = str.encode(p.read().rstrip())
    try:
      vault = VaultLib([(DEFAULT_VAULT_ID_MATCH, VaultSecret(key))])
      raw = vault.decrypt(v.read())
      return yaml.load(raw, Loader=yaml.CLoader)
    except AnsibleVaultError as e:
      print("[E] Failed to decrypt the vault. Check your password and try again:", e, file=sys.stderr)
      sys.exit(1)


def migrate_edge(tn4_hostname, tn3_interfaces):
  port_converter = make_port_converter(tn4_hostname)
  tn4_interfaces = {}
  for tn3_port, props in tn3_interfaces.items():
    tn4_port = port_converter(tn3_port)
    tn4_interfaces[tn4_port] = props
  return tn4_interfaces


def migrate_all_edges(devices, tn3_all_interfaces, hosts=[]):
  tn4_all_interfaces = {}
  for device in devices:
    tn4_hostname = device["name"]
    if hosts and tn4_hostname not in hosts:
      continue
    tn3_hostname = tn4_hostname + "-1"  # Hostname conversion rule
    tn3_interfaces = tn3_all_interfaces[tn3_hostname]
    tn4_all_interfaces[tn4_hostname] = migrate_edge(tn4_hostname, tn3_interfaces)
  return tn4_all_interfaces


def main():
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  
  vlans = vlan_load()
  devices = device_load()
  sitegroups = [{k: d[k] for k in ["sitegroup_name", "sitegroup"]} for d in devices]
  sites = [{k: d[k] for k in ["region", "sitegroup", "site_name", "site"]} for d in devices]
  tn3_interfaces = interface_load()
  tn4_interfaces = migrate_all_edges(devices, tn3_interfaces, hosts=["minami3"])
  
  res = nb.create_vlans(vlans)
  if res:
    pprint(res)
  
  res = nb.create_sitegroups(sitegroups)
  if res:
    pprint(res)

  res = nb.create_sites(sites)
  if res:
    pprint(res)

  res = nb.create_devices(devices)
  if res:
    pprint(res)
  
  res = nb.disable_all_interfaces(devices)
  if res:
    pprint(res)

  res = nb.update_interfaces(tn4_interfaces)
  if res:
    pprint(res)


if __name__ == "__main__":
    main()
