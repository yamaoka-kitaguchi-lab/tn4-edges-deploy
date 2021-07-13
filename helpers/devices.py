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
KEYJSON_PATH = os.path.join(os.path.dirname(__file__), "../.secrets/googleapi.json")

def open_sheet(keyjson_path, sheetkey):
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(keyjson_path, scope)
    gc = gspread.authorize(credentials)
    sheets = gc.open_by_key(sheetkey)
    return sheets


def load(keyjson_path=KEYJSON_PATH):
    devices =[]
    sheet = open_sheet(keyjson_path, SPREADSHEET_KEY).sheet1
    lines = sheet.get_all_values()
    for n, line in enumerate(lines):
        if n < 2: continue
        
        register    = line[0]
        region      = line[1]
        group_name  = line[2]
        group       = line[3]
        site_name   = line[4]
        site        = line[5]
        device_type = line[6]
        vc          = line[7]
        name        = line[8]
        ipv4        = line[9]
        cidr        = line[10]
        
        if register is False:
            continue
        if vc == "Stacked":
            device_type += "-stacked"
        devices.append({
            "name": name,
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
    keypath = sys.argv[1]
    pprint(load(keypath))
