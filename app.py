# Non-technical User Interface 

import streamlit as st
import json
from qualifier import qualify_lead
# from sheets import log_to_sheet  # your existing gspread logic

st.set_page_config(page_title="Solar Lead Qualifier", page_icon="☀️")
st.title("☀️ Solar Lead Qualifier")

with st.form("lead_form"):
    name = st.text_input("Lead Name")
    email = st.text_input("Email")
    notes = st.text_area("Notes from call / inquiry")
    budget = st.text_input("Budget (optional)")
    timeline = st.selectbox("Timeline", ["ASAP", "1-3 months", "3-6 months", "Just browsing"])
    submitted = st.form_submit_button("Qualify Lead")

if submitted:
    with st.spinner("Scoring lead..."):
        result = qualify_lead(name, email, notes, budget, timeline)
        data = json.loads(result)

    st.metric("Lead Score", f"{data['score']}/10")
    st.write(f"**Reasoning:** {data['reason']}")

    # log_to_sheet(name, email, data['score'], data['reason'])
    st.success("Logged to tracking sheet ✅")
