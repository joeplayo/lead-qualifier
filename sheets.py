"""
Google Sheets I/O — authentication, reading leads, writing results.
"""

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_FILE = "credentials/service_account.json"
SPREADSHEET_NAME = "Lead Sample Data"


def get_sheet(credentials_file=CREDENTIALS_FILE, spreadsheet_name=SPREADSHEET_NAME):
    """Authenticate with Google Sheets and return the worksheet."""
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open(spreadsheet_name)
    return spreadsheet.sheet1


def write_result(sheet, sheet_row, result):
    """Write a qualification result back to the given row."""
    sheet.update_cell(sheet_row, 5, result["score"])
    sheet.update_cell(sheet_row, 6, result["status"])
    sheet.update_cell(sheet_row, 7, result["next_action"])


def write_error(sheet, sheet_row):
    sheet.update_cell(sheet_row, 5, "Error")
    sheet.update_cell(sheet_row, 6, "Error")
    sheet.update_cell(sheet_row, 7, "Error")


def get_unscored_rows(sheet):
    """Return (index, row_dict, sheet_row_number) for rows with no Status yet."""
    rows = sheet.get_all_records()
    for index, row in enumerate(rows):
        if row["Status"] == "":
            yield index, row, index + 2
