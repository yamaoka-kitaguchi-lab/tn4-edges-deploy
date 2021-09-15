#!/usr/bin/env python3
"""
Load migration rule from Google Spreadsheet
"""
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint
import os
import sys
import re
import gspread
import openpyxl

# See: https://docs.google.com/spreadsheets/d/11M9m7-C7Ogvuow7F5OG4U--TBk4gwETUcWTZWEJGCOY
SPREADSHEET_KEY = "11M9m7-C7Ogvuow7F5OG4U--TBk4gwETUcWTZWEJGCOY"
JSON_KEYFILE_PATH = os.path.join(os.path.dirname(__file__), "../.secrets/googleapi.json")

XLSX_PATH = os.path.join(os.path.dirname(__file__), "./port_migration_rules.xlsx")


def open_worksheets(keyfile, sheetkey):
  scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
  credentials = ServiceAccountCredentials.from_json_keyfile_name(keyfile, scope)
  gc = gspread.authorize(credentials)
  workbook = gc.open_by_key(sheetkey)
  return workbook.worksheets()


def open_xlsx(xlsx_path):
  print("Loading migration rules from Excel...")
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
    tn3_port   = stringify(l[2])                   # Column C
    tn4_desc   = stringify(l[3]).replace(" ", "")  # Column D
    tn4_noshut = stringify(l[5]) != "down"         # Column F
    tn4_poe    = stringify(l[7]) == "TRUE"         # Column H
    tn4_lag    = stringify(l[8])                   # Column I (name of LAG parent)

    # Header
    if n < 1: continue

    # Skip uplink LAG interfaces as well as incomplete lines
    if tn4_port == "": continue
    if tn3_port == "" and tn4_desc == "": continue
    if tn4_port == "ae0": continue
    if tn4_port == "ae1": continue  # added temporally (2021.09.15)
    if tn4_port[:2] == "et": continue

    # Mark if this port connects to AP or Meraki switch (LAG parent and children)
    # Submit specified VLAN settings instead of migrating from Tn3
    wifi_mode = False
    to_ap = tn4_desc[:2] in ["o-", "s-"] or tn4_desc[:3] == "ap-"
    is_lag_child = re.match('.*-p[2-9]*\(.*\)', tn4_desc) is not None
    is_lag_parent = tn4_port[:2] == "ae" and re.match('.*-p[2-9]*', tn4_desc) is not None
    if to_ap or is_lag_parent or is_lag_child:
      wifi_mode = True
      tn3_port = ""

    rule[tn4_port] = {
      "wifi_mode":   wifi_mode,
      "tn3_port":    tn3_port,
      "description": tn4_desc,
      "enable":      tn4_noshut,
      "poe":         tn4_poe,
      "lag":         tn4_lag,
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
    print(f"Loading migration rule: {tn4_hostname} (id:{i})")
    try:
      lines = sheet.get_all_values()
    except AttributeError:
      lines = [l for l in sheet.values]
    rules[tn4_hostname] = parse_migration_rule(lines)
  return rules


if __name__ == "__main__":
  #sheets = open_worksheets(JSON_KEYFILE_PATH, SPREADSHEET_KEY)
  #pprint(load(sheets, hosts=["minami1", "minami2"]))
  #pprint(load(sheets))
  
  sheets = open_xlsx(XLSX_PATH)
  #pprint(load(sheets, hosts=["minami1", "minami2"]))
  pprint(load(sheets))
  