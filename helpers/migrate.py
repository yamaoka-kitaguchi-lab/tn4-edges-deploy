#!/usr/bin/env python3
from pprint import pprint
import os


def converter(rules):
    def inner(tn3_port):
        try:
            return rules[tn3_port]
        except KeyError:
            return None
    return inner


def kitaguchi_rule(host):
    port_rules = {}
    desc_rules = {}
    cfg = os.path.join(os.path.dirname(__file__), f"./tn3/migration/rules/{host}.txt")
    with open(cfg) as fd:
        for n, line in enumerate(fd):
            if n == 0:
                continue
            rule = line.split()
            if len(rule) < 8:
                continue
            tn3_port, tn4_port, tn4_desc = rule[0], rule[6], rule[7]
            if tn4_port == "-":
                continue
            port_rules[tn3_port] = tn4_port
            desc_rules[tn3_port] = tn4_desc
    return {
        "port": port_rules,
        "description": desc_rules,
    }


def kitaguchi_rules():
    rulebook = []
    for n in range(2, 9+1):
        host = f"minami{n}"
        rulebook.append({
            "hostname": host,
            "rules": kitaguchi_rule(host)
        })
    return rulebook


def make_port_desc_converter(tn4_hostname):
    port_rulebook = {
        **{
            k_rule["hostname"]: k_rule["rules"]["port"] for k_rule in kitaguchi_rules()
        },
    }
    desc_rulebook = {
        **{
            k_rule["hostname"]: k_rule["rules"]["description"] for k_rule in kitaguchi_rules()
        },
    }
    try: 
        return converter(port_rulebook[tn4_hostname]), converter(desc_rulebook[tn4_hostname])
    except KeyError:
        return None, None


if __name__ == "__main__":
    f = make_port_desc_converter("minami3")
    pc, dc = f
    for old in ["ge-0/0/0", "ge-0/0/47", "ge-1/0/0", "ge-1/0/47"]:
        pprint(pc(old))
        pprint(dc(old))
