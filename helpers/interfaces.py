#!/usr/bin/env python3
from pybatfish.client.commands import *
from pybatfish.question import bfq
from pybatfish.question.question import load_questions
from pprint import pprint
import os

SNAPSHOT_PATH = os.path.join(os.path.curdir, "./tn3")


def group_by_node(props, key="Node", subkey="name"):
    by_node = {}
    for prop in props:
        node = prop[key][subkey]
        try:
            by_node[node].append(prop)
        except KeyError:
            by_node[node] = [prop]
    return by_node


def load(if_type="ge"):
    load_questions()
    bf_init_snapshot(SNAPSHOT_PATH)
    
    q1 = bfq.interfaceProperties(
            interfaces=f"/{if_type}-[0,1]\/0\/[0-9]*\.0/",
            properties="Switchport_Mode,Access_VLAN,Allowed_VLANs,Description")
    q2 = bfq.switchedVlanProperties(interfaces=f"/{if_type}-[0,1]\/0\/[0-9]*\.0/")
    all_interfaces = q1.answer().rows
    all_vlans = q2.answer().rows
    
    return {
        "interfaces": {
            node: {prop["Interface"]["interface"]: prop for prop in props}
            for node, props in group_by_node(all_interfaces, key="Interface", subkey="hostname").items()
        },
        "vlans": {
            node: [prop["VLAN_ID"] for prop in props] for node, props in group_by_node(all_vlans).items()
        }
    }
    

if __name__ == "__main__":
    pprint(load())
