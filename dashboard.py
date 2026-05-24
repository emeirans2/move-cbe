import streamlit as st
import httpx
import plotly.graph_objects as go
import json

BASE = "http://localhost:8000"

st.set_page_config(page_title="MOVE CBE", layout="wide", page_icon="🎯")
st.title("🎯 MOVE CBE — Cultural-Behavioural Engine")

# --- Sidebar: client selector ---
st.sidebar.header("Client")
clients_resp = httpx.get(f"{BASE}/clients")
clients = clients_resp.json() if clients_resp.status_code == 200 else []

if not clients:
    st.warning("No clients yet. Add one below.")
    st.stop()

client_names = {c["id"]: c["name"] for c in clients}
selected_id = st.sidebar.selectbox("Select client", options=list(client_names.keys()),
                                    format_func=lambda x: client_names[x])

# --- Main tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🎨 Creatives", "🌤 Score Mood", "📋 Audit"])

# TAB 1: Dashboard
with tab1:
    st.subheader("Today's Recommendations")
    recs_resp = httpx.get(f"{BASE}/recommendations?status=pending")
    recs = [r for r in recs_resp.json() if r["client_id"] == selected_id]

    if not recs:
        st.info("✅ Nothing needs you today — no pending recommendations for this client.")
    else:
        for rec in recs:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 2])
                with col1:
                    st.markdown(f"**{rec['headline'] or 'Creative ' + str(rec['creative_id'])}**")
                    st.caption(rec["primary_text"][:80] + "...")
                with col2:
                    match_pct = round(rec["emotional_match"] * 100, 1)
                    color = "🟢" if match_pct >= 80 else "🟡" if match_pct >= 70 else "⚪"
                    st.metric("Match", f"{color} {match_pct}%")
                with col3:
                    st.metric("Demand", f"×{rec['demand_index']}")
                    st.caption(f"€{rec['current_budget_eur']} → €{rec['proposed_budget_eur']}")
                with col4:
                    col4a, col4b = st.columns(2)
                    with col4a:
                        if st.button("✅ Approve", key=f"approve_{rec['id']}"):
                            httpx.post(f"{BASE}/recommendations/{rec['id']}/approve")
                            st.success("Approved!")
                            st.rerun()
                    with col4b:
                        if st.button("❌ Reject", key=f"reject_{rec['id']}"):
                            httpx.post(f"{BASE}/recommendations/{rec['id']}/reject")
                            st.rerun()
                st.divider()

    # Mood vector radar
    st.subheader("Today's Mood Vector")
    from datetime import date
    today = str(date.today())
    db_resp = httpx.get(f"{BASE}/audit?limit=1")



    axes = ["joy","trust","anticipation","surprise","fear","urgency","nostalgia","aspiration","belonging","sadness"]
    if recs:
        mood_vec = recs[0].get("mood_vector", [0]*10) if "mood_vector" in recs[0] else [0.3,0.5,0.2,0.1,0.5,0.3,0.1,0.3,0.4,0.4]
    else:
        mood_vec = [0.3,0.5,0.2,0.1,0.5,0.3,0.1,0.3,0.4,0.4]

    fig = go.Figure(go.Scatterpolar(
        r=mood_vec + [mood_vec[0]],
        theta=axes + [axes[0]],
        fill='toself',
        name='Today mood',
        line_color='#6366f1'
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,1])),
                      showlegend=False, height=400, paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

# TAB 2: Creatives
with tab2:
    st.subheader(f"Creatives for {client_names[selected_id]}")
    creatives_resp = httpx.get(f"{BASE}/creatives/{selected_id}")
    creatives = creatives_resp.json()

    if not creatives:
        st.info("No creatives yet.")
    else:
        for c in creatives:
            st.markdown(f"**{c['headline'] or 'No headline'}** — `{c['status']}`")
            st.caption(c["primary_text"])
            st.divider()

    st.subheader("Add Creative")
    with st.form("add_creative"):
        headline = st.text_input("Headline")
        primary_text = st.text_area("Primary text")
        visual_desc = st.text_input("Visual description (optional)")
        submitted = st.form_submit_button("Score & Add")
        if submitted and primary_text:
            with st.spinner("Scoring creative (3 runs)..."):
                resp = httpx.post(f"{BASE}/creatives", json={
                    "client_id": selected_id,
                    "headline": headline,
                    "primary_text": primary_text,
                    "visual_description": visual_desc
                }, timeout=90)
            if resp.status_code == 200:
                result = resp.json()
                st.success(f"Creative scored! Urgency: {result['scores']['urgency']}, Joy: {result['scores']['joy']}")
                st.rerun()
            else:
                st.error(f"Error: {resp.text}")

# TAB 3: Score Mood
with tab3:
    st.subheader("Score Today's Cultural Mood")
    with st.form("score_mood"):
        brief = st.text_area("Today's context brief (news, weather, events...)", height=200,
                             placeholder="Latvijas ziņas šodien: ...")
        col1, col2, col3 = st.columns(3)
        with col1:
            name_day = st.slider("Name day boost", 0.0, 0.3, 0.0, 0.05)
        with col2:
            payday = st.slider("Payday window", 0.0, 0.3, 0.0, 0.05)
        with col3:
            holiday = st.slider("Holiday proximity", 0.0, 0.4, 0.0, 0.05)
        submitted = st.form_submit_button("Score Mood")
        if submitted and brief:
            with st.spinner("Scoring mood..."):
                resp = httpx.post(f"{BASE}/mood/score", json={
                    "brief": brief,
                    "demand_inputs": {
                        "name_day_boost": name_day,
                        "payday_window": payday,
                        "holiday_proximity_boost": holiday
                    }
                }, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                st.success(f"Mood scored! Demand index: {result['demand_index']}")
                st.json(result["scores"])

                # Run matches automatically
                with st.spinner("Running matches..."):
                    budgets = {str(c["id"]): 50.0 for c in creatives}
                    match_resp = httpx.post(f"{BASE}/matches/run", json={
                        "client_id": selected_id,
                        "current_budgets": budgets
                    }, timeout=30)
                if match_resp.status_code == 200:
                    st.success("Matches computed. Check the Dashboard tab.")
                    st.rerun()
            else:
                st.error(f"Error: {resp.text}")

# TAB 4: Audit
with tab4:
    st.subheader("Audit Log")
    audit_resp = httpx.get(f"{BASE}/audit?limit=20")
    audit = audit_resp.json()
    if audit:
        for entry in audit:
            st.markdown(f"`{entry['ts'][:19]}` **{entry['event_type']}** — {entry['entity_type']} #{entry['entity_id']}")
    else:
        st.info("No audit entries yet.")
