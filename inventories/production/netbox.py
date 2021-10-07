#!/usr/bin/env python3
# This file is part of Ansible.

from pprint import pprint
from datetime import datetime
import json
import os
import re
import requests
import sys
import yaml

from ansible.constants import DEFAULT_VAULT_ID_MATCH
from ansible.parsing.vault import VaultLib
from ansible.parsing.vault import VaultSecret
from ansible.parsing.vault import AnsibleVaultError

VAULT_FILE = os.path.join(os.path.dirname(__file__), "./group_vars/all/vault.yml")
VAULT_PASSWORD_FILE = os.path.join(os.path.dirname(__file__), "../../.secrets/vault-pass.txt")


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


def timestamp():
  n = datetime.now()
  return n.strftime("%Y-%m-%d@%H-%M-%S")


class NetBoxClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = netbox_url.rstrip("/") + "/api"
    self.token = netbox_api_token
    self.all_vlans = []
    self.all_devices = []
    self.all_interfaces = []


  def query(self, request_path):
    responses = []
    url = self.api_endpoint + request_path
    headers = {
      "Authorization": f"Token {self.token}",
      "Content-Type":  "application/json",
      "Accept":        "application/json; indent=4"
    }

    while url:
      raw = requests.get(url, headers=headers, verify=True)
      res = json.loads(raw.text)
      responses += res["results"]
      url = res["next"]
    return responses


  def get_all_vlans(self, use_cache=True):
    if not use_cache or not self.all_vlans:
      self.all_vlans = self.query("/ipam/vlans/")
    return self.all_vlans


  def get_all_devices(self, use_cache=True):
    if not use_cache or not self.all_devices:
      self.all_devices = self.query("/dcim/devices/")
    return self.all_devices


  def get_all_interfaces(self, use_cache=True):
    if not use_cache or not self.all_interfaces:
      self.all_interfaces = self.query("/dcim/interfaces/")
    return self.all_interfaces


class EdgeConfig:
  def __init__(self, netbox_cli):
    self.all_vlans = netbox_cli.get_all_vlans()
    self.all_devices = self.__filter_active_devices(netbox_cli.get_all_devices())
    self.all_interfaces = self.__group_by_device(netbox_cli.get_all_interfaces())


  def __regex_device_name(self, device_name):
    dev_name_reg = re.match("([\w|-]+) \((\d+)\)", device_name)
    is_stacked = dev_name_reg is not None
    is_vc_slave = is_stacked and int(dev_name_reg.group(2)) > 1
    basename = device_name
    if is_stacked:
      basename = dev_name_reg.group(1)
    return is_stacked, is_vc_slave, basename


  def __regex_interface_name(self, interface_name):
    is_mgmt_port = interface_name == "irb"
    is_upstream_port = interface_name == "ae0"
    is_qsfp_port = interface_name[:3] == "et-"
    is_lag_port = interface_name[:2] == "ae"
    return is_mgmt_port, is_upstream_port, is_qsfp_port, is_lag_port


  def __filter_active_devices(self, devices):
    filtered = []
    for dev in devices:
      is_inactive = dev["status"]["value"] != "active"
      has_ipaddr = dev["primary_ip"] is not None
      _, is_vc_slave, basename = self.__regex_device_name(dev["name"])
      if is_inactive or not has_ipaddr or is_vc_slave:
        continue
      dev["name"] = basename
      filtered.append(dev)
    return filtered


  def __group_by_device(self, interfaces):
    arranged = {}
    for interface in interfaces:
      _, _, basename = self.__regex_device_name(interface["device"]["name"])
      try:
        arranged[basename][interface["name"]] = interface
      except KeyError:
        arranged[basename] = {interface["name"]: interface}
    return arranged


  def get_vlans(self, hostname):
    vlans, vids = [], set()
    for prop in self.all_interfaces[hostname].values():
      for vlan in [prop["untagged_vlan"], *prop["tagged_vlans"]]:
        if vlan is not None:
          vids.add(vlan["vid"])
    for vid in vids:
      for vlan in self.all_vlans:
        if vlan["vid"] == vid:
          vlans.append({
            "name":        vlan["name"],
            "vid":         vlan["vid"],
            "description": vlan["description"],
          })
    return vlans


  def get_all_devices(self):
    return [d["name"] for d in self.all_devices if d["device_role"]["slug"] == "edge-sw"]


  def get_manufacturer(self, hostname):
    for d in self.all_devices:
      if d["name"] == hostname:
        return d["device_type"]["manufacturer"]["slug"]
    return None


  def get_ip_address(self, hostname):
    ip = lambda cidr: cidr.split("/")[0]
    for d in self.all_devices:
      if d["name"] == hostname:
        return ip(d["primary_ip"]["address"])


  def get_lag_members(self, hostname):
    lag_members = {}
    for ifname, prop in self.all_interfaces[hostname].items():
      is_mgmt_port, is_upstream_port, is_qsfp_port, is_lag_port = self.__regex_interface_name(ifname)
      is_lag_member_port = prop["lag"] is not None

      if is_mgmt_port or is_upstream_port or is_qsfp_port:
        continue

      if is_lag_port:
        if ifname not in lag_members.keys():
          lag_members[ifname] = []
      elif is_lag_member_port:
        try:
          lag_members[prop["lag"]["name"]].append(ifname)
        except KeyError:
          lag_members[prop["lag"]["name"]] = [ifname]

    return lag_members


  def get_interfaces(self, hostname):
    interfaces = {}
    for ifname, prop in self.all_interfaces[hostname].items():
      tags = [t["slug"] for t in prop["tags"]]
      is_mgmt_port, is_upstream_port, is_qsfp_port, is_lag_port = self.__regex_interface_name(ifname)
      is_poe_port = "poe" in tags

      if is_mgmt_port or is_upstream_port or is_qsfp_port:
        continue

      is_vlan_port = prop["mode"] is not None
      vlan_mode, native_vid, vids = None, None, []
      if is_vlan_port:
        vlan_mode = prop["mode"]["value"].lower()
        if vlan_mode == "access":
          vids = [prop["untagged_vlan"]["vid"]]
        elif vlan_mode == "tagged":
          vlan_mode = "trunk"  # Format conversion: from netbox to juniper/cisco style
          vids = [v["vid"] for v in prop["tagged_vlans"]]
          if prop["untagged_vlan"] is not None:
            native_vid = prop["untagged_vlan"]["vid"]
            vids.append(native_vid)

      interfaces[ifname] = {
        "physical":    not (is_mgmt_port or is_lag_port),
        "enabled":     prop["enabled"],
        "description": prop["description"],
        "poe":         is_poe_port,
        "auto_speed":  True,
        "mode":        vlan_mode,
        "vlans":       vids,
        "native":      native_vid,
      }

    return interfaces


if __name__ == "__main__":
  ts = timestamp()
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  cf = EdgeConfig(nb)

  print(json.dumps({
    hostname: {
      "hosts": [cf.get_ip_address(hostname)],
      "vars": {
        "hostname":     hostname,
        "datetime":     ts,
        "manufacturer": cf.get_manufacturer(hostname),
        "vlans":        cf.get_vlans(hostname),
        "interfaces":   cf.get_interfaces(hostname),
        "lag_members":  cf.get_lag_members(hostname),
      }
    }
    for hostname in cf.get_all_devices()
  }))
