from datetime import datetime, timedelta
from urllib.parse import urlparse

import plotly.express as px
import streamlit as st
import requests

from src import db
from src.config import get_discord_webhook, get_drop_threshold
from src.notifications import send_price_alert
from src.scraper import CustomScraper

st.set_page_config(page_title="Price Tracker", page_icon="🔮", layout="wide")
scraper = CustomScraper()

for k, v in {"last_check": None, "check_results": [], "page": "📊 Dashboard"}.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("""
<style>
    section[data-testid="stSidebar"] { background: #413735 !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.1) !important; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        display: flex !important; align-items: center !important; gap: 8px !important;
        padding: 6px 10px !important; border-radius: 6px !important;
        font-size: 0.875rem !important; cursor: pointer !important; color: #f5f0eb !important;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: rgba(255,255,255,0.08) !important; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] { background: #f43e01 !important; color: white !important; }
    section[data-testid="stSidebar"] .stTextInput input {
        background: rgba(255,255,255,0.08) !important; border: 1px solid rgba(255,255,255,0.15) !important;
        color: #2D2926 !important; border-radius: 6px !important;
    }
    section[data-testid="stSidebar"] .stTextInput input::placeholder { color: rgba(45,41,38,0.4) !important; }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] { background: #f43e01 !important; color: white !important; border: none !important; border-radius: 6px !important; }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] .stMarkdown { color: #f5f0eb !important; }
    .stButton button, .stLinkButton a { color: white !important; border: none !important; border-radius: 6px !important; }
    .stButton button[kind="primary"], .stLinkButton a { background: #f43e01 !important; }
    .stButton button[kind="secondary"] { background: #6B5B4F !important; color: white !important; }
    header[data-testid="stHeader"] button, header[data-testid="stHeader"] svg { color: #2D2926 !important; fill: #2D2926 !important; }
</style>
""", unsafe_allow_html=True)


def _run_check():
    products = db.get_all_products()
    if not products:
        st.session_state.check_results = []
        st.session_state.last_check = datetime.now()
        return

    threshold = get_drop_threshold()
    results = []
    bar = st.progress(0, text="Checking prices...")
    for i, p in enumerate(products):
        try:
            data = scraper.scrape_url(p["url"])["extract"]
            new_price = data["price"]
            history = db.get_price_history(p["url"])
            alert_data = {}
            if history:
                first_price = history[0]["price"]
                if first_price > new_price:
                    drop = (first_price - new_price) / first_price
                    if drop >= threshold:
                        send_price_alert(p["name"], first_price, new_price, p["url"])
                        alert_data = {"alert": True, "old_price": first_price, "new_price": new_price, "drop": drop * 100}
            name = data.get("name", p["name"])
            db.add_price_entry(p["url"], new_price, name)
            db.update_product(p["url"], new_price, name, data.get("currency", "USD"), data.get("main_image_url", ""))
            results.append({"name": name, "price": new_price} | alert_data)
        except Exception as e:
            results.append({"name": p.get("name", p["url"]), "error": str(e)})
        bar.progress((i + 1) / len(products), text=f"Checked {i + 1}/{len(products)}")
    bar.empty()
    st.session_state.check_results = results
    st.session_state.last_check = datetime.now()


def _show_dashboard():
    if st.session_state.check_results:
        alerts = [r for r in st.session_state.check_results if r.get("alert")]
        errors = [r for r in st.session_state.check_results if r.get("error")]
        ok = [r for r in st.session_state.check_results if not r.get("alert") and not r.get("error")]
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ OK", len(ok))
        c2.metric("🔔 Drops", len(alerts))
        c3.metric("❌ Errors", len(errors))
        for r in st.session_state.check_results:
            if r.get("alert"):
                st.warning(f"🚨 {r['name']} dropped {r['drop']:.1f}% — ${r['old_price']:.2f} → ${r['new_price']:.2f}")
            elif r.get("error"):
                st.error(f"❌ {r['name']} — {r['error']}")
            else:
                st.info(f"✅ {r['name']} — ${r['price']:.2f}")
        st.divider()

    st.subheader("📦 Tracked Products")
    products = db.get_all_products()
    if not products:
        st.info("No products tracked yet. Add one from the sidebar!")
        return

    for p in products:
        history = db.get_price_history(p["url"])
        latest_price = history[-1]["price"] if history else p["price"]
        currency = p.get("currency", "USD")
        prefix = "PKR " if currency == "PKR" else "$" if currency == "USD" else f"{currency} "

        drop_pct = None
        if history and latest_price < history[0]["price"]:
            drop_pct = (history[0]["price"] - latest_price) / history[0]["price"] * 100

        with st.container():
            cols = st.columns([1, 3, 2])
            if p.get("main_image_url"):
                cols[0].image(p["main_image_url"], width=64)
            else:
                cols[0].empty()
            with cols[1]:
                st.markdown(f"**{p['name'][:70]}**")
                badge = f"🔻 {drop_pct:.1f}%" if drop_pct else "✅ Stable"
                st.caption(f"{badge} · {currency}")
            with cols[2]:
                st.markdown(f"**{prefix}{latest_price:.2f}**")
                if history and len(history) >= 2:
                    diff = latest_price - history[-2]["price"]
                    if diff < 0:
                        st.markdown(f"📉 ${abs(diff):.2f}")
                    elif diff > 0:
                        st.markdown(f"📈 ${diff:.2f}")

            with st.expander("📊 Price History"):
                if history:
                    fig = px.line(history, x="timestamp", y="price")
                    fig.update_layout(height=180, margin=dict(l=0, r=0, t=4, b=0),
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    fig.update_traces(line=dict(color="#f43e01", width=2), fill="tozeroy", fillcolor="rgba(244,62,1,0.08)")
                    fig.update_yaxes(tickprefix=prefix)
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=f"chart_{p['url']}")
                else:
                    st.caption("No history yet")
            a, b = st.columns([1, 1])
            a.link_button("🔗 Visit", p["url"], use_container_width=True)
            if b.button("🗑️ Remove", key=f"rm_{p['url']}", use_container_width=True):
                db.delete_product(p["url"])
                st.rerun()
        st.divider()


def _show_settings():
    st.subheader("⚙️ Settings")

    st.markdown("**⏱ Price Checker**")
    db_interval = db.get_setting("check_interval", "Manual")
    vals = ["Manual", "1 hour", "2 hours", "4 hours", "6 hours", "12 hours", "24 hours"]
    idx = vals.index(db_interval) if db_interval in vals else 3
    interval = st.selectbox("Auto-check every", vals, index=idx, label_visibility="collapsed")
    db.set_setting("check_interval", interval)
    if st.button("🔍 Check Now", type="primary", use_container_width=True):
        _run_check()
    if st.session_state.last_check:
        st.caption(f"Last: {st.session_state.last_check.strftime('%Y-%m-%d %H:%M')}")
        if interval != "Manual":
            h = int(interval.split()[0])
            due = st.session_state.last_check + timedelta(hours=h)
            st.caption(f"Next: ~{due.strftime('%Y-%m-%d %H:%M')}")

    st.divider()

    st.markdown("**🔔 Alerts**")
    threshold = st.slider("Drop threshold (%)", 1, 50, int(get_drop_threshold() * 100), 1)
    db.set_setting("drop_threshold", threshold / 100)
    webhook = st.text_input("Discord Webhook URL", value=get_discord_webhook() or "",
                            placeholder="https://discord.com/api/webhooks/...", type="password")
    if webhook != get_discord_webhook():
        db.set_setting("discord_webhook_url", webhook)
        if webhook:
            st.success("✅ Webhook saved!")
        else:
            st.info("ℹ️ Webhook cleared — alerts disabled")
    if not webhook:
        st.caption("⚠️ No webhook — Discord alerts disabled")
    else:
        st.caption("✅ Discord alerts active")

    st.divider()

    st.markdown("**ℹ️ About**")
    products = db.get_all_products()
    st.markdown(f"- Tracked products: {len(products)}")
    st.markdown(f"- With price history: {sum(1 for p in products if db.get_price_history(p['url']))}")
    if st.button("🗑️ Reset All Data", type="secondary", use_container_width=True):
        db.reset_all()
        st.session_state.check_results = []
        st.session_state.last_check = None
        st.rerun()


def _show_test():
    st.subheader("🧪 Test Mode")
    webhook = get_discord_webhook()

    st.markdown("**Send Test Notification**")
    if not webhook:
        st.warning("No Discord webhook configured. Go to Settings > Alerts to add one.")
    else:
        if st.button("📨 Send Test Discord Alert", type="primary", use_container_width=True):
            try:
                r = requests.post(webhook, json={
                    "embeds": [{
                        "title": "🧪 Test Notification",
                        "description": "**Price Tracker Test**\n\nIf you see this, Discord alerts are working!\nYour webhook is configured correctly.",
                        "color": 15258703,
                        "footer": {"text": "Price Tracker · Test Mode"}
                    }]
                }, timeout=10)
                if r.ok:
                    st.success("✅ Test notification sent! Check your Discord channel.")
                else:
                    st.error(f"❌ Discord returned {r.status_code}: {r.text}")
            except Exception as e:
                st.error(f"❌ Failed: {e}")

    st.divider()
    st.markdown("**📋 Discord Setup Guide**")
    st.markdown("""
Follow these steps to get Discord alerts:

**Step 1 — Open Discord**
- Go to your Discord server (or create one)

**Step 2 — Create Webhook**
- Right-click the **channel** where you want alerts
- Click **Edit Channel** → **Integrations** → **Webhooks**
- Click **Create Webhook**

**Step 3 — Configure**
- Give it a name (e.g. "Price Tracker")
- (Optional) Set a profile picture
- Click **Copy Webhook URL**

**Step 4 — Add to Price Tracker**
- Go to **Settings** → **Alerts**
- Paste the copied URL into the **Discord Webhook URL** field
- It saves automatically

**Step 5 — Test**
- Come back to this **Test** page
- Click **Send Test Discord Alert**
- Check your Discord channel for the test message

That's it! You'll now get notified when tracked products drop in price.
""")


st.markdown("""
<div style="background:white;border:1px solid #E5DDD5;border-radius:10px;padding:1.2rem 1rem;margin:-0.3rem 0 1.2rem;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <h1 style="margin:0;font-size:1.4rem;font-weight:600;color:#2D2926;">🔮 Price Tracker</h1>
    <p style="margin:0.2rem 0 0;font-size:0.8rem;color:#6B5B4F;">Track prices across e-commerce sites · Get alerts on drops</p>
</div>
""", unsafe_allow_html=True)

PAGES = ["📊 Dashboard", "⚙️ Settings", "🧪 Test"]
with st.sidebar:
    page = st.radio("", PAGES, label_visibility="collapsed",
                     index=PAGES.index(st.session_state.page) if st.session_state.page in PAGES else 0)
    if page != st.session_state.page:
        st.session_state.page = page
        st.rerun()

    if page == "📊 Dashboard":
        st.divider()
        st.markdown("**➕ Add Product**")
        new_url = st.text_input("URL", placeholder="https://...", label_visibility="collapsed")
        if st.button("➕ Add Product", use_container_width=True) and new_url:
            parsed = urlparse(new_url)
            if not all([parsed.scheme, parsed.netloc]):
                st.error("Invalid URL")
            elif db.get_product(new_url):
                st.error("Already tracked!")
            else:
                with st.spinner("Scraping..."):
                    try:
                        data = scraper.scrape_url(new_url)["extract"]
                        db.add_product(new_url, data["name"], data["price"],
                                       data.get("currency", "USD"), data.get("main_image_url", ""), "")
                        db.add_price_entry(new_url, data["price"], data["name"])
                        st.success(f"Added {data['name'][:30]}...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

        st.divider()
        st.markdown("**⏱ Quick Check**")
        if st.button("🔍 Check Now", type="primary", use_container_width=True):
            _run_check()
        if st.session_state.last_check:
            st.caption(f"Last: {st.session_state.last_check.strftime('%H:%M, %b %d')}")
            db_interval = db.get_setting("check_interval", "Manual")
            if db_interval != "Manual":
                h = int(db_interval.split()[0])
                due = st.session_state.last_check + timedelta(hours=h)
                st.caption(f"Next: ~{due.strftime('%H:%M, %b %d')}")

# Auto-check
db_interval = db.get_setting("check_interval", "Manual")
if db_interval != "Manual" and st.session_state.last_check:
    h = int(db_interval.split()[0])
    if datetime.now() - st.session_state.last_check >= timedelta(hours=h):
        _run_check()

if page == "📊 Dashboard":
    _show_dashboard()
elif page == "⚙️ Settings":
    _show_settings()
else:
    _show_test()
