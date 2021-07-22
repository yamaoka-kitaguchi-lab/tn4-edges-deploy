#!/usr/bin/env python3
"""
Load VLANs from the output of `show configuration vlans | display set`
"""
from pprint import pprint
import os
import re

VLANTXT_PATH = os.path.join(os.path.dirname(__file__), "./tn3/vlans/core-o1.vlan.txt")


def load(path=VLANTXT_PATH):
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
        int(v["vlan-id"]): {
            "name": k,
            "description": v["description"]
        }
        for k, v in vlans.items()
    }


if __name__ == "__main__":
    pprint(load())
