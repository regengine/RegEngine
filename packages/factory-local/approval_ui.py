"""Human approval screen.  streamlit run approval_ui.py --server.port 8501"""

from __future__ import annotations

import json

import streamlit as st

from pipeline import approve, pg_connect

st.set_page_config(page_title="factory-local approvals", layout="wide")
st.title("Rules awaiting human verification")

with pg_connect() as conn:
    rows = conn.execute(
        """SELECT r.rule_uid, r.extraction_source, r.rego, r.z3_result, r.ir_json, b.statutory_text
           FROM extracted_rules r JOIN bill_versions b USING (version_uid)
           WHERE r.human_verified = false ORDER BY r.updated_at"""
    ).fetchall()

if not rows:
    st.info("No unverified rules. Run `python pipeline.py run` to extract one.")

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

    if st.button("Approve & Deploy", key=f"approve-{rule_uid}", type="primary"):
        try:
            with st.spinner("Deploying to OPA and writing receipts"):
                result = approve(rule_uid)
            st.success("Deployed and receipts written")
            st.json(result)
        except Exception as exc:  # surface any failure to the reviewer
            st.error(f"{type(exc).__name__}: {exc}")
