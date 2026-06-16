"""
AI Lead Qualifier
Reads new leads from a Google Sheet, scores them using an LLM,
and writes the results back to the sheet.
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from dotenv import load_dotenv

load_dotenv("config.env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client_ai = genai.Client(api_key=GEMINI_API_KEY)

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


def qualify_lead(row):
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
    response = client_ai.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt
    )
    print(response.text)

def main():
    sheet = get_sheet()
    rows = sheet.get_all_records()
    new_leads = [row for row in rows if row["Status"] == ""]
    
    # Step 5: test on first lead only
    qualify_lead(new_leads[0])
    


if __name__ == "__main__":
    main()
