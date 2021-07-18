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


# Source: https://labo301.slack.com/archives/DCCNU4AA2/p1625829587152400
def rule_minami3():
    rules = {}
    with open(os.path.join(os.path.dirname(__file__), "./tn3/migration/minami3.txt")) as fd:
        for n, line in enumerate(fd):
            if n == 0:
                continue
            rule = line.split()
            if len(rule) == 4:
                rules[rule[0]] = None
            if len(rule) > 4:
                rules[rule[0]] = rule[4]
    return rules


def rule_common(all_sfp=False):
    rules = {}
    for chassis in range(2):
        for port in range(48):
            tn3_port = f"ge-{chassis}/0/{port}"
            tn4_port = tn3_port
            if not all_sfp and port >= 24:
                tn4_port = "m" + tn3_port
            rules[tn3_port] = tn4_port
    return rules


def make_port_converter(tn4_hostname):
    rulebook = {
        "minami3": rule_minami3(),
        "nishi8e": rule_common(all_sfp=True),  # Dummy
        "nishi8w": rule_common(all_sfp=True),  # Dummy
        "b1": rule_common(all_sfp=True),       # Dummy
        "b2": rule_common(all_sfp=True),       # Dummy
        "j2": rule_common(all_sfp=True),       # Dummy
        "*": rule_common(),
    }
    try:
        return converter(rulebook[tn4_hostname])
    except KeyError:
        return converter(rulebook["*"])


if __name__ == "__main__":
    f = make_port_converter("minami3")
    for old in ["ge-0/0/0", "ge-0/0/47", "ge-1/0/0", "ge-1/0/47"]:
        pprint(f(old))
