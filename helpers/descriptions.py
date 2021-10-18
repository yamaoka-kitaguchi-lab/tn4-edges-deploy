#!/usr/bin/env python3
"""
Load description
"""
from pprint import pprint
import os
import re
import openpyxl

XLSX_PATH = os.path.join(os.path.dirname(__file__), "./port_migration_rules_part2.xlsx")


def open_xlsx(xlsx_path):
  print("Loading description from Excel...")
  book = openpyxl.load_workbook(xlsx_path)
  return book.worksheets


def stringify(c):
  if c == None: return ""
  if c == True: return "TRUE"
  if c == False: return "FALSE"
  return c


def parse_migration_rule(lines):
  rule = {}

  for n, l in enumerate(lines):
    tn4_port   = stringify(l[0])                   # Column A
    tn4_desc   = stringify(l[3]).replace(" ", "")  # Column D
    tn4_noshut = stringify(l[5]) != "down"         # Column F

    # Header
    if n < 1: continue

    # Skip incomplete lines
    if tn4_port == "": continue

    # Replace ae1 to ae0
    tn4_desc = tn4_desc.replace("ae1", "ae0")
    if tn4_port == "ae1":
      tn4_port = "ae0"

    rule[tn4_port] = {
      "description": tn4_desc,
      "enabled":      tn4_noshut,
    }

  return rule


def load(sheets=None, hosts=[]):
  rules = {}
  if sheets is None:
    sheets = open_xlsx(XLSX_PATH)
  for i, sheet in enumerate(sheets):
    tn4_hostname = sheet.title
    if hosts and tn4_hostname not in hosts:
      continue
    print(f"Loading description: {tn4_hostname} (id:{i})")
    try:
      lines = sheet.get_all_values()
    except AttributeError:
      lines = [l for l in sheet.values]
    rules[tn4_hostname] = parse_migration_rule(lines)
  return rules


if __name__ == "__main__":
  sheets = open_xlsx(XLSX_PATH)
  #pprint(load(sheets, hosts=["minami1", "minami2"]))
  pprint(load(sheets))
