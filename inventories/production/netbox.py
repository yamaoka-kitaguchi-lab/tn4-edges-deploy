#!/usr/bin/env python3
# This file is part of Ansible

from pprint import pprint
from datetime import datetime as dt
from datetime import timezone as tz
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


VAULT_FILE = os.path.join(os.path.dirname(__file__), "./group_vars/all/vault.yml")
VAULT_PASSWORD_FILE = os.path.join(os.path.dirname(__file__), "../../.secrets/vault-pass.txt")
TIMESTAMP_FILE = os.path.join(os.path.dirname(__file__), "../../.ts-last-update")


class NetBoxAPIClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = "{}/api".format(netbox_url.rstrip("/"))
    self.token = netbox_api_token

  def query(self, request_path):
    headers = {
      "Authorization": "Token {}".format(self.token),
      "Content-Type": "application/json"
    }
    responses = []
    url = self.api_endpoint + request_path
    while url:
      raw = requests.get(url, headers=headers, verify=True)
      res = json.loads(raw.text)
      responses += res["results"]
      url = res["next"]
    return responses

  def search_prefixes(self, **filters):
    path = "/ipam/prefixes/?" + urlencode(filters)
    return self.query(path)

  def search_addresses(self, **filters):
    path = "/ipam/ip-addresses/?" + urlencode(filters)
    return self.query(path)


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


def lastupdate():
  try:
    with open(TIMESTAMP_FILE, "r") as fd:
      return dt.fromisoformat(fd.read().rstrip())
  except (FileNotFoundError, ValueError):
    return dt.now(tz.utc)


def tun_name(prefix):
  # Conversion rule: tunX <-> 2001:200:e20:X0::/60
  # This scheme ensures the interface name to be unique among all sites.
  idx = prefix.split(":")[3][:1]
  return "tun{}".format(idx)


def fqdn(prefix):
  return "{}-ce.access.vsix.wide.ad.jp".format(tun_name(prefix))


def __load_delegated_prefixes(nb, filter_active):
  keys = ["prefix", "description", "created", "last_updated"]
  slugkeys = ["site"]
  delegated = []
  filters = {"role": "prefix-delegation"}
  if filter_active:
    filters["status"] = "active"
  details = nb.search_prefixes(**filters)
  for detail in details:
    delegated.append({
      **{k: detail[k] for k in keys},
      **{k: detail[k]["slug"] for k in slugkeys}
    })
  return delegated


def __load_ce_endpoint_addr(nb, prefix):
  addrs = nb.search_addresses(dns_name=fqdn(prefix))
  if len(addrs) != 1:
    return
  return addrs[0]["address"].split("/")[0]


def load_customers(nb, last_updated, filter_active=True):
  '''
  Returns the customer information gathered from NetBox as a list of dictionaries.

  Parameters:
    nb:            Instance object of the class NetboxAPIClient
    last_update:   Datetime object indicating the last update timestamp
    filter_active: Set true to exclude prefixes other than Status=Active

  Note:
    - Assume that NetBox returns the UTC timestamp

  Example output:
    [{'ce_address': '2405:6581:800:6c10:dea6:32ff:fead:e5a6',
      'created': '2021-06-06',
      'description': 'miya <miya@net.ict.e.titech.ac.jp>',
      'kea_delegated_len': '60',
      'kea_prefix': '2001:200:e20:20::',
      'kea_prefix_len': '60',
      'kea_subnet': '2001:200:e20:20::/60',
      'last_updated': '2021-06-15T12:54:10.346082Z',
      'prefix': '2001:200:e20:20::/60',
      'reattach': True,
      'site': 'kote',
      'tunnel': 'tun2'}]
  '''

  all_customers = __load_delegated_prefixes(nb, filter_active)
  for customer in all_customers:
    customer["tunnel"] = tun_name(customer["prefix"])
    customer["ce_address"] = __load_ce_endpoint_addr(nb, customer["prefix"])
    customer["kea_subnet"] = customer["prefix"]
    customer["kea_prefix"] = customer["prefix"].split("/")[0]
    customer["kea_prefix_len"] = customer["prefix"].split("/")[1]
    customer["kea_delegated_len"] = customer["kea_prefix_len"]
    tunnel_last_updated = customer["last_updated"].split(".")[0] + "+00:00"
    customer["reattach"] = last_updated < dt.fromisoformat(tunnel_last_updated)
  customers = [c for c in all_customers if c["ce_address"] is not None]
  #pprint(customers)
  return customers


def main():
  secrets = __load_encrypted_secrets()
  nb = NetBoxAPIClient(secrets["netbox_url"], secrets["netbox_api_token"])
  customers = load_customers(nb, lastupdate())
  
  # For every entry, the host group name in Ansible and the site name in NetBox must match.
  sites = ["kote", "note", "fujisawa"]
  print(json.dumps({
    s: {"vars": {"customers":
         [c for c in customers if c["site"] in [s, "vsix-global"]]
       }} for s in sites
  }))


if __name__ == "__main__":
  main()
