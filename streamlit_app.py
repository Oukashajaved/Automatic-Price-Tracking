import math
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import requests

from src import db
from src.ai_service import AIService
from src.config import get_discord_webhook, get_drop_threshold, get_groq_api_key
from src.scraper import CustomScraper
from src.site_scrapers import available_sites, search_all

st.set_page_config(page_title="Universal Price Tracker", layout="wide")
scraper = CustomScraper()
ai_service = AIService()

st.session_state.setdefault("last_check", None)
st.session_state.setdefault("chat_history", [])

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
    from src.check_prices import check_prices
    check_prices()
    st.session_state.last_check = datetime.now()


def _analytics_for_products(products: list[dict]):
    prices = [p["price"] for p in products if p["price"] > 0]
    if not prices:
        return {}
    n = len(prices)
    mean = sum(prices) / n
    variance = sum((x - mean) ** 2 for x in prices) / n
    std = math.sqrt(variance)
    mn, mx = min(prices), max(prices)
    threshold_2sigma = mean + 2 * std
    outliers = [p for p in products if p["price"] > 0 and abs(p["price"] - mean) > 2 * std]
    fraud_flags = [p for p in products if p["price"] > 0 and p["price"] < mean * 0.2]
    return {
        "n": n, "mean": mean, "std": std, "min": mn, "max": mx,
        "outliers": outliers, "fraud_flags": fraud_flags,
        "threshold_2sigma": threshold_2sigma,
    }


def _group_filter_ui(group_name: str):
    key = f"gf_{group_name}"
    with st.popover("Filters", key=f"fp_{group_name}"):
        price_range = st.slider("Price range", 0.0, 10000.0, (0.0, 10000.0), key=f"{key}_pr")
        sellers = st.multiselect("Sellers", [], key=f"{key}_se", placeholder="All sellers")
        show_outliers = st.checkbox("Show outliers only", False, key=f"{key}_so")
        sort_by = st.selectbox("Sort by", ["Price (low)", "Price (high)", "Name", "Site"], key=f"{key}_sb")
    return {"price_range": price_range, "sellers": sellers, "show_outliers": show_outliers, "sort_by": sort_by}


def _show_dashboard():
    c1, c2 = st.columns([6, 1])
    c1.subheader("Tracked Products Dashboard")
    if c2.button("Check Now", type="primary", width="stretch", key="cd"):
        _run_check()
        
    products = db.get_all_products()
    if not products:
        st.info("No products tracked yet. Search or add a URL from the sidebar!")
        return

    df = pd.DataFrame(products)

    if "comparison_group" in df.columns:
        grouped_df = df[df["comparison_group"].notna() & (df["comparison_group"] != "")]
        ungrouped_df = df[df["comparison_group"].isna() | (df["comparison_group"] == "")]
    else:
        grouped_df, ungrouped_df = pd.DataFrame(), df

    all_groups = sorted(grouped_df["comparison_group"].unique()) if not grouped_df.empty else []

    fc1, fc2 = st.columns([2, 1])
    with fc1:
        sel_groups = st.multiselect("Group filter", all_groups + (["Ungrouped"] if not ungrouped_df.empty else []),
                                    default=all_groups + (["Ungrouped"] if not ungrouped_df.empty else []), key="fg")
    with fc2:
        threshold = st.slider("Alert on drop (%)", 1, 50, int(get_drop_threshold() * 100), 1, key="dt")
        db.set_setting("drop_threshold", threshold / 100)

    group_filter = [g for g in sel_groups if g != "Ungrouped"]
    show_ungrouped = "Ungrouped" in sel_groups

    if group_filter:
        grouped_df = grouped_df[grouped_df["comparison_group"].isin(group_filter)]
    if not show_ungrouped:
        ungrouped_df = pd.DataFrame()

    if not grouped_df.empty:
        st.markdown("### Comparison Groups")
        for group_name, group_products in grouped_df.groupby("comparison_group"):
            with st.expander(f"Group: {group_name}", expanded=True):
                products_list = group_products.sort_values("price").to_dict("records")
                analytics = _analytics_for_products(products_list)

                if analytics:
                    a_cols = st.columns(5)
                    a_cols[0].metric("Products", analytics["n"])
                    a_cols[1].metric("Mean", f"${analytics['mean']:.2f}")
                    a_cols[2].metric("Std Dev", f"${analytics['std']:.2f}")
                    a_cols[3].metric("Min", f"${analytics['min']:.2f}")
                    a_cols[4].metric("Max", f"${analytics['max']:.2f}")

                    if analytics["outliers"]:
                        outlier_names = ", ".join(p["name"][:30] for p in analytics["outliers"][:3])
                        st.warning(f"Outliers (2σ): {outlier_names}{'...' if len(analytics['outliers']) > 3 else ''}")
                    if analytics["fraud_flags"]:
                        fraud_names = ", ".join(p["name"][:30] for p in analytics["fraud_flags"][:3])
                        st.error(f"Fraud flags: {fraud_names}")

                filters = _group_filter_ui(group_name)
                reco = ai_service.generate_recommendation(group_name, products_list)
                if reco:
                    st.info(f"**AI Tip:** {reco}")

                g_tab_products, g_tab_charts, g_tab_data = st.tabs(["Products", "Charts", "Data"])

                with g_tab_products:
                    filtered = list(products_list)
                    if filters["price_range"] != (0.0, 10000.0):
                        lo, hi = filters["price_range"]
                        filtered = [p for p in filtered if lo <= p["price"] <= hi]
                    if filters["sellers"]:
                        filtered = [p for p in filtered if p.get("seller", "") in filters["sellers"]]
                    if filters["show_outliers"] and analytics:
                        outlier_urls = {p["url"] for p in analytics["outliers"]}
                        filtered = [p for p in filtered if p["url"] in outlier_urls]
                    
                    sort_map = {"Price (low)": ("price", True), "Price (high)": ("price", False),
                                "Name": ("name", True), "Site": ("site", True)}
                    skey, srev = sort_map.get(filters["sort_by"], ("price", True))
                    filtered = sorted(filtered, key=lambda x: x.get(skey, ""), reverse=not srev)

                    cheapest_url = min(filtered, key=lambda x: x["price"])["url"] if filtered else ""

                    for p_row in filtered:
                        domain = urlparse(p_row["url"]).netloc.replace("www.", "")
                        is_cheapest = p_row["url"] == cheapest_url
                        prefix = "🏆 " if is_cheapest else ""

                        h = db.get_price_history(p_row["url"])
                        latest_price = h[-1]["price"] if h else p_row["price"]
                        curr = p_row.get("currency", "USD")
                        fmt = "PKR " if curr == "PKR" else "$" if curr == "USD" else f"{curr} "

                        drop_pct = None
                        if h and latest_price < h[0]["price"]:
                            drop_pct = (h[0]["price"] - latest_price) / h[0]["price"] * 100

                        # Multi-image list extraction
                        images_list = []
                        try:
                            images_list = json.loads(p_row.get("images", "[]"))
                        except:
                            pass
                        if not images_list and p_row.get("main_image_url"):
                            images_list = [p_row["main_image_url"]]

                        card_cols = st.columns([1.5, 4, 1.5])
                        
                        # Images column
                        with card_cols[0]:
                            if images_list:
                                st.image(images_list[0], width=110)
                                if len(images_list) > 1:
                                    st.image(images_list[1:5], width=24)
                            else:
                                st.caption("No Image")
                        
                        # Details column
                        with card_cols[1]:
                            st.markdown(f"**{prefix}{p_row['name']}**")
                            if p_row.get("brand"):
                                st.markdown(f"**Brand:** `{p_row['brand']}`")
                                
                            # Stars & Rating
                            r_val = float(p_row.get("rating", 0.0))
                            r_count = int(p_row.get("review_count", 0))
                            if r_val > 0:
                                stars = "★" * int(round(r_val)) + "☆" * (5 - int(round(r_val)))
                                st.markdown(f"⭐ **{r_val:.1f}/5** ({r_count} reviews) · {stars}")
                            
                            site_tag = p_row.get('site', domain)
                            badge = f"📉 {drop_pct:.1f}%" if drop_pct else "Stable"
                            seller_tag = p_row.get('seller', '')
                            ship_tag = p_row.get('shipping', '')
                            cond_tag = p_row.get('condition', 'New')
                            
                            st.markdown(
                                f"🏷️ **Store:** `{site_tag}` &nbsp;&nbsp;|&nbsp;&nbsp; 🏪 **Seller:** `{seller_tag or 'Direct'}`  \n"
                                f"📦 **Shipping:** `{ship_tag or 'Calculated'}` &nbsp;&nbsp;|&nbsp;&nbsp; ✨ **Condition:** `{cond_tag}`"
                            )
                            
                            # Specs & Description
                            desc = p_row.get("description", "")
                            specs_dict = {}
                            try:
                                specs_dict = json.loads(p_row.get("specs", "{}"))
                            except:
                                pass
                                
                            if desc or specs_dict:
                                with st.expander("Details & Specs"):
                                    if desc:
                                        st.markdown(f"**Description:**  \n{desc[:300]}{'...' if len(desc) > 300 else ''}")
                                    if specs_dict:
                                        st.markdown("**Specifications:**")
                                        st.table(pd.DataFrame(specs_dict.items(), columns=["Spec", "Value"]).set_index("Spec"))
                        
                        # Price/Actions column
                        with card_cols[2]:
                            st.markdown(f"### {fmt}{latest_price:.2f}")
                            st.link_button("Visit Site", p_row["url"], width="stretch")
                            if st.button("Remove", key=f"rm_g_{p_row['url']}", width="stretch"):
                                db.delete_product(p_row["url"])
                                st.rerun()
                        
                        st.divider()

                with g_tab_charts:
                    histories = []
                    for _, row in group_products.iterrows():
                        domain = urlparse(row["url"]).netloc.replace("www.", "")
                        site_tag = row.get("site", domain)
                        for entry in db.get_price_history(row["url"]):
                            histories.append({
                                "ts": entry["timestamp"],
                                "price": entry["price"],
                                "store": f"{row['name'][:20]} ({site_tag})"
                            })

                    dfh = pd.DataFrame(histories)
                    if not dfh.empty:
                        dfh["ts"] = pd.to_datetime(dfh["ts"])
                        pivot = dfh.pivot_table(index="ts", columns="store", values="price", aggfunc="first")

                        ct1, ct2, ct3 = st.tabs(["Line", "Bar", "Scatter"])
                        with ct1:
                            st.line_chart(pivot, height=350)
                        with ct2:
                            latest_prices = group_products.to_dict('records')
                            for lp in latest_prices:
                                ph = db.get_price_history(lp["url"])
                                lp["latest_price"] = ph[-1]["price"] if ph else lp["price"]
                            bar_df = pd.DataFrame(latest_prices)
                            if not bar_df.empty:
                                bar_df["label"] = bar_df.apply(
                                    lambda r: f"{r['name'][:15]} ({r.get('site', urlparse(r['url']).netloc.replace('www.', ''))[:10]})", axis=1)
                                st.bar_chart(bar_df.set_index("label")["latest_price"], height=350)
                        with ct3:
                            all_prices = []
                            for _, row in group_products.iterrows():
                                domain = urlparse(row["url"]).netloc.replace("www.", "")
                                site_tag = row.get("site", domain)
                                for entry in db.get_price_history(row["url"]):
                                    all_prices.append({
                                        "price": entry["price"],
                                        "product": f"{row['name'][:15]} ({site_tag})",
                                        "timestamp": entry["timestamp"],
                                    })
                            if all_prices:
                                sc_df = pd.DataFrame(all_prices)
                                sc_df["timestamp"] = pd.to_datetime(sc_df["timestamp"])
                                st.scatter_chart(sc_df, x="timestamp", y="price", color="product", height=350)
                    else:
                        st.info("Run a price check to see charts.")

                with g_tab_data:
                    data_rows = []
                    for p_row in products_list:
                        ph = db.get_price_history(p_row["url"])
                        latest_price = ph[-1]["price"] if ph else p_row["price"]
                        data_rows.append({
                            "Name": p_row["name"][:40],
                            "Site": p_row.get("site", ""),
                            "Brand": p_row.get("brand", ""),
                            "Seller": p_row.get("seller", ""),
                            "Price": latest_price,
                            "Currency": p_row.get("currency", "USD"),
                            "Condition": p_row.get("condition", ""),
                            "Shipping": p_row.get("shipping", ""),
                            "Rating": p_row.get("seller_rating", ""),
                            "Reviews": p_row.get("review_count", 0),
                        })
                    if data_rows:
                        st.dataframe(pd.DataFrame(data_rows), width="stretch", hide_index=True)

    if not ungrouped_df.empty:
        st.markdown("### Individual Products")
        for _, p in ungrouped_df.iterrows():
            history = db.get_price_history(p["url"])
            latest_price = history[-1]["price"] if history else p["price"]
            curr = p.get("currency", "USD")
            fmt = "PKR " if curr == "PKR" else "$" if curr == "USD" else f"{curr} "

            ca, cb = st.columns([4, 1.5])
            with ca:
                cols = st.columns([1, 4])
                if p.get("main_image_url"):
                    cols[0].image(p["main_image_url"], width=60)
                cols[1].markdown(f"**{p['name']}**")
                cols[1].caption(f"Domain: `{urlparse(p['url']).netloc}`")
            with cb:
                st.markdown(f"#### {fmt}{latest_price:.2f}")
                st.link_button("Visit Site", p["url"], width="stretch")
                if st.button("Remove", key=f"rm_{p['url']}", width="stretch"):
                    db.delete_product(p["url"])
                    st.rerun()
            st.divider()

    st.divider()
    st.markdown("### Global AI Assistant")
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    if user_msg := st.chat_input("Ask about prices, trends, or comparisons...", key="gci"):
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with chat_container:
            with st.chat_message("user"):
                st.write(user_msg)

        all_prods = db.get_all_products()
        context_lines = []
        for p in all_prods:
            store = urlparse(p["url"]).netloc.replace("www.", "")
            site = p.get("site", store)
            group = p.get("comparison_group", "Ungrouped")
            ph = db.get_price_history(p["url"])
            if ph:
                low = min(e["price"] for e in ph)
                high = max(e["price"] for e in ph)
                latest = ph[-1]["price"]
                history_summary = f" (range ${low:.2f}-${high:.2f}, latest ${latest:.2f})"
            else:
                history_summary = ""
            context_lines.append(f"- [{group}] {p['name']} at {site}: ${p['price']:.2f}{history_summary}")
        context = "\n".join(context_lines)

        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = ai_service.generate_chat_response(
                        context=context,
                        user_message=user_msg,
                        chat_history=st.session_state.chat_history[:-1]
                    )
                st.write(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})


def _show_test():
    st.subheader("Test Discord Alerts")
    webhook = get_discord_webhook()
    if not webhook:
        st.warning("No Discord webhook configured. Add one in Settings.")
        return
    if st.button("Send Test Alert", type="primary", width="stretch"):
        try:
            r = requests.post(webhook, json={
                "embeds": [{"title": "Test Alert", "description": "Universal Price Tracker alert working!", "color": 10980346}]
            }, timeout=10)
            st.success("Sent! Check Discord.") if r.ok else st.error(f"HTTP {r.status_code}")
        except Exception as e:
            st.error(str(e))


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
        st.caption(f"Last checked: {st.session_state.last_check.strftime('%Y-%m-%d %H:%M')}")
        if interval != "Manual":
            h = int(interval.split()[0])
            due = st.session_state.last_check + timedelta(hours=h)
            st.caption(f"Next check: ~{due.strftime('%Y-%m-%d %H:%M')}")

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
    webhook = st.text_input("Discord Webhook URL", value=get_discord_webhook() or "",
                            placeholder="https://discord.com/api/webhooks/...", type="password")
    if webhook != get_discord_webhook():
        db.set_setting("discord_webhook_url", webhook)
        if webhook:
            st.success("Webhook saved!")
        else:
            st.info("Webhook cleared alerts disabled")
    if not webhook:
        st.caption("No webhook. Discord alerts disabled.")
    else:
        st.caption("Discord alerts active.")

    st.divider()

    st.markdown("**About**")
    products = db.get_all_products()
    st.markdown(f"- Tracked products: {len(products)}")
    st.markdown(f"- With price history: {sum(1 for p in products if db.get_price_history(p['url']))}")
    if st.button("Reset All Data", type="secondary", width="stretch"):
        db.reset_all()
        st.session_state.last_check = None
        st.rerun()


st.markdown("<h1 style='text-align:center;color:#2D2926;font-size:1.5rem'>Universal Price Tracker</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("**Search & Scrape**")
    search_q = st.text_input("Product Search Term", placeholder="e.g. RTX 4090", label_visibility="collapsed", key="sq")
    pages = st.slider("Pages per site", 1, 5, 1, key="sp")
    
    selected_sites = st.multiselect("Predefined Sites", available_sites(), default=["eBay", "Newegg"], key="ss")
    custom_domains_input = st.text_input("Custom Domains (comma-separated)", placeholder="e.g. bhphotovideo.com, target.com", key="cdi")
    
    if st.button("Search & Track", type="primary", width="stretch", key="sb"):
        if search_q:
            custom_domains = [d.strip() for d in custom_domains_input.split(",") if d.strip()]
            group_s = search_q.strip()
            
            with st.status("Initializing search...", expanded=True) as status_box:
                def update_progress(msg):
                    status_box.update(label=msg)
                    st.write(f"- {msg}")
                
                total = 0
                all_items = search_all(
                    search_q,
                    sites=selected_sites,
                    custom_domains=custom_domains,
                    max_pages=pages,
                    progress_callback=update_progress
                )
                
                if not all_items:
                    status_box.update(label="No products found!", state="error")
                    st.error("No products found on those sites. Check spelling or try custom domains.")
                else:
                    status_box.update(label="Parsing results...", state="running")
                    for site_name, items in all_items.items():
                        for it in items:
                            if not db.get_product(it["url"]):
                                db.add_product(
                                    url=it["url"],
                                    name=it["name"],
                                    price=it["price"],
                                    currency=it.get("currency", "USD"),
                                    main_image_url=it.get("main_image_url", ""),
                                    check_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    comparison_group=group_s,
                                    seller=it.get("seller", ""),
                                    seller_rating=it.get("seller_rating", "0.0"),
                                    review_count=it.get("review_count", 0),
                                    condition=it.get("condition", "New"),
                                    shipping=it.get("shipping", ""),
                                    site=it.get("site", ""),
                                    images=it.get("images", "[]"),
                                    brand=it.get("brand", ""),
                                    rating=float(it.get("seller_rating", 0.0)),
                                    description=it.get("description", ""),
                                    specs=it.get("specs", "{}")
                                )
                                db.add_price_entry(it["url"], it["price"], it["name"])
                                total += 1
                    
                    if total:
                        status_box.update(label=f"Successfully tracked {total} new products!", state="complete", expanded=False)
                        st.success(f"Added {total} new products under group '{group_s}'!")
                        st.rerun()
                    else:
                        status_box.update(label="All products already tracked.", state="complete", expanded=False)
                        st.warning("All found products are already being tracked.")
        else:
            st.error("Please enter a search query.")

    st.divider()

    st.markdown("**Track Specific URL**")
    url_in = st.text_input("Paste Product URL", placeholder="https://...", label_visibility="collapsed", key="au")
    url_group = st.text_input("Comparison Group Name", placeholder="e.g. RTX 4090", key="ug")
    
    if st.button("Add URL", type="primary", width="stretch", key="ab"):
        if not url_in:
            st.error("Please enter a URL.")
        elif db.get_product(url_in):
            st.error("Already tracking this URL!")
        else:
            group_name = url_group.strip() if url_group.strip() else "Individual"
            with st.status("Fetching product details...", expanded=True) as status_box:
                try:
                    status_box.update(label="Connecting to product page...")
                    data = scraper.scrape_url(url_in)["extract"]
                    status_box.update(label="Product data extracted, saving to database...")
                    db.add_product(
                        url=url_in,
                        name=data["name"],
                        price=data["price"],
                        currency=data.get("currency", "USD"),
                        main_image_url=data.get("main_image_url", ""),
                        check_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        comparison_group=group_name,
                        seller=data.get("seller", ""),
                        seller_rating=str(data.get("rating", 0.0)),
                        review_count=data.get("review_count", 0),
                        condition=data.get("condition", "New"),
                        shipping=data.get("shipping", ""),
                        site=urlparse(url_in).netloc.replace("www.", ""),
                        images=json.dumps(data.get("images", [])),
                        brand=data.get("brand", ""),
                        rating=data.get("rating", 0.0),
                        description=data.get("description", ""),
                        specs=json.dumps(data.get("specs", {}))
                    )
                    db.add_price_entry(url_in, data["price"], data["name"])
                    status_box.update(label="Product added successfully!", state="complete", expanded=False)
                    st.success(f"Added: {data['name'][:35]}...")
                    st.rerun()
                except Exception as e:
                    status_box.update(label="Failed to extract product data!", state="error")
                    st.error(f"Failed to scrape: {e}")

db_interval = db.get_setting("check_interval", "Manual")
if db_interval != "Manual" and st.session_state.last_check:
    h = int(db_interval.split()[0])
    if datetime.now() - st.session_state.last_check >= timedelta(hours=h):
        _run_check()

tab_dashboard, tab_test, tab_settings = st.tabs(["Dashboard", "Test Alerts", "Settings"])

with tab_dashboard:
    _show_dashboard()

with tab_test:
    _show_test()

with tab_settings:
    _show_settings()
