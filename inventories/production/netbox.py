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


class NetBoxClient:
  def __init__(self, netbox_url, netbox_api_token):
    self.api_endpoint = netbox_url.rstrip("/") + "/api"
    self.token = netbox_api_token
    self.all_sites = []
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


  def get_all_sites(self, use_cache=True):
    if not use_cache or not self.all_sites:
      self.all_sites = self.query("/dcim/sites/")
    return self.all_sites


  def get_all_vlans(self, use_cache=True):
    if not use_cache or not self.all_vlans:
      self.all_vlans = self.query("/ipam/vlans/")
      for vlan in self.all_vlans:
        vlan["tags"] = [tag["slug"] for tag in vlan["tags"]]
    return self.all_vlans


  def get_all_devices(self, use_cache=True):
    if not use_cache or not self.all_devices:
      self.all_devices = self.query("/dcim/devices/")
      for device in self.all_devices:
        device["tags"] = [tag["slug"] for tag in device["tags"]]
    return self.all_devices


  def get_all_interfaces(self, use_cache=True):
    if not use_cache or not self.all_interfaces:
      self.all_interfaces = self.query("/dcim/interfaces/")
      for interface in self.all_interfaces:
        interface["tags"] = [tag["slug"] for tag in interface["tags"]]
    return self.all_interfaces


class DevConfig:
  VLAN_GROUP                = "titanet"
  DEV_ROLE_EDGE             = "edge-sw"
  DEV_ROLE_CORE             = "core-sw"
  REGION_OOKAYAMA           = "ookayama"
  REGION_SUZUKAKE           = "suzukake"
  REGION_TAMACHI            = "tamachi"
  TAG_MGMT_EDGE_OOKAYAMA    = "mgmt-vlan-eo"
  TAG_MGMT_EDGE_SUZUKAKE    = "mgmt-vlan-es"
  TAG_MGMT_CORE_OOKAYAMA    = "mgmt-vlan-co"
  TAG_MGMT_CORE_SUZUKAKE    = "mgmt-vlan-cs"
  TAG_MCLAG_MASTER          = "mclag-master-core"
  TAG_MCLAG_MASTER_OOKAYAMA = "mclag-master-co"
  TAG_MCLAG_MASTER_SUZUKAKE = "mclag-master-cs"
  TAG_MCLAG_SLAVE           = "mclag-slave-core"
  TAG_MCLAG_SLAVE_OOKAYAMA  = "mclag-slave-co"
  TAG_MCLAG_SLAVE_SUZUKAKE  = "mclag-slave-cs"
  TAG_ANSIBLE               = "ansible"
  TAG_PROTECT               = "protect"
  TAG_UPLINK                = "uplink"
  TAG_POE                   = "poe"


  def __init__(self, netbox_cli):
    self.all_sites = netbox_cli.get_all_sites()
    self.all_vlans = self.__filter_vlan_group(netbox_cli.get_all_vlans())
    self.all_devices = self.__filter_active_devices(netbox_cli.get_all_devices())
    self.all_interfaces = self.__group_by_device(netbox_cli.get_all_interfaces())
    self.__all_core_mclag_interfaces = None  # cache


  def __regex_device_name(self, device_name):
    dev_name_reg = re.match("([\w|-]+) \((\d+)\)", device_name)
    is_stacked = dev_name_reg is not None
    is_vc_slave = is_stacked and int(dev_name_reg.group(2)) > 1
    basename = device_name
    if is_stacked:
      basename = dev_name_reg.group(1)
    return is_stacked, is_vc_slave, basename


  def __regex_interface_name(self, interface_name):
    is_qsfp_port = interface_name[:3] == "et-"
    is_lag_port = interface_name[:2] == "ae" or interface_name[:12] == "Port-channel"
    return is_qsfp_port, is_lag_port


  def __filter_vlan_group(self, vlans):
    filtered = []
    for vlan in vlans:
      if vlan["group"] is None:
        continue
      if vlan["group"]["slug"] == DevConfig.VLAN_GROUP:
        filtered.append(vlan)
    return filtered


  def __filter_active_vc_masters(self, devices):
    filtered = []
    vc_masters = {}
    are_all_active = {}

    for dev in devices:
      is_active = dev["status"]["value"] == "active"
      has_ansible_tag = DevConfig.TAG_ANSIBLE in dev["tags"]
      is_stacked, is_vc_slave, basename = self.__regex_device_name(dev["name"])

      if is_stacked:
        try:
          are_all_active[basename] &= has_ansible_tag and is_active
        except KeyError:
          are_all_active[basename] = has_ansible_tag and is_active
        if not is_vc_slave:
          vc_masters[basename] = dev

    for basename in [n for n, c in are_all_active.items() if c]:
      filtered.append(vc_masters[basename])

    return filtered


  def __filter_active_devices(self, devices):
    filtered = []
    stacked_devices = self.__filter_active_vc_masters(devices)
    unstacked_devices = []

    for dev in devices:
      is_stacked, _, _ = self.__regex_device_name(dev["name"])
      if not is_stacked:
        unstacked_devices.append(dev)

    for dev in [*stacked_devices, *unstacked_devices]:
      is_active = dev["status"]["value"] == "active"
      has_ansible_tag = DevConfig.TAG_ANSIBLE in dev["tags"]
      has_ipaddr = dev["primary_ip"] is not None
      _, _, basename = self.__regex_device_name(dev["name"])

      if is_active and has_ansible_tag and has_ipaddr and not is_stacked:
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


  def __get_vlan_name(self, vid):
    for vlan in self.all_vlans:
      if vlan["vid"] == vid:
        return vlan["name"]
    return None


  def get_region(self, site):
    for s in self.all_sites:
      if s["slug"] == site:
        return s["region"]["slug"]
    return None


  def get_vlans(self, hostname):
    vlans, vids, irb_vids = [], set(), set()
    for ifname, prop in self.all_interfaces[hostname].items():
      is_irb_port = ifname[:4] == "irb."
      for vlan in [prop["untagged_vlan"], *prop["tagged_vlans"]]:
        if vlan is not None:
          vids.add(vlan["vid"])
        if is_irb_port:
          irb_vids.add(vlan["vid"])

    for vid in vids:
      for vlan in self.all_vlans:
        is_in_use_vlan = vlan["vid"] == vid
        is_protected_vlan = "protect" in vlan["tags"]
        is_irb_vlan = vlan["vid"] in irb_vids
        if is_in_use_vlan or is_protected_vlan:
          vlans.append({
            "name":        vlan["name"],
            "vid":         vlan["vid"],
            "irb":         is_irb_vlan,
            "used":        is_in_use_vlan,
            "protected":   is_protected_vlan,
            "description": vlan["description"],
          })
    return vlans


  def get_mgmt_vlan(self, device_role, region):
    mgmt_vlan_tags = {
      DevConfig.REGION_OOKAYAMA: {
        DevConfig.DEV_ROLE_EDGE: DevConfig.TAG_MGMT_EDGE_OOKAYAMA,
        DevConfig.DEV_ROLE_CORE: DevConfig.TAG_MGMT_CORE_OOKAYAMA,
      },
      DevConfig.REGION_TAMACHI: {
        DevConfig.DEV_ROLE_EDGE: DevConfig.TAG_MGMT_EDGE_OOKAYAMA,
        DevConfig.DEV_ROLE_CORE: DevConfig.TAG_MGMT_CORE_OOKAYAMA,
      },
      DevConfig.REGION_SUZUKAKE: {
        DevConfig.DEV_ROLE_EDGE: DevConfig.TAG_MGMT_EDGE_SUZUKAKE,
        DevConfig.DEV_ROLE_CORE: DevConfig.TAG_MGMT_CORE_SUZUKAKE,
      },
    }

    for vlan in self.all_vlans:
      if mgmt_vlan_tags[region][device_role] in vlan["tags"]:
        return {
          "name":        vlan["name"],
          "vid":         vlan["vid"],
          "description": vlan["description"],
        }
    return None


  def get_all_devices(self):
    return [{
      "hostname": d["name"],
      "role":     d["device_role"]["slug"],
      "region":   self.get_region(d["site"]["slug"]),
    } for d in self.all_devices]


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
      _, is_lag_port = self.__regex_interface_name(ifname)
      is_lag_member_port = prop["lag"] is not None
      is_upstream_port = DevConfig.TAG_UPLINK in prop["tags"]

      if is_upstream_port:
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

    ## See: https://github.com/netbox-community/netbox/blob/develop/netbox/dcim/choices.py#L688-L923
    iftypes_virtual = ["lag"]  # Ignore virtual type interfaces
    iftypes_ethernet = [
      "100base-tx", "1000base-t", "1000base-x-gbic", "1000base-x-sfp", "2.5gbase-t", "5gbase-t",
      "10gbase-t", "10gbase-cx4", "10gbase-x-sfpp", "10gbase-x-xfp", "10gbase-x-xenpak", "10gbase-x-x2",
      "25gbase-x-sfp28", "40gbase-x-qsfpp", "50gbase-x-sfp28", "100gbase-x-cfp", "100gbase-x-cfp2", "100gbase-x-cfp4",
      "100gbase-x-cpak", "100gbase-x-qsfp28", "200gbase-x-cfp2", "200gbase-x-qsfp56", "400gbase-x-qsfpdd", "400gbase-x-osfp",
    ]

    for ifname, prop in self.all_interfaces[hostname].items():
      is_deploy_port = prop["type"]["value"] in [*iftypes_virtual, *iftypes_ethernet]
      _, is_lag_port = self.__regex_interface_name(ifname)
      is_lag_member_port = prop["lag"] is not None
      is_upstream_port = DevConfig.TAG_UPLINK in prop["tags"]
      is_poe_port = DevConfig.TAG_POE in prop["tags"]

      if not is_deploy_port:
        continue

      description = prop["description"]
      is_vlan_port = prop["mode"] is not None
      vlan_mode, native_vid, vids, is_trunk_all = None, None, [], False

      if is_upstream_port:
        vlan_mode = "trunk"
        is_trunk_all = True

      elif is_vlan_port:
        vlan_mode = prop["mode"]["value"].lower()
        has_untagged_vid = prop["untagged_vlan"] is not None
        has_tagged_vid = prop["tagged_vlans"] is not None

        if vlan_mode == "access":
          if has_untagged_vid:
            vid = prop["untagged_vlan"]["vid"]
            vids = [vid]
            vlan_name = self.__get_vlan_name(vid)
            if description == "" and vlan_name is not None:
              description = vlan_name

        elif vlan_mode == "tagged":
          vlan_mode = "trunk"  # Format conversion: from netbox to juniper/cisco style
          if has_tagged_vid:
            vids = [v["vid"] for v in prop["tagged_vlans"]]
          if has_untagged_vid:
            native_vid = prop["untagged_vlan"]["vid"]
            vids.append(native_vid)

        elif vlan_mode == "tagged-all":
          vlan_mode = "trunk"
          is_trunk_all = True

      ## Cisco
      removed_vids = [vid for vid in range(1,4095) if vid not in vids]
      removed_vids_packed = [removed_vids[i:i+20] for i in range(0, len(removed_vids), 20)]

      interfaces[ifname] = {
        "physical":     not is_lag_port,
        "enabled":      prop["enabled"] or is_upstream_port,
        "description":  description,
        "lag_member":   is_lag_member_port,
        "poe":          is_poe_port,
        "auto_speed":   True,
        "vlan_mode":    vlan_mode,
        "vids":         vids,
        "removed_vids": removed_vids_packed,
        "native_vid":   native_vid,
        "trunk_all":    is_trunk_all,
      }

    return interfaces


  ## ToDo: need refactoring but soon to be obsoleted
  def get_core_mclag_interfaces(self, hostname):
    if self.__all_core_mclag_interfaces is not None:
      try:
        return self.__all_core_mclag_interfaces[hostname]
      except KeyError:
        return {}
    self.__all_core_mclag_interfaces = {}

    def has_tag(prop, *tags):
      for tag in tags:
        if tag in prop["tags"]:
          return True
      return False

    is_core = lambda d: d["device_role"]["slug"] == DevConfig.DEV_ROLE_CORE
    core_hostnames = [d["name"] for d in self.all_devices if is_core(d)]
    migrate_keys = ["enabled", "mode", "tagged_vlans", "untagged_vlan", "description"]
    masters, masters_o, masters_s = {}, {}, {}

    for hname in core_hostnames:
      for ifname, prop in self.all_interfaces[hname].items():
        is_lag_parent = prop["type"]["value"] == "lag"
        if not is_lag_parent:
          continue

        master_prop = {key: prop[key] for key in migrate_keys}
        if has_tag(prop, DevConfig.TAG_MCLAG_MASTER):
          masters[ifname] = master_prop
        elif has_tag(prop, DevConfig.TAG_MCLAG_MASTER_OOKAYAMA):
          masters_o[ifname] = master_prop
        elif has_tag(prop, DevConfig.TAG_MCLAG_MASTER_SUZUKAKE):
          masters_s[ifname] = master_prop

    for hname in core_hostnames:
      for ifname, prop in self.all_interfaces[hname].items():
        is_lag_parent = prop["type"]["value"] == "lag"
        if not is_lag_parent:
          continue

        try:
          master_prop = None
          if has_tag(prop, DevConfig.TAG_MCLAG_SLAVE, DevConfig.TAG_MCLAG_MASTER):
            master_prop = masters[ifname]
          elif has_tag(prop, DevConfig.TAG_MCLAG_SLAVE_OOKAYAMA, DevConfig.TAG_MCLAG_MASTER_OOKAYAMA):
            master_prop = masters_o[ifname]
          elif has_tag(prop, DevConfig.TAG_MCLAG_SLAVE_SUZUKAKE, DevConfig.TAG_MCLAG_MASTER_SUZUKAKE):
            master_prop = masters_s[ifname]
          else:
            continue
        except KeyError:
          continue

        is_vlan_port = master_prop["mode"] is not None
        vlan_mode, native_vid, vids, is_trunk_all = None, None, [], False
        if is_vlan_port:
          vlan_mode = master_prop["mode"]["value"].lower()
          has_untagged_vid = master_prop["untagged_vlan"] is not None
          has_tagged_vid = master_prop["tagged_vlans"] is not None

          if vlan_mode == "access":
            if has_untagged_vid:
              vid = master_prop["untagged_vlan"]["vid"]
              vids = [vid]

          elif vlan_mode == "tagged":
            vlan_mode = "trunk"  # Format conversion: from netbox to juniper/cisco style
            if has_tagged_vid:
              vids = [v["vid"] for v in master_prop["tagged_vlans"]]
            if has_untagged_vid:
              native_vid = master_prop["untagged_vlan"]["vid"]
              vids.append(native_vid)

          elif vlan_mode == "tagged-all":
            vlan_mode = "trunk"
            is_trunk_all = True

        prop = {
          "enabled":     master_prop["enabled"],
          "description": master_prop["description"],
          "vlan_mode":   vlan_mode,
          "vids":        vids,
          "native_vid":  native_vid,
          "trunk_all":   is_trunk_all,
        }

        try:
          self.__all_core_mclag_interfaces[hname][ifname] = prop
        except KeyError:
          self.__all_core_mclag_interfaces[hname] = {ifname: prop}

    return self.__all_core_mclag_interfaces[hostname]


  def get_device_interfaces(self, role, hostname):
    interfaces = self.get_interfaces(hostname)
    if role == DevConfig.DEV_ROLE_CORE:
      mlag = self.get_core_mclag_interfaces(hostname)
      interfaces.update(mlag)
    return interfaces


  ## CAUTION: hardcoded hostnames
  def get_device_vlans(self, hostname):
    vlans = self.get_vlans(hostname)
    uniq_vlans = []
    if hostname in ["core-gsic", "core-honkan", "core-si", "core-s7"]:
      vlans.extend(self.get_vlans("core-honkan"))
      vlans.extend(self.get_vlans("core-gsic"))
      vlans.extend(self.get_vlans("core-si"))
      vlans.extend(self.get_vlans("core-s7"))
    for vlan in vlans:
      if vlan not in uniq_vlans:
        uniq_vlans.append(vlan)
    return uniq_vlans


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


def dynamic_inventory():
  ts = timestamp()
  secrets = __load_encrypted_secrets()
  nb = NetBoxClient(secrets["netbox_url"], secrets["netbox_api_token"])
  cf = DevConfig(nb)

  devices = cf.get_all_devices()
  inventory = {
    "_meta": {
      "hostvars": {}
    }
  }

  for device in devices:
    hostname = device["hostname"]
    role = device["role"]
    group = role.upper()
    try:
      inventory[group]["hosts"].append(hostname)
    except KeyError:
      inventory[group] = {"hosts": [hostname]}

    inventory["_meta"]["hostvars"][hostname] = {
      "hostname":     hostname,
      "region":       device["region"],
      "manufacturer": cf.get_manufacturer(hostname),
      "vlans":        cf.get_device_vlans(hostname),
      "mgmt_vlan":    cf.get_mgmt_vlan(role, device["region"]),
      "interfaces":   cf.get_device_interfaces(role, hostname),
      "lag_members":  cf.get_lag_members(hostname),
      "ansible_host": cf.get_ip_address(hostname),
      "datetime":     ts,
    }

  return inventory


if __name__ == "__main__":
  inventory = dynamic_inventory()
  print(json.dumps(inventory))

  ## for deadman
  #for hostname, props in inventory["_meta"]["hostvars"].items():
  #  print(hostname, props["ansible_host"])
