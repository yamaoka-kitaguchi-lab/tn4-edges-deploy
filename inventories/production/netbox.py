#!/usr/bin/env python3
# This file is part of Ansible.

from pprint import pprint
import os
import sys
import json
import yaml

import requests

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


class NetBoxClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = netbox_url.rstrip("/") + "/api"
    self.token = netbox_api_token

  def query(self, request_path):
    responses = []
    url = self.api_endpoint + request_path
    headers = {
      "Authorization": f"Token {self.token}",
      "Content-Type": "application/json",
      "Accept": "application/json; indent=4"
    }
    
    while url:
      raw = requests.get(url, headers=headers, verify=True)
      res = json.loads(raw.text)
      responses += res["results"]
      url = res["next"]
    return responses
  
  def get_all_vlans(self):
    return self.query("/ipam/vlans/")
  
  def get_all_devices(self):
    return self.query("/dcim/devices/")
  
  def get_all_interfaces(self):
    return self.query("/dcim/interfaces/")


class EdgeConfig:
  def __init__(self, netbox_cli):
    self.all_vlans = netbox_cli.get_all_vlans()
    self.all_devices = self.__grep_active_devices(netbox_cli.get_all_devices())
    self.all_interfaces = self.__group_by_device(netbox_cli.get_all_interfaces())
  
  def __grep_active_devices(self, devices):
    return [dev for dev in devices if dev["status"]["value"] == "active"]
  
  def __group_by_device(self, interfaces):
    arranged = {}
    for interface in interfaces:
      key = interface["device"]["name"]
      try:
        arranged[key][interface["name"]] = interface
      except KeyError:
        arranged[key] = {interface["name"]: interface}
    return arranged
  
  def get_vlans(self, hostname):
    vlans, vids = [], set()
    for prop in self.all_interfaces[hostname].values():
      for vlan in [prop["untagged_vlan"], *prop["tagged_vlans"]]:
        if vlan:
          vids.add(vlan["vid"])
    for vid in vids:
      for vlan in self.all_vlans:
        if vlan["vid"] == vid:
          vlans.append({
            "name": vlan["name"],
            "vid": vlan["vid"],
            "description": vlan["description"],
          })
    return vlans
  
  def get_all_devices(self):
    return [d["name"] for d in self.all_devices]
  
  def get_device_ip_address(self, hostname):
    for device in self.all_devices:
      if device["name"] != hostname:
        continue
      return device["primary_ip"]["address"].split("/")[0]
  
  def get_interfaces(self, hostname):
    interfaces = {}
    for ifname, prop in self.all_interfaces[hostname].items():
      if ifname == "irb":
        continue
      
      # Auto negotiate link speed on the interface whose description begins with "ap-" or "noc"
      speed = "1g"
      description = prop["description"]
      if description[:3] in ["ap-", "noc"]:
        speed = "auto"
      
      # Allow PoE for AP interface
      poe = False
      if description[:3] == "ap-":
        poe = True
      
      vlans = []
      mode = prop["mode"]  # "ACCESS" or "TAGGED", or None
      if mode:
        mode = mode["value"].upper()
      if mode == "ACCESS":
        vlans = [prop["untagged_vlan"]["vid"]]
      if mode == "TAGGED":
        vlans = [v["vid"] for v in prop["tagged_vlans"]]
      
      interfaces[ifname] = {
        "enabled": prop["enabled"],
        "description": description,
        "speed": speed,
        "poe": poe,
        "mode": mode,
        "vlans": vlans,
      }
    return interfaces


if __name__ == "__main__":
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  cf = EdgeConfig(nb)
  
  print(json.dumps({
    hostname: {
      "hosts": [cf.get_device_ip_address(hostname)],
      "vars": {
        "hostname": hostname,
        "vlans": cf.get_vlans(hostname),
        "interfaces": cf.get_interfaces(hostname),
      }
    }
    for hostname in cf.get_all_devices()
  }))
