#!/usr/bin/env python3
"""
Load sites and devices from Google Spreadsheet
"""
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint
import sys
import gspread

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
    idx = 3
    while True:
        if not sheet.cell(idx, 1) or idx > 1000:
            break
        devices.append({
            "site": {
                "fullname": sheet.cell(idx, 2).value,
                "slug": sheet.cell(idx, 3).value
            },
            "devicetype": {
                "slug": sheet.cell(idx, 4).value
            },
            "device": {
                "fullname": sheet.cell(idx, 6).value,
                "slug": sheet.cell(idx, 7).value
            },
            "vc": {"Single": False, "Stacked": True}[sheet.cell(idx, 5).value],
        })
        idx += 1
    return devices


if __name__ == "__main__":
    keypath = sys.argv[1]
    load(keypath)
