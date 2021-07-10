#!/usr/bin/env python3
"""
Load VLANs from the output of `show configuration vlans | display set`
"""
import re
import sys
from pprint import pprint


def loader(path):
    vlans = {}
    with open(path) as fd:
        hits = re.findall("set vlans (\S+) (\S+) (\S+)", fd.read(), re.S)
        for r in hits:
            name, key, value = r
            if key not in ["vlan-id", "description"]:
                continue
            try:
                vlans[name][key] = value
            except KeyError:
                vlans[name] = {"description": ""}
                vlans[name][key] = value
    return {
        int(v["vlan-id"]): {"name": k, "description": v["description"]}
        for k, v in vlans.items()
    }


if __name__ == "__main__":
    filepath = sys.argv[1]
    pprint(loader(filepath))
