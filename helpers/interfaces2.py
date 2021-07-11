#!/usr/bin/env python3
from pprint import pprint
import re
import os

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "./tn3/configs/")


def dirty_interfaces_parser(hostname):
  cf = []
  depth, l = 1, 0
  interfaces = {}
  
  def token(line):
    return line.lstrip().rstrip("{}; ").split()
  
  def enum_if_range(if_from, if_to):
    if_base = if_from.split("/")[:-1]
    port_from, port_to = int(if_from.split("/")[-1]), int(if_to.split("/")[-1])
    return [if_base + f"/{port}" for port in range(port_from, port_to+1)]
  
  def enum_vlan_members(members):
    vids = []
    for s in members.split():
      if "-" in s:
        a, b = s.split("-")
        vids += [vid for vid in range(int(a), int(b)+1)]
      vids.append(int(s))
    return vids
  
  with open(os.path.join(CONFIG_DIR, hostname)) as fd:
    cf = fd.read().split("\n")
  
  while l <= len(cf):
    if token(cf[l])[0] == "interfaces":
      break
    l += 1
  
  while l <= len(cf):
    if cf[l][-1] == "{":
      depth += 1
    if cf[l][-1] == "}":
      depth -= 1
    if depth == 0:
      break
    
    ifname = token(cf[l])[0]
    if ifname == "interface-range":
      interface_range = []
      common_props = {"enable": True}
      l += 1
      while depth > 1:
        if cf[l][-1] == "{":
          depth += 1
        if cf[l][-1] == "}":
          depth -= 1
        tk = token(cf[l])
        if tk[0] == "member-range":
          interface_range += enum_if_range(tk[1], tk[3])
        if tk[0] == "port-mode":
          common_props["mode"] = tk[1]
        if tk[0] == "members":
          common_props["vlan"] = enum_vlan_members(tk[1:].strip("[]"))
        if tk[0] == "description":
          common_props["description"] = tk[1]
        if tk[0] == "disable":
          common_props["enable"] = False
        l += 1
      for interface in interface_range:
        interfaces[interface] = common_props
    if ifname != "":
      interfaces[ifname] = {"enable": True}
      l += 1
      while depth > 1:
        if cf[l][-1] == "{":
          depth += 1
        if cf[l][-1] == "}":
          depth -= 1
        tk = token(cf[l])
        if tk[0] == "port-mode":
          interfaces[ifname]["mode"] = tk[1]
        if tk[0] == "members":
          interfaces[ifname]["vlan"] = enum_vlan_members(tk[1:].strip("[]"))
        if tk[0] == "description":
          interfaces[ifname]["description"] = tk[1]
        if tk[0] == "disable":
          interfaces[ifname]["enable"] = False
        l += 1
    
  return interfaces


if __name__ == "__main__":
  pprint(dirty_interfaces_parser("minami3-1"))