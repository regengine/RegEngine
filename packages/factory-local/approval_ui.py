"""Read-only rule review screen. streamlit run approval_ui.py --server.port 8501"""

from __future__ import annotations

import json

import streamlit as st
from pipeline import pg_connect

st.set_page_config(page_title="factory-local approvals", layout="wide")
st.title("Rules awaiting human verification")

with pg_connect() as conn:
    rows = conn.execute(
        """SELECT r.rule_uid, r.extraction_source, r.rego, r.z3_result, r.ir_json, b.statutory_text
           FROM extracted_rules r JOIN bill_versions b USING (version_uid)
           WHERE r.human_verified = false ORDER BY r.updated_at"""
    ).fetchall()

if not rows:
    st.info("No data yet")

for rule_uid, source, rego, z3_result, ir_json, statutory_text in rows:
    st.header(rule_uid)
    st.caption(f"Extraction source: {source}")
    left, right = st.columns(2)
    with left:
        st.subheader("Statutory text")
        st.text(statutory_text)
        st.subheader("Deontic IR")
        st.code(json.dumps(ir_json, indent=2, ensure_ascii=False), language="json")
    with right:
        st.subheader("Rego")
        st.code(rego, language="rego")
        st.subheader("Z3 result")
        st.code(json.dumps(z3_result, indent=2), language="json")

    st.info("No data yet: evaluation cases required before approval and deployment")
