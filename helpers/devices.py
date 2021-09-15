#!/usr/bin/env python3
"""
Load sites and devices from Google Spreadsheet
"""
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint
import os
import sys
import gspread

# See: https://docs.google.com/spreadsheets/d/19ZUxcU-pdpwuNDDOA8u9IaQyuXxwpZh1X7uRygeo7Hw
SPREADSHEET_KEY = "19ZUxcU-pdpwuNDDOA8u9IaQyuXxwpZh1X7uRygeo7Hw"
JSON_KEYFILE_PATH = os.path.join(os.path.dirname(__file__), "../.secrets/googleapi.json")


def open_worksheets(keyfile, sheetkey):
  scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
  credentials = ServiceAccountCredentials.from_json_keyfile_name(keyfile, scope)
  gc = gspread.authorize(credentials)
  workbook = gc.open_by_key(sheetkey)
  return workbook.worksheets()


def load(hosts=[]):
  devices =[]
  sheet = open_worksheets(JSON_KEYFILE_PATH, SPREADSHEET_KEY)[0]
  lines = sheet.get_all_values()
  for n, l in enumerate(lines):
    if n < 2: continue

    register    = l[0]
    region      = l[1]
    group_name  = l[2]
    group       = l[3]
    site_name   = l[4]
    site        = l[5]
    tn3_name    = l[6]
    name        = l[7]
    device_type = l[8]
    ipv4        = l[9]
    cidr        = l[10]

    if hosts and name not in hosts:
      continue

    if register != "FALSE":
      devices.append({
        "name": name,
        "tn3_name": tn3_name,
        "device_type": device_type,
        "region": region,
        "sitegroup_name": group_name,
        "sitegroup": group,
        "site_name": site_name,
        "site": site,
        "ipv4": ipv4,
        "cidr": cidr,
      })
  return devices


if __name__ == "__main__":
  pprint(load())
