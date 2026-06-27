import urllib.parse

import requests
from src import db
from src.config import get_groq_api_key


class AIService:
    def __init__(self):
        self.api_key = get_groq_api_key()
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate_ai_alert(self, product_name: str, old_price: float, new_price: float, url: str, group_name: str = None) -> str:
        if not self.api_key:
            return f"Price dropped from ${old_price:.2f} to ${new_price:.2f}!"

        group_context = ""
        if group_name:
            products = db.get_all_products()
            group_products = [p for p in products if p.get("comparison_group") == group_name]
            if len(group_products) > 1:
                group_context = "\nOther tracked products in this group:\n"
                for gp in group_products:
                    if gp["url"] != url:
                        store = urllib.parse.urlparse(gp["url"]).netloc.replace("www.", "")
                        group_context += f"- {gp['name']} at {store}: {gp['currency']} {gp['price']:.2f}\n"

        prompt = f"""
We detected a price drop for a tracked product!
Product: {product_name}
Old Price: ${old_price:.2f}
New Price: ${new_price:.2f}
Price Drop: {((old_price - new_price) / old_price) * 100:.1f}%
Link: {url}
{group_context}

Write a witty, short (maximum 40 words), and highly informative alert message advising the user. Compare with other products in the group if context is provided. Do not use placeholders. Write only the advice message.
"""
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": "You are a smart shopping assistant. Provide a concise, witty, and contextual shopping alert."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.5,
        }
        try:
            r = requests.post(self.url, headers=self._headers(), json=payload, timeout=10)
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"AI Alert generation error: {e}")
            return f"Price dropped from ${old_price:.2f} to ${new_price:.2f}!"

    def generate_recommendation(self, query: str, products: list) -> str:
        if not self.api_key or not products:
            return ""

        deals = []
        for p in products:
            store = urllib.parse.urlparse(p["url"]).netloc.replace("www.", "")
            deals.append(f"- {p['name']}: {p['currency']} {p['price']:.2f} (Store: {store})")
        deals_str = "\n".join(deals)

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": "You are a smart shopping assistant. Provide a brief, one-sentence advice (less than 25 words) comparing the options. Highlight the best value."},
                {"role": "user", "content": f"Query: '{query}'\nDeals:\n{deals_str}\nRecommend the best deal."},
            ],
            "temperature": 0.3,
        }
        try:
            r = requests.post(self.url, headers=self._headers(), json=payload, timeout=10)
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Groq recommendation generation error: {e}")
            return ""

    def generate_chat_response(self, context: str, user_message: str, chat_history: list) -> str:
        if not self.api_key:
            return "Groq API Key is not configured."

        messages = [
            {"role": "system", "content": f"You are a helpful e-commerce shopping assistant. Below is the current price data and price history for all tracked products across all groups. Analyze this data to answer the user's questions about price trends, comparison details, best deals, or buying recommendations.\n\nContext Data:\n{context}"}
        ]
        for msg in chat_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": messages,
            "temperature": 0.5,
        }
        try:
            r = requests.post(self.url, headers=self._headers(), json=payload, timeout=15)
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Groq chat generation error: {e}")
            return f"Error communicating with AI: {e}"
