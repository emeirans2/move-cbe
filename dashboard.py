import streamlit as st
import httpx
import plotly.graph_objects as go
from datetime import date

BASE = "http://localhost:8000"

st.set_page_config(page_title="MOVE CBE", layout="wide", page_icon="🎯")
st.title("🎯 MOVE CBE — Cultural-Behavioural Engine")

# --- Sidebar: client selector ---
st.sidebar.header("Client")
clients_resp = httpx.get(f"{BASE}/clients")
clients = clients_resp.json() if clients_resp.status_code == 200 else []

if not clients:
    st.warning("No clients yet.")
    st.stop()

client_names = {c["id"]: c["name"] for c in clients}
selected_id = st.sidebar.selectbox("Select client", options=list(client_names.keys()),
                                    format_func=lambda x: client_names[x])

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🎨 Creatives", "🔧 Manual Override", "📋 Audit"])

# ============ TAB 1: DASHBOARD ============
with tab1:
    # Run daily loop button
    col_run, _ = st.columns([1, 3])
    with col_run:
        if st.button("🔄 Run Daily Loop", type="primary"):
            with st.spinner("Fetching news, weather, calendar · scoring mood · matching creatives..."):
                resp = httpx.post(f"{BASE}/mood/auto", timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"✅ Loop complete · {data['recommendations_generated']} matches · sources: {', '.join(data['sources']['news'])}")
                st.rerun()
            else:
                st.error(f"Error: {resp.text}")

    st.divider()

    # --- Budget Allocation (primary view) ---
    st.subheader("💰 Budget Allocation")

    budget_resp = httpx.get(f"{BASE}/budget/{selected_id}")
    current_budget = budget_resp.json().get("budget_eur", 100.0) if budget_resp.status_code == 200 else 100.0

    col_b1, col_b2 = st.columns([1, 3])
    with col_b1:
        new_budget = st.number_input("Daily budget (€)", min_value=5.0, value=float(current_budget),
                                     step=10.0, key="budget_input")
        if st.button("Update budget"):
            httpx.post(f"{BASE}/budget/set", json={"client_id": selected_id, "budget_eur": new_budget})
            st.rerun()

    alloc_resp = httpx.post(f"{BASE}/allocate/v2", json={"client_id": selected_id}, timeout=30)
    if alloc_resp.status_code == 200:
        alloc_data = alloc_resp.json()
        allocations = alloc_data.get("allocations", [])
        if allocations:
            st.caption(f"Total: €{alloc_data['total_allocated']} · Demand index: ×{alloc_data['demand_index']} · {alloc_data['date']}")
            for a in allocations:
                pct = a["share_pct"]
                match_color = "🟢" if a["similarity"] >= 0.85 else "🟡" if a["similarity"] >= 0.75 else "⚪"
                st.markdown(f"**{a['headline']}** {match_color}")
                bar_col, info_col = st.columns([3, 1])
                with bar_col:
                    st.progress(pct / 100)
                with info_col:
                    delta = a["proposed_budget_eur"] - a["current_budget_eur"]
                    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                    st.markdown(f"**€{a['proposed_budget_eur']}** ({pct}%)")
                    st.caption(f"{arrow} from €{a['current_budget_eur']}")
                st.caption(f"Match: {round(a['similarity']*100,1)}%")
                st.write("")

            st.info("💡 Allocations are proportional to how well each creative matches today's cultural mood. The split is budget-agnostic — change the budget above and amounts rescale while percentages hold.")
            # --- Why this allocation? ---
            with st.expander("🧠 Why this allocation?", expanded=True):
                exp_resp = httpx.post(f"{BASE}/allocate/explain", json={"client_id": selected_id}, timeout=30)
                if exp_resp.status_code == 200:
                    st.write(exp_resp.json().get("explanation", ""))
                else:
                    st.caption("Explanation unavailable.")
        else:
            st.info("No allocation yet — add creatives and run the daily loop.")
    else:
        st.warning("Run the daily loop first to generate today's mood.")

    st.divider()

    # --- Mood radar ---
    st.subheader("🌤 Today's Mood Vector")
    # --- Mood vector as battery bars ---
    st.subheader("🌤 Today's Mood Vector")
    axes = ["joy","trust","anticipation","surprise","fear","urgency","nostalgia","aspiration","belonging","sadness"]
    mood_vec = alloc_data.get("mood_vector") if alloc_resp.status_code == 200 and "mood_vector" in alloc_data else None
    if not mood_vec:
        mood_vec = [0.3,0.5,0.4,0.2,0.3,0.2,0.1,0.3,0.5,0.2]

    # Sort emotions high to low so the dominant mood reads top-down
    paired = sorted(zip(axes, mood_vec), key=lambda x: x[1], reverse=True)

    def bar_color(v):
        if v >= 0.6: return "#22c55e"   # green - strong
        if v >= 0.35: return "#eab308"  # yellow - moderate
        return "#64748b"                # grey - low

    for name, val in paired:
        pct = int(val * 100)
        color = bar_color(val)
        st.markdown(f"""
        <div style="display:flex; align-items:center; margin-bottom:8px;">
            <div style="width:110px; font-size:14px; text-transform:capitalize;">{name}</div>
            <div style="flex:1; background:#1e293b; border-radius:6px; height:22px; overflow:hidden; margin-right:10px;">
                <div style="width:{pct}%; background:{color}; height:100%; border-radius:6px; transition:width 0.3s;"></div>
            </div>
            <div style="width:45px; text-align:right; font-size:14px; font-weight:600;">{val:.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
# ============ TAB 2: CREATIVES ============
with tab2:
    if "upload_counter" not in st.session_state:
        st.session_state.upload_counter = 0
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
    st.subheader("📤 Upload Ad Image")
    uploaded = st.file_uploader(
        "Upload an ad creative (PNG/JPG)",
        type=["png", "jpg", "jpeg"],
        key=f"img_uploader_{st.session_state.upload_counter}",
    )
    if uploaded:
        st.image(uploaded, width=300)
        up_headline = st.text_input("Headline (optional)", key=f"img_headline_{st.session_state.upload_counter}")
        up_text = st.text_area("Caption/copy (optional)", key=f"img_text_{st.session_state.upload_counter}")
        if st.button("🔍 Analyze & Add"):
            import base64
            img_bytes = uploaded.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode()
            media = f"image/{uploaded.type.split('/')[-1]}"
            with st.spinner("Claude Vision analyzing the image..."):
                resp = httpx.post(f"{BASE}/creatives/image", json={
                    "client_id": selected_id,
                    "headline": up_headline,
                    "primary_text": up_text,
                    "image_base64": img_b64,
                    "media_type": media
                }, timeout=90)
            if resp.status_code == 200:
                result = resp.json()
                st.success("Image analyzed and added!")
                st.json(result["scores"])
                st.session_state.upload_counter += 1
                st.rerun()
            else:
                st.error(f"Error: {resp.text}")
    st.divider()
    st.subheader("Add Creative")
    with st.form("add_creative", clear_on_submit=True):
        headline = st.text_input("Headline")
        primary_text = st.text_area("Primary text")
        visual_desc = st.text_input("Visual description (optional)")
        submitted = st.form_submit_button("Score & Add")
        if submitted and primary_text:
            with st.spinner("Scoring creative (3 runs)..."):
                resp = httpx.post(f"{BASE}/creatives", json={
                    "client_id": selected_id, "headline": headline,
                    "primary_text": primary_text, "visual_description": visual_desc
                }, timeout=90)
            if resp.status_code == 200:
                result = resp.json()
                st.success(f"Scored! Urgency: {result['scores']['urgency']}, Belonging: {result['scores']['belonging']}")
                st.rerun()
            else:
                st.error(f"Error: {resp.text}")

# ============ TAB 3: MANUAL OVERRIDE ============
with tab3:
    st.subheader("🔧 Manual Override")
    st.caption("The daily loop fetches news/weather/calendar automatically. Use this only when you know something the feed doesn't — breaking news, a special event, or to test a hypothetical.")
    with st.form("manual_mood"):
        brief = st.text_area("Custom context brief", height=200,
                             placeholder="Paste a specific situation to score manually...")
        col1, col2, col3 = st.columns(3)
        with col1:
            name_day = st.slider("Name day boost", 0.0, 0.3, 0.0, 0.05)
        with col2:
            payday = st.slider("Payday window", 0.0, 0.3, 0.0, 0.05)
        with col3:
            holiday = st.slider("Holiday proximity", 0.0, 0.4, 0.0, 0.05)
        submitted = st.form_submit_button("Override Today's Mood")
        if submitted and brief:
            with st.spinner("Scoring custom mood..."):
                resp = httpx.post(f"{BASE}/mood/score", json={
                    "brief": brief,
                    "demand_inputs": {"name_day_boost": name_day, "payday_window": payday,
                                      "holiday_proximity": holiday}
                }, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                st.success(f"Mood overridden · demand index ×{result['demand_index']}")
                st.json(result["scores"])
                st.info("Go to Dashboard and the allocation will reflect this override.")
            else:
                st.error(f"Error: {resp.text}")

# ============ TAB 4: AUDIT ============
with tab4:
    st.subheader("📋 Audit Log")
    audit_resp = httpx.get(f"{BASE}/audit?limit=30")
    audit = audit_resp.json()
    if audit:
        for entry in audit:
            st.markdown(f"`{entry['ts'][:19]}` **{entry['event_type']}** — {entry['entity_type']} #{entry['entity_id']}")
    else:
        st.info("No audit entries yet.")
