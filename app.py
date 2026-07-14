"""
Solar Lead Qualifier — Streamlit UI.
"""

import os
import streamlit as st

from qualifier import qualify_lead

st.set_page_config(page_title="Solar Lead Qualifier", page_icon="☀️")

# --- Secrets → env vars (works both locally via secrets.toml and on
# Streamlit Community Cloud via the dashboard) ---
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]

st.title("☀️ Solar Lead Qualifier")

tab_single, tab_batch = st.tabs(["Score a Lead", "Run Sheet Batch"])

# ---------- Single lead ----------
with tab_single:
    st.caption("Score one lead and see the result immediately.")

    with st.form("lead_form"):
        name = st.text_input("Name")
        company = st.text_input("Company")
        source = st.selectbox(
            "Source", ["Website", "Referral", "Cold Call", "Trade Show", "Other"]
        )
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Qualify Lead")

    if submitted:
        if not name:
            st.warning("Name is required.")
        else:
            with st.spinner("Scoring lead..."):
                try:
                    result = qualify_lead(name, company, source, notes)
                except Exception as e:
                    st.error(f"Couldn't score this lead: {e}")
                    result = None

            if result:
                status_color = {"Hot": "🔴", "Warm": "🟠", "Cold": "🔵"}.get(
                    result["status"], "⚪"
                )
                col1, col2 = st.columns(2)
                col1.metric("Score", f"{result['score']}/10")
                col2.metric("Status", f"{status_color} {result['status']}")
                st.write(f"**Next action:** {result['next_action']}")
                st.write(f"**Reason:** {result['reason']}")

# ---------- Batch mode ----------
with tab_batch:
    st.caption(
        "Scans the connected Google Sheet for leads with no Status yet, "
        "scores them, and writes results back."
    )
    st.info(
        "Requires the service account credentials to be configured "
        "(see README). This runs the same logic as the original batch script."
    )

    if st.button("Run Batch"):
        from sheets import get_sheet, write_result, write_error, get_unscored_rows

        try:
            sheet = get_sheet()
        except Exception as e:
            st.error(f"Couldn't connect to the sheet: {e}")
            st.stop()

        rows_to_process = list(get_unscored_rows(sheet))
        if not rows_to_process:
            st.success("No unscored leads found — everything's up to date.")
        else:
            progress = st.progress(0)
            results_table = []
            for i, (index, row, sheet_row) in enumerate(rows_to_process):
                try:
                    result = qualify_lead(
                        name=row["Name"],
                        company=row["Company"],
                        source=row["Source"],
                        notes=row["Notes"],
                    )
                    write_result(sheet, sheet_row, result)
                    results_table.append({"Name": row["Name"], **result})
                except Exception as e:
                    write_error(sheet, sheet_row)
                    results_table.append(
                        {"Name": row["Name"], "score": "Error", "status": "Error",
                         "next_action": str(e), "reason": ""}
                    )
                progress.progress((i + 1) / len(rows_to_process))

            st.success(f"Processed {len(rows_to_process)} lead(s).")
            st.dataframe(results_table)
