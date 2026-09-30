import io

import pandas as pd
import streamlit as st

from scraper import search_public_leads

STATUS_OPTIONS = ["Pending", "Interested", "Call Back", "Not Interested", "Closed", "Invalid Number"]
COLUMNS = [
    "Lead ID", "Business Name", "Phone", "Call Link", "WhatsApp Link",
    "Email Address", "Website", "Call Status", "Notes", "City",
]

st.set_page_config(page_title="Webtel Lead Generator", page_icon="📞", layout="wide")
st.title("📞 Webtel Sales Lead Generator & Telecalling Tracker")

if "lead_data" not in st.session_state:
    st.session_state["lead_data"] = pd.DataFrame(columns=COLUMNS)

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("🔎 Search Settings")
    industry = st.text_input("Target Profession / Industry", value="CA Firms")
    location = st.text_input("City / Location", value="Chennai")
    limit = st.slider("Number of Leads to Find", min_value=5, max_value=50, value=15)

    if st.button("🚀 Find Leads", width="stretch"):
        if not industry.strip() or not location.strip():
            st.warning("Please enter both industry and location.")
        else:
            with st.spinner(f"Searching public listings for {industry} in {location}..."):
                new_leads = search_public_leads(industry.strip(), location.strip(), limit=limit)
            if new_leads:
                combined = pd.concat(
                    [st.session_state["lead_data"], pd.DataFrame(new_leads, columns=COLUMNS)],
                    ignore_index=True,
                )
                combined["_key"] = combined["Business Name"].astype(str).str.strip().str.lower()
                combined = combined.drop_duplicates(subset="_key", keep="first").drop(columns="_key")
                combined["Lead ID"] = range(1, len(combined) + 1)
                st.session_state["lead_data"] = combined.reset_index(drop=True)
                st.success(f"Found {len(new_leads)} leads.")
            else:
                st.error("No leads found. Try a different query or retry in a minute.")

    if st.button("🧹 Clear List", width="stretch"):
        st.session_state["lead_data"] = pd.DataFrame(columns=COLUMNS)
        st.rerun()

df = st.session_state["lead_data"]

if df.empty:
    st.info("👈 Enter an industry and city in the sidebar and click **🚀 Find Leads** to begin.")
    st.stop()

# ---------------- Analytics ----------------
status_counts = df["Call Status"].value_counts()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Prospects", len(df))
m2.metric("Pending Calls", int(status_counts.get("Pending", 0)))
m3.metric("Interested", int(status_counts.get("Interested", 0)))
m4.metric("Call Back Required", int(status_counts.get("Call Back", 0)))
m5.metric("Closed Deals", int(status_counts.get("Closed", 0)))

st.divider()

# ---------------- Filter ----------------
selected_status = st.multiselect("Filter by Call Status", options=STATUS_OPTIONS, default=STATUS_OPTIONS)
filtered = df[df["Call Status"].isin(selected_status)]

# ---------------- Editable table ----------------
edited = st.data_editor(
    filtered,
    key="lead_editor",
    hide_index=True,
    width="stretch",
    disabled=["Lead ID"],
    column_config={
        "Lead ID": st.column_config.NumberColumn("Lead ID", width="small"),
        "Website": st.column_config.LinkColumn("Website", display_text="Visit Web"),
        "WhatsApp Link": st.column_config.LinkColumn("WhatsApp", display_text="💬 Chat on WA"),
        "Call Link": st.column_config.LinkColumn("Call", display_text="📞 Call Now"),
        "Call Status": st.column_config.SelectboxColumn("Call Status", options=STATUS_OPTIONS, required=True),
        "Notes": st.column_config.TextColumn("Notes", help="Add call remarks"),
    },
)

# Persist edits back to the master list by Lead ID.
if not edited.equals(filtered):
    master = df.set_index("Lead ID")
    master.update(edited.set_index("Lead ID"))
    st.session_state["lead_data"] = master.reset_index()[COLUMNS]
    st.rerun()

# ---------------- Export ----------------
export_df = st.session_state["lead_data"]
c1, c2 = st.columns(2)
c1.download_button(
    "📥 Export Lead List to CSV",
    data=export_df.to_csv(index=False).encode("utf-8"),
    file_name="leads.csv",
    mime="text/csv",
    width="stretch",
)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    export_df.to_excel(writer, index=False, sheet_name="Leads")
c2.download_button(
    "📊 Export Lead List to Excel (.xlsx)",
    data=excel_buffer.getvalue(),
    file_name="leads.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="stretch",
)
