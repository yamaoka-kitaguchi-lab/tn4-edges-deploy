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
  
  def create_vlans(self, vlans):
    existed_vids = self.get_all_vids()
    data = [
      {"vid": vid, "name": prop["name"], "status": "active", "description": prop["description"]}
      for vid, prop in vlans.items() if vid not in existed_vids
    ]
    print("[I] {} VLANs are newly created.".format(len(data)))
    return self.query("/ipam/vlans/", data)
    
  
  def create_devices(self, devices):
    pass


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


def main():
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  nb.create_vlans(vlan_load())


if __name__ == "__main__":
    main()
