#!/usr/bin/env python3
from pybatfish.client.commands import *
from pybatfish.question import bfq
from pybatfish.question.question import load_questions
from pprint import pprint
import re
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
    interfaces = {}         # Dict of interface metadata
    uplink_interfaces = []  # List of the uplink interface name
    n = 0
    while n < len(cf):
        if cf[n].lstrip()[:15] == "interface-range":
            depth = 1
            members = []
            enabled = True
            description = ""
            mode = "NONE"
            vlan_str = ""
            uplink = False
            
            if cf[n].lstrip()[15:].strip(" {")  == "uplink":
                uplink = True
            
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
            
            if uplink:
                uplink_interfaces += members
            
            if mode == "NONE":
                continue
            
            for member in members:
                interfaces[member] = {
                    "enabled": enabled,
                    "mode": mode,
                    "untagged": int(vlan_str) if mode == "ACCESS" else None,
                    "tagged": enum_vlans(vlan_str) if mode == "TRUNK" else None,
                }
                if description:
                    interfaces[member]["description"] = description
        n += 1
    return interfaces, uplink_interfaces


def interface_range_patch(loader):
    def new_loader(*args, **kwargs):
        data, keep = loader(*args, **kwargs)
        for hostname in data:
            try:
                with open(os.path.join(SNAPSHOT_PATH, f"./configs/{hostname}_juniper.conf")) as fd:
                    interfaces, uplinks = interface_range_vlan(fd.read().split("\n"))
                    for ifname, props in interfaces.items():
                        try:
                            data[hostname][ifname].update(props)
                        except KeyError:
                            data[hostname][ifname] = props
                    for ifname in uplinks:
                        del(data[hostname][ifname])
            except FileNotFoundError as e:
                print("Skipped to parse interface-range (not Juniper host?):", hostname)
                continue
        return data, keep
    return new_loader


def load():
    load_questions()
    bf_init_snapshot(SNAPSHOT_PATH)
    
    interface_props = "Active,Switchport_Mode,Access_VLAN,Allowed_VLANs,Description"
    alala_phy_regex = "(Fast|Gigabit)Ethernet0\/[0-9]{1,2}"
    juniper_phy_regex = "[g,x]e-[0-9]+\/[0,1]\/[0-9]{1,2}"
    juniper_log_regex = f"{juniper_phy_regex}\.0"
    
    q1 = bfq.interfaceProperties(interfaces=f"/{alala_phy_regex}|{juniper_phy_regex}/", properties=interface_props)
    q2 = bfq.interfaceProperties(interfaces=f"/{juniper_log_regex}/", properties=interface_props)
    q3 = bfq.switchedVlanProperties(interfaces=f"/{juniper_log_regex}/")
    
    all_phy_interfaces = q1.answer().rows
    all_log_interfaces = q2.answer().rows
    all_vlans = q3.answer().rows
    
    return {
        "phy_interfaces": {
            node: {prop["Interface"]["interface"]: prop for prop in props}
            for node, props in group_by_node(all_phy_interfaces, key="Interface", subkey="hostname").items()
        },
        "log_interfaces": {
            node: {prop["Interface"]["interface"]: prop for prop in props}
            for node, props in group_by_node(all_log_interfaces, key="Interface", subkey="hostname").items()
        },
        "vlans": {
            node: [prop["VLAN_ID"] for prop in props] for node, props in group_by_node(all_vlans).items()
        }
    }


@interface_range_patch
def load_chassis_interfaces(excludes=[]):
    data = load()
    interfaces = {}
    n_stacked = {}
    for hostname, props in data["phy_interfaces"].items():
        interfaces[hostname] = {}
        chassis = set()
        if hostname in excludes:
            continue
        for ifname, p_prop in props.items():
            if ifname in excludes:
                continue
            
            prop = p_prop
            try:
                prop = data["log_interfaces"][hostname][f"{ifname}.0"]
            except KeyError:
                pass
            
            chassis_number = re.match("[g,x]e-(\d+)/\d+/\d+", ifname)  # Juniper format
            if chassis_number:
                chassis.add(chassis_number[1])
            
            desc = prop["Description"]
            if desc is None:
                desc = ""
            
            # Interface name conversion rule for Alaxala (2021.07.31)
            # ex) from FastEthernet0/21 to 0/21
            ifname = ifname.lstrip("FastEthernet")
            ifname = ifname.lstrip("GigabitEthernet")
            
            interfaces[hostname][ifname] = {
                "enabled": prop["Active"],
                "description": desc,
                "mode": prop["Switchport_Mode"],
                "untagged": prop["Access_VLAN"],
                "tagged": enum_vlans(prop["Allowed_VLANs"]),
                "lag": None,
                "poe": None,
            }
        
        n_stacked[hostname] = len(chassis)
    
    # Override with exception rule (Tn3 hostnames)
    n_stacked["green1-1"] = 2
    n_stacked["gsic-1"] = 1
    n_stacked["minami1-1"] = 1
    
    return interfaces, n_stacked


if __name__ == "__main__":
    interfaces, n_stacked = load_chassis_interfaces()
    pprint(interfaces)
    for hostname, n in n_stacked.items():
        print(n, "\t", hostname)
