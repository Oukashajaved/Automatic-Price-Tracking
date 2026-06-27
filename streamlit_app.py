from datetime import datetime, timedelta
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import requests

from src import db
from src.ai_search_service import AISearchService
from src.config import get_discord_webhook, get_drop_threshold, get_groq_api_key
from src.scraper import CustomScraper

st.set_page_config(page_title="Price Tracker", layout="wide")
scraper = CustomScraper()

st.session_state.setdefault("last_check", None)

st.markdown("""<style>
    section[data-testid="stSidebar"] { background: #F0ECEA !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(0,0,0,0.06) !important; }
    section[data-testid="stSidebar"] .stTextInput input { background: white !important; border: 1px solid #D5CFC8 !important; border-radius: 6px !important; outline: none !important; box-shadow: none !important; }
    section[data-testid="stSidebar"] .stTextInput input:focus { outline: none !important; box-shadow: none !important; border-color: #A78BFA !important; }
    section[data-testid="stSidebar"] .stTextInput input::placeholder { color: rgba(45,41,38,0.3) !important; }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] .stMarkdown { color: #4A4458 !important; }
    section[data-testid="stSidebar"] .stButton button[kind="secondary"] { background: transparent !important; color: #A78BFA !important; border: 1px solid #A78BFA !important; border-radius: 6px !important; }
    section[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover { background: rgba(167,139,250,0.08) !important; }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] { background: #A78BFA !important; color: white !important; border-radius: 6px !important; }
    section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover { background: #9578E8 !important; }
    .stButton button[kind="secondary"] { background: transparent !important; color: #EF4444 !important; border: 1px solid #EF4444 !important; border-radius: 6px !important; }
    .stButton button[kind="secondary"]:hover { background: #FEF2F2 !important; }
    .stButton button[kind="primary"] { background: #A78BFA !important; border-radius: 6px !important; }
    .stButton button[kind="primary"]:hover { background: #9578E8 !important; }
    .stLinkButton a { background: transparent !important; color: #A78BFA !important; border: 1px solid #A78BFA !important; border-radius: 6px !important; }
    .stLinkButton a:hover { background: rgba(167,139,250,0.08) !important; }
    div[data-testid="stMetric"] { background: #F5F3FF; padding: 8px 12px; border-radius: 8px; }
    div[data-testid="stMetric"] label { color: #6B5B4F !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #2D2926 !important; }
</style>""", unsafe_allow_html=True)


def _run_check():
    from src.check_prices import check_prices  # ponytail: lazy import avoids circular dep at module level
    results = check_prices()
    st.session_state.last_check = datetime.now()


def _show_dashboard():
    c1, c2 = st.columns([6, 1])
    c1.subheader("Tracked Products")
    if c2.button("Check Now", type="primary", use_container_width=True, key="cd"):
        _run_check()
    products = db.get_all_products()
    if not products:
        st.info("No products tracked yet. Add one from the sidebar!")
        return

    df = pd.DataFrame(products)

    if "comparison_group" in df.columns:
        grouped_df = df[df["comparison_group"].notna() & (df["comparison_group"] != "")]
        ungrouped_df = df[df["comparison_group"].isna() | (df["comparison_group"] == "")]
    else:
        grouped_df, ungrouped_df = pd.DataFrame(), df

    if not grouped_df.empty:
        st.markdown("### Price Comparison Groups")
        for group_name, group_products in grouped_df.groupby("comparison_group"):
            with st.expander(f"Group: {group_name}", expanded=True):
                ai_service = AISearchService()
                products_list = group_products.sort_values("price").to_dict("records")
                g_tab_products, g_tab_charts, g_tab_ai = st.tabs(["Products", "Price Charts", "Chat"])

                with g_tab_products:
                    recommendation = ai_service.generate_recommendation(group_name, products_list)
                    if recommendation:
                        st.info(f"**AI Tip:** {recommendation}")

                    cheapest_url = min(products_list, key=lambda x: x["price"])["url"]

                    for p_row in products_list:
                        domain = urlparse(p_row["url"]).netloc.replace("www.", "")
                        is_cheapest = p_row["url"] == cheapest_url
                        prefix = "Cheapest — " if is_cheapest else ""

                        h = db.get_price_history(p_row["url"])
                        latest_price = h[-1]["price"] if h else p_row["price"]
                        curr = p_row.get("currency", "USD")
                        fmt = "PKR " if curr == "PKR" else "$" if curr == "USD" else f"{curr} "

                        drop_pct = None
                        if h and latest_price < h[0]["price"]:
                            drop_pct = (h[0]["price"] - latest_price) / h[0]["price"] * 100

                        cols = st.columns([1, 3, 2])
                        if p_row.get("main_image_url"):
                            cols[0].image(p_row["main_image_url"], width=80)
                        cols[1].markdown(f"**{prefix}{p_row['name']}**")
                        badge = f"Down {drop_pct:.1f}%" if drop_pct else "Stable"
                        cols[1].caption(f"**{domain}** · {badge}")
                        cols[2].markdown(f"**{fmt}{latest_price:.2f}**")
                        cols[2].link_button("Visit", p_row["url"], use_container_width=True)
                        if cols[2].button("Remove", key=f"rm_g_{p_row['url']}", use_container_width=True):
                            db.delete_product(p_row["url"])
                            st.rerun()
                        st.divider()

                with g_tab_charts:
                    histories = []
                    for _, row in group_products.iterrows():
                        domain = urlparse(row["url"]).netloc.replace("www.", "")
                        for entry in db.get_price_history(row["url"]):
                            histories.append({
                                "ts": entry["timestamp"],
                                "price": entry["price"],
                                "store": f"{row['name'][:25]} ({domain})"
                            })

                    if histories:
                        dfh = pd.DataFrame(histories)
                        dfh["ts"] = pd.to_datetime(dfh["ts"])
                        dfh = dfh.pivot_table(index="ts", columns="store", values="price", aggfunc="first").ffill()
                        st.area_chart(dfh, height=350, use_container_width=True)
                    else:
                        st.caption("No price history yet for this group.")

                with g_tab_ai:
                    if "chat_history" not in st.session_state:
                        st.session_state.chat_history = {}
                    if group_name not in st.session_state.chat_history:
                        st.session_state.chat_history[group_name] = []

                    chat_container = st.container(height=350)
                    with chat_container:
                        for msg in st.session_state.chat_history[group_name]:
                            with st.chat_message(msg["role"]):
                                st.write(msg["content"])

                    if user_msg := st.chat_input("Ask about price trends or store comparisons..."):
                        st.session_state.chat_history[group_name].append({"role": "user", "content": user_msg})
                        with chat_container:
                            with st.chat_message("user"):
                                st.write(user_msg)

                        histories_dict = {row["url"]: db.get_price_history(row["url"]) for _, row in group_products.iterrows()}

                        with chat_container:
                            with st.chat_message("assistant"):
                                with st.spinner(""):
                                    response = ai_service.generate_chat_response(
                                        group_name=group_name, products=products_list,
                                        histories=histories_dict, user_message=user_msg,
                                        chat_history=st.session_state.chat_history[group_name][:-1]
                                    )
                                st.write(response)
                        st.session_state.chat_history[group_name].append({"role": "assistant", "content": response})

    if not ungrouped_df.empty:
        st.markdown("### Individual Products")
        for _, p in ungrouped_df.iterrows():
            history = db.get_price_history(p["url"])
            latest_price = history[-1]["price"] if history else p["price"]
            curr = p.get("currency", "USD")
            fmt = "PKR " if curr == "PKR" else "$" if curr == "USD" else f"{curr} "

            ca, cb = st.columns([4, 1])
            with ca:
                cols = st.columns([1, 3, 1])
                if p.get("main_image_url"):
                    cols[0].image(p["main_image_url"], width=50)
                cols[1].markdown(f"**{p['name'][:50]}**")
                cols[2].markdown(f"**{fmt}{latest_price:.2f}**")
            with cb:
                st.link_button("Visit", p["url"], use_container_width=True)
                if st.button("Remove", key=f"rm_{p['url']}", use_container_width=True):
                    db.delete_product(p["url"])
                    st.rerun()


def _show_settings():
    st.subheader("Settings")

    st.markdown("**Price Checker**")
    db_interval = db.get_setting("check_interval", "Manual")
    vals = ["Manual", "1 hour", "2 hours", "4 hours", "6 hours", "12 hours", "24 hours"]
    idx = vals.index(db_interval) if db_interval in vals else 3
    interval = st.selectbox("Auto-check every", vals, index=idx, label_visibility="collapsed")
    db.set_setting("check_interval", interval)
    if st.button("Check Now", type="primary", width="stretch"):
        _run_check()
    if st.session_state.last_check:
        st.caption(f"Last: {st.session_state.last_check.strftime('%Y-%m-%d %H:%M')}")
        if interval != "Manual":
            h = int(interval.split()[0])
            due = st.session_state.last_check + timedelta(hours=h)
            st.caption(f"Next: ~{due.strftime('%Y-%m-%d %H:%M')}")

    st.divider()

    st.markdown("**AI Config**")
    groq_key = st.text_input("Groq API Key", value=get_groq_api_key() or "",
                             placeholder="gsk_...", type="password")
    if groq_key != get_groq_api_key():
        db.set_setting("groq_api_key", groq_key)
        if groq_key:
            st.success("Groq API Key saved!")
            st.rerun()
        else:
            st.info("Groq API Key cleared")
            st.rerun()

    st.divider()

    st.markdown("**Alerts**")
    threshold = st.slider("Drop threshold (%)", 1, 50, int(get_drop_threshold() * 100), 1)
    db.set_setting("drop_threshold", threshold / 100)
    webhook = st.text_input("Discord Webhook URL", value=get_discord_webhook() or "",
                            placeholder="https://discord.com/api/webhooks/...", type="password")
    if webhook != get_discord_webhook():
        db.set_setting("discord_webhook_url", webhook)
        if webhook:
            st.success("Webhook saved!")
        else:
            st.info("Webhook cleared — alerts disabled")
    if not webhook:
        st.caption("No webhook — Discord alerts disabled")
    else:
        st.caption("Discord alerts active")

    st.divider()

    st.markdown("**Test**")
    if get_discord_webhook():
        if st.button("Send Test Discord Alert", type="primary", use_container_width=True):
            try:
                r = requests.post(get_discord_webhook(), json={
                    "embeds": [{"title": "Test", "description": "Price Tracker alert working!", "color": 3066993}]
                }, timeout=10)
                st.success("Test sent!") if r.ok else st.error(f"HTTP {r.status_code}")
            except Exception as e:
                st.error(str(e))

    st.markdown("**About**")
    products = db.get_all_products()
    st.markdown(f"- Tracked products: {len(products)}")
    st.markdown(f"- With price history: {sum(1 for p in products if db.get_price_history(p['url']))}")
    if st.button("Reset All Data", type="secondary", width="stretch"):
        db.reset_all()
        st.session_state.last_check = None
        st.rerun()


st.markdown("<h1 style='text-align:center;color:#2D2926;font-size:1.5rem'>🏷️ Price Tracker</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("**Search & Add**")
    search_q = st.text_input("Search", placeholder="e.g. iPhone 15", label_visibility="collapsed", key="sq")
    group_search = st.text_input("Group name", placeholder="e.g. phones", label_visibility="collapsed", key="gs")
    if st.button("Search & Add", type="secondary", use_container_width=True, key="sb"):
        if search_q:
            g = group_search or search_q
            with st.spinner(""):
                try:
                    items = AISearchService().search_google_products(search_q)
                    if not items:
                        st.error("No products found.")
                    else:
                        n = 0
                        for it in items:
                            if not db.get_product(it["url"]):
                                db.add_product(it["url"], it["name"], it["price"],
                                    it.get("currency", "USD"), it.get("main_image_url", ""),
                                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), g)
                                db.add_price_entry(it["url"], it["price"], it["name"])
                                n += 1
                        st.success(f"Added {n} product(s) to '{g}'") if n else st.warning("Already tracked.")
                        if n:
                            st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()

    st.markdown("**Add URL**")
    url_in = st.text_input("URL", placeholder="https://...", label_visibility="collapsed", key="au")
    group_url = st.text_input("Group name", placeholder="e.g. phones", label_visibility="collapsed", key="gu")
    if st.button("Add URL", type="secondary", use_container_width=True, key="ab"):
        if url_in and group_url:
            if db.get_product(url_in):
                st.error("Already tracked!")
            else:
                with st.spinner(""):
                    try:
                        data = scraper.scrape_url(url_in)["extract"]
                        db.add_product(url_in, data["name"], data["price"],
                            data.get("currency", "USD"), data.get("main_image_url", ""),
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), group_url)
                        db.add_price_entry(url_in, data["price"], data["name"])
                        st.success(f"Added {data['name'][:30]}...")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        elif not group_url:
            st.error("Enter a group name.")

db_interval = db.get_setting("check_interval", "Manual")
if db_interval != "Manual" and st.session_state.last_check:
    h = int(db_interval.split()[0])
    if datetime.now() - st.session_state.last_check >= timedelta(hours=h):
        _run_check()

tab_dashboard, tab_settings = st.tabs(["Dashboard", "Settings"])

with tab_dashboard:
    _show_dashboard()

with tab_settings:
    _show_settings()
