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

from migrate import migrater
from devices import load as device_load
from vlans import load as vlan_load
from interfaces import load as interface_load

VAULT_FILE = os.path.join(os.path.dirname(__file__), "../inventories/production/group_vars/all/vault.yml")
VAULT_PASSWORD_FILE = os.path.join(os.path.dirname(__file__), "../.secrets/vault-pass.txt")


class NetBoxClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = netbox_url.rstrip("/") + "/api"
    self.token = netbox_api_token

  def query(self, request_path, data=None):
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
    if data:
      print("[I] {} VLANs are newly created.".format(len(data)))
      return self.query("/ipam/vlans/", data)
    print("[I] Skip to create VLAN.")
    return

  def create_sites(self, sites):
    existed_sites = self.get_all_siteslugs()
    data = [
      {
        "name": site["name"],
        "slug": site["slug"],
        "status": "active",
      }
      for site in sites if site["slug"] not in existed_sites
    ]
    if data:
      print("[I] {} sites are newly created.".format(len(data)))
      return self.query("/dcim/sites/", data)
    print("[I] Skip to create site.")
    return
  
  def create_devices(self, devices):
    existed_devices = self.get_all_devicenames()
    data = [
      {
        "name": device["name"],
        "device_role": "edge-sw",
        "device_type": device["type"]["slug"],
        "site": device["site"]["slug"],
        "status": "active"
      }
      for device in devices if device["name"] not in existed_devices
    ]
    if data:
      print("[I] {} devices are newly created.".format(len(data)))
      return self.query("/dcim/devices/", data)
    print("[I] Skip to create device.")
    return
  
  def create_vc(self):
    pass


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


def main():
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  #nb.create_vlans(vlan_load())
  #nb.create_devices(device_load())
  nb.create_sites(None)


if __name__ == "__main__":
    main()
