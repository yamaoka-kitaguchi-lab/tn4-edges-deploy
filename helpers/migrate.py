#!/usr/bin/env python3
"""
Load migration rule from Google Spreadsheet
"""
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint
import os
import sys
import gspread

# See: https://docs.google.com/spreadsheets/d/11M9m7-C7Ogvuow7F5OG4U--TBk4gwETUcWTZWEJGCOY
SPREADSHEET_KEY = "11M9m7-C7Ogvuow7F5OG4U--TBk4gwETUcWTZWEJGCOY"
JSON_KEYFILE_PATH = os.path.join(os.path.dirname(__file__), "../.secrets/googleapi.json")


def open_worksheets(keyfile, sheetkey):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(keyfile, scope)
    gc = gspread.authorize(credentials)
    workbook = gc.open_by_key(sheetkey)
    return workbook.worksheets()


def parse_migration_rule(lines):
    rule = {}
    for n, l in enumerate(lines):
        tn4_port   = l[0]                   # Column A
        tn3_port   = l[2]                   # Column C
        tn4_desc   = l[3].replace(" ", "")  # Column D
        tn4_noshut = l[5] != "down"         # Column F
        tn4_poe    = l[7] == "TRUE"         # Column H
        tn4_lag    = l[8]                   # Column I
        
        # Header
        if n < 1: continue
        
        # Skip uplink and LAG interfaces as well as incomplete lines
        if tn4_port == "": continue
        if tn3_port == "" and tn4_desc == "": continue
        if tn4_port[:2] == "et": continue
        if tn4_port[:2] == "ae": continue
        
        # Mark if this port connects to AP or Meraki switch
        wifi_mode = False
        if tn4_desc[:2] in ["o-", "s-"] or tn4_lag[2:] != "0":
            wifi_mode = True
            tn3_port = ""
        
        rule[tn4_port] = {
            "wifi_mode": wifi_mode,
            "tn3_port":  tn3_port,
            "desc":      tn4_desc,
            "noshut":    tn4_noshut,
            "poe":       tn4_poe,
            "lag":       tn4_lag,
        }
    return rule


def load_migration_rules(hosts=[]):
    sheets = open_worksheets(JSON_KEYFILE_PATH, SPREADSHEET_KEY)
    rules = {}
    for sheet in sheets:
        tn4_hostname = sheet.title
        if hosts and tn4_hostname not in hosts:
            continue
        lines = sheet.get_all_values()
        rules[tn4_hostname] = parse_migration_rule(lines)
    return rules


if __name__ == "__main__":
    pprint(load_migration_rules(hosts=["minami2"]))
