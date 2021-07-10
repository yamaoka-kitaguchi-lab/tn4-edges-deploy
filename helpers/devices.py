#!/usr/bin/env python3
"""
Load sites and devices from Google Spreadsheet
"""
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint
import sys
import gspread

# See: https://docs.google.com/spreadsheets/d/19ZUxcU-pdpwuNDDOA8u9IaQyuXxwpZh1X7uRygeo7Hw
SPREADSHEET_KEY = "19ZUxcU-pdpwuNDDOA8u9IaQyuXxwpZh1X7uRygeo7Hw"


def open_sheet(keyjson_path, sheetkey):
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(keyjson_path, scope)
    gc = gspread.authorize(credentials)
    sheets = gc.open_by_key(sheetkey)
    return sheets


def load(keyjson_path):
    devices =[]
    sheet = open_sheet(keyjson_path, SPREADSHEET_KEY).sheet1
    lines = sheet.get_all_values()
    for n, line in enumerate(lines):
        if n < 2: continue
        devices.append({
            "site": {
                "fullname": line[1],
                "slug": line[2]
            },
            "devicetype": {
                "slug": line[3]
            },
            "device": {
                "fullname": line[5],
                "slug": line[6]
            },
            "vc": {"Single": False, "Stacked": True}[line[4]],
        })
    return devices


if __name__ == "__main__":
    keypath = sys.argv[1]
    pprint(load(keypath))
