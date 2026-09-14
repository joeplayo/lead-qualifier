"""
AI Lead Qualifier
Reads new leads from a Google Sheet, scores them using an LLM,
and writes the results back to the sheet.
"""

import os
import gspread
import json
from google.oauth2.service_account import Credentials
from groq import Groq
from dotenv import load_dotenv

load_dotenv("config.env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client_ai = Groq(api_key=GROQ_API_KEY)

# --- Configuration ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_FILE = "credentials/service_account.json"  # path to service account JSON
SPREADSHEET_NAME = "Lead Sample Data"  # name of your Google Sheet


def get_sheet():
    """Authenticate with Google Sheets and return the worksheet."""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    return spreadsheet.sheet1


def qualify_lead(sheet, row, sheet_row):
    prompt = f"""
You are a lead qualification assistant for a solar installation company.
Score the following lead from 1-10 and provide a next action.

Lead Info:
- Name: {row['Name']}
- Company: {row['Company']}
- Source: {row['Source']}
- Notes: {row['Notes']}

Respond in this exact JSON format:
{{
    "score": <number 1-10>,
    "status": "<Hot / Warm / Cold>",
    "next_action": "<one sentence recommended next action>",
    "reason": "<one sentence explanation of the score>"
}}

Respond with JSON only, no other text.
"""
    try:
        response = client_ai.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
        
        json_string = response.choices[0].message.content
        result = json.loads(json_string)
        
        print("Score:", result["score"])
        print("Status:", result["status"])
        print("Next Action:", result["next_action"])
        print("Reason:", result["reason"])

        sheet.update_cell(sheet_row, 5, result["score"])
        sheet.update_cell(sheet_row, 6, result["status"])
        sheet.update_cell(sheet_row, 7, result["next_action"])
    except Exception as e:
        print(f"Error processing lead {row['Name']}: {e}")
        
        sheet.update_cell(sheet_row, 5, "Error")
        sheet.update_cell(sheet_row, 6, "Error")
        sheet.update_cell(sheet_row, 7, "Error")

def main():
    sheet = get_sheet()
    rows = sheet.get_all_records()

    for index, row in enumerate(rows):
        if row["Status"] == "":
            sheet_row = index + 2
            qualify_lead(sheet, row, sheet_row)


if __name__ == "__main__":
    main()
