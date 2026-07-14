"""
AI Lead Qualifier — batch mode.
Reads new leads from a Google Sheet, scores them using an LLM,
and writes the results back to the sheet.
"""

import os
from dotenv import load_dotenv

from qualifier import qualify_lead
from sheets import get_sheet, write_result, write_error, get_unscored_rows

load_dotenv("config.env")


def main():
    sheet = get_sheet()

    for index, row, sheet_row in get_unscored_rows(sheet):
        try:
            result = qualify_lead(
                name=row["Name"],
                company=row["Company"],
                source=row["Source"],
                notes=row["Notes"],
            )
            print("Score:", result["score"])
            print("Status:", result["status"])
            print("Next Action:", result["next_action"])
            print("Reason:", result["reason"])
            write_result(sheet, sheet_row, result)
        except Exception as e:
            print(f"Error processing lead {row['Name']}: {e}")
            write_error(sheet, sheet_row)


if __name__ == "__main__":
    main()
