#!/usr/bin/env python3
from pprint import pprint
import os


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
    return lambda old_port: rules[old_port]


def rule_common():
    pass


def migrater(hostname):
    registry = {
        "minami3": rule_minami3()
    }
    try:
        return registry[hostname]
    except KeyError:
        return rule_common()


if __name__ == "__main__":
    f = migrater("minami3")
    for old in ["ge-0/0/0", "ge-0/0/47", "ge-1/0/0", "ge-1/0/47"]:
        pprint(f(old))
