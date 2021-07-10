#!/usr/bin/env python3
from pybatfish.client.commands import *
from pybatfish.question import bfq
from pybatfish.question.question import load_questions, list_questions

from pprint import pprint

load_questions()
bf_init_snapshot("./tn3")

props = bfq.interfaceProperties(nodes="minami3-1").answer()
pprint(props.rows)