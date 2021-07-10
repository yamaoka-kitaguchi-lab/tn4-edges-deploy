#!/usr/bin/env python3
from pybatfish.client.commands import *
from pybatfish.question import bfq
from pybatfish.question.question import load_questions
from pprint import pprint

load_questions()
bf_init_snapshot("./tn3")

q = bfq.interfaceProperties(
    nodes="minami3-1", interfaces="/ge-[0,1]\/0\/[0-9]*\.0/",
    properties="Switchport_Mode,Access_VLAN,Allowed_VLANs,Description")
#pprint(q.answer().rows)

q = bfq.switchedVlanProperties(
    nodes="minami3-1", interfaces="/ge-[0,1]\/0\/[0-9]*\.0/")
pprint(q.answer().rows)