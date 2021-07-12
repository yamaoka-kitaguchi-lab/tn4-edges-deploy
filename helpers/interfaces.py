#!/usr/bin/env python3
from pybatfish.client.commands import *
from pybatfish.question import bfq
from pybatfish.question.question import load_questions
from pprint import pprint
import os

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "./tn3")


def group_by_node(props, key="Node", subkey="name"):
    by_node = {}
    for prop in props:
        node = prop[key][subkey]
        try:
            by_node[node].append(prop)
        except KeyError:
            by_node[node] = [prop]
    return by_node


def enum_interfaces(if_from, if_to):
    if_base = "/".join(if_from.split("/")[:-1])
    port_from = int(if_from.split("/")[-1])
    port_to = int(if_to.split("/")[-1])
    return [if_base + f"/{port}" for port in range(port_from, port_to+1)]


def enum_vlans(vlan_str):
    vlans = []
    if vlan_str in [None, "None", ""]:
        return None
    if type(vlan_str) == int:
        return vlan_str
    for vlan_range in vlan_str.split(","):
        v = vlan_range.split("-")
        if len(v) == 1:
            vlans.append(int(v[0]))
        if len(v) == 2:
            vlans.extend(list(range(int(v[0]), int(v[1])+1)))
    return vlans


# CAUTION: Dirty hack
def interface_range_vlan(cf):
    interfaces = {}
    n = 0
    while n < len(cf):
        if cf[n].lstrip()[:15] == "interface-range":
            depth = 1
            members = []
            enabled = True
            description = ""
            mode = "NONE"
            vlan_str = ""
            
            while depth > 0:
                n += 1
                if cf[n][-1] == "{":
                    depth += 1
                if cf[n][-1] == "}":
                    depth -= 1
            
                tk = cf[n].rstrip(";").split()
                if tk[0] == "member":
                    members.append(tk[1])
                if tk[0] == "member-range":
                    members += enum_interfaces(tk[1], tk[3])
                if tk[0] == "disable":
                    enabled = False
                if tk[0] == "port-mode":
                    mode = tk[1].upper()
                if tk[0] == "members":
                    vlan_str = " ".join(tk[1:]).strip("[]")
                
            if mode == "NONE":
                break
            for member in members:
                interfaces[member] = {
                    "enabled": enabled,
                    "description": description,
                    "mode": mode,
                    "untagged": enum_vlans(vlan_str) if mode == "ACCESS" else None,
                    "tagged": enum_vlans(vlan_str) if mode == "TRUNK" else None,
                }
        n += 1
    return interfaces


def interface_range_patch(loader):
    def new_loader(*args, **kwargs):
        data = loader(*args, **kwargs)
        for hostname in data:
            with open(os.path.join(SNAPSHOT_PATH, f"./configs/{hostname}.cfg")) as fd:
                data[hostname] |= interface_range_vlan(fd.read().split("\n"))
        return data
    return new_loader


def load(if_type="ge"):
    load_questions()
    bf_init_snapshot(SNAPSHOT_PATH)
    
    q1 = bfq.interfaceProperties(
            interfaces=f"/{if_type}-[0,1]\/0\/[0-9]*\.0/",
            properties="Active,Switchport_Mode,Access_VLAN,Allowed_VLANs,Description")
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


@interface_range_patch
def load_interfaces(if_type="ge"):
    return {
        hostname: {
            ifname.split(".")[0]: {
                "enabled": prop["Active"],
                "description": prop["Description"],
                "mode": prop["Switchport_Mode"],  # "ACCESS" or "TRUNK" or "NONE"
                "untagged": enum_vlans(prop["Access_VLAN"]),
                "tagged": enum_vlans(prop["Allowed_VLANs"]),
            }
            for ifname, prop in props.items()
        }
        for hostname, props in load(if_type)["interfaces"].items()
    }


if __name__ == "__main__":
    #pprint(load())
    pprint(load_interfaces())
