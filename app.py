import streamlit as st
from datetime import date
import pandas as pd
from db import get_connection
from io import BytesIO
import re

# ======================================================
# BASIC SETUP
# ======================================================
st.set_page_config(page_title="Couple Finance App", layout="centered")

# ======================================================
# UI + CHAT STYLES
# ======================================================
st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 200px; }

/* Floating Chat Button */
.chat-fab {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #0f62fe;
    color: white;
    border-radius: 30px;
    padding: 12px 18px;
    font-size: 15px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    z-index: 1000;
    box-shadow: 0 8px 20px rgba(0,0,0,0.25);
}

/* Chat Panel */
.chat-panel {
    position: fixed;
    bottom: 90px;
    right: 20px;
    width: 360px;
    max-height: 420px;
    background: white;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    padding: 12px;
    overflow-y: auto;
    z-index: 999;
    animation: slideUp 0.35s ease-out;
}

@keyframes slideUp {
    from { transform: translateY(120%); opacity: 0; }
    to   { transform: translateY(0); opacity: 1; }
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# DB CONNECTION
# ======================================================
@st.cache_resource
def get_db():
    return get_connection()

conn = get_db()
cur = conn.cursor()

USERS = ["Uddeshya", "Megha"]

# ======================================================
# HELPERS
# ======================================================
def get_categories():
    cur.execute("SELECT name FROM categories ORDER BY name")
    return [row[0] for row in cur.fetchall()]

def export_excel(expenses_df, budget_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        expenses_df.to_excel(writer, sheet_name="Expenses", index=False)
        budget_df.to_excel(writer, sheet_name="Budget", index=False)
    output.seek(0)
    return output

def parse_expense_text(text, categories, users):
    t = text.lower()

    amt = float(re.search(r'\b(\d+)\b', t).group(1)) if re.search(r'\b(\d+)\b', t) else None
    paid = next((u for u in users if u.lower() in t), None)
    cat = next((c for c in categories if c.lower() in t), None)

    if not cat:
        if any(x in t for x in ["uber", "ola", "cab", "bus", "train"]): cat = "Travel"
        elif any(x in t for x in ["food", "pizza", "swiggy", "zomato", "chai"]): cat = "Food"
        elif any(x in t for x in ["medicine", "doctor", "hospital"]): cat = "Medical"
        elif any(x in t for x in ["amazon", "flipkart", "shopping"]): cat = "Shopping"
        else: cat = "Other"

    return amt, cat, paid, text

# ======================================================
# CHAT STATE
# ======================================================
if "chat_open" not in st.session_state:
    st.session_state.chat_open = False
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "pending_expense" not in st.session_state:
    st.session_state.pending_expense = None

# ======================================================
# TITLE
# ======================================================
st.title("💰 Couple Finance & Expense App")

# ======================================================
# MONTH SELECTOR
# ======================================================
today = date.today()
months = pd.date_range("2024-01-01", today, freq="MS").strftime("%Y-%m").tolist()
selected_month = st.sidebar.selectbox("📅 Select Month", sorted(months, reverse=True))

# ======================================================
# SIDEBAR MENU
# ======================================================
menu = st.sidebar.selectbox(
    "Menu",
    ["Add Expense", "Dashboard", "Expenses", "Budget", "Export Data"]
)

# ======================================================
# DASHBOARD
# ======================================================
if menu == "Dashboard":
    cur.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE to_char(date,'YYYY-MM')=%s",
        (selected_month,)
    )
    spent = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(monthly_budget),0) FROM budget")
    budget = cur.fetchone()[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Spent", f"₹{spent:.0f}")
    c2.metric("Monthly Budget", f"₹{budget:.0f}")
    c3.metric("Remaining", f"₹{budget - spent:.0f}", delta_color="inverse")

# ======================================================
# ADD EXPENSE
# ======================================================
if menu == "Add Expense":
    st.header("⚡ Quick Add Expense")
    amount = st.number_input("Amount (₹)", min_value=1.0, step=10.0)

    categories = get_categories()
    cols = st.columns(4)
    for i, cat in enumerate(categories):
        if cols[i % 4].button(cat):
            st.session_state["selected_category"] = cat

    category = st.session_state.get("selected_category")
    paid_by = st.radio("Paid By", USERS, horizontal=True)
    notes = st.text_input("Note (optional)")

    if st.button("💾 Save Expense", use_container_width=True) and category:
        cur.execute("""
            INSERT INTO expenses(date,amount,category,paid_by,notes)
            VALUES(%s,%s,%s,%s,%s)
        """, (today, amount, category, paid_by, notes))
        conn.commit()
        st.success("Expense added")
        st.session_state.pop("selected_category", None)
        st.rerun()

# ======================================================
# EXPENSE LIST
# ======================================================
if menu == "Expenses":
    st.header("📋 Expense List")

    cur.execute("""
        SELECT id,date,amount,category,paid_by,notes
        FROM expenses
        WHERE to_char(date,'YYYY-MM')=%s
        ORDER BY date DESC
    """, (selected_month,))
    rows = cur.fetchall()

    if not rows:
        st.info("No expenses found")
    else:
        for r in rows:
            st.write(r)

# ======================================================
# BUDGET
# ======================================================
if menu == "Budget":
    st.header("🎯 Monthly Budget")

    for cat in get_categories():
        cur.execute("SELECT monthly_budget FROM budget WHERE category=%s", (cat,))
        row = cur.fetchone()
        value = row[0] if row else 0.0

        new_val = st.number_input(cat, value=float(value), key=f"b_{cat}")
        if st.button(f"Save {cat}", key=f"save_{cat}"):
            cur.execute("""
                INSERT INTO budget(category,monthly_budget)
                VALUES(%s,%s)
                ON CONFLICT(category) DO UPDATE
                SET monthly_budget=EXCLUDED.monthly_budget
            """, (cat, new_val))
            conn.commit()
            st.success("Saved")

# ======================================================
# EXPORT DATA
# ======================================================
if menu == "Export Data":
    cur.execute("SELECT date,amount,category,paid_by,notes FROM expenses")
    expenses_df = pd.DataFrame(
        cur.fetchall(),
        columns=["Date","Amount","Category","Paid By","Notes"]
    )

    cur.execute("SELECT category,monthly_budget FROM budget")
    budget_df = pd.DataFrame(
        cur.fetchall(),
        columns=["Category","Monthly Budget"]
    )

    if not expenses_df.empty or not budget_df.empty:
        file = export_excel(expenses_df, budget_df)
        st.download_button(
            "⬇️ Download Excel",
            file,
            "couple_finance_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No data to export")

# ======================================================
# FLOATING CHAT TOGGLE (TEXT BUTTON)
# ======================================================
label = "Close Chat" if st.session_state.chat_open else "Chat"

st.markdown(f'<div class="chat-fab">{label}</div>', unsafe_allow_html=True)

if st.button(label, key="chat_toggle"):
    st.session_state.chat_open = not st.session_state.chat_open

# ======================================================
# FLOATING CHAT PANEL (ANIMATED)
# ======================================================
if st.session_state.chat_open:
    st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

    st.markdown("### 🤖 Expense Chat")
    st.caption("Type like: `450 uber paid by Megha`")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Add expense…")

    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        cats = get_categories()
        amt, cat, paid, notes = parse_expense_text(user_input, cats, USERS)

        if not amt or not paid:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": "❌ Include amount & who paid"}
            )
        else:
            st.session_state.pending_expense = {
                "amount": amt, "category": cat, "paid_by": paid, "notes": notes
            }
            st.session_state.chat_messages.append(
                {"role": "assistant",
                 "content": f"Save ₹{amt} | {cat} | {paid}? (Yes / No)"}
            )
        st.rerun()

    if st.session_state.pending_expense:
        confirm = st.chat_input("Yes or No")
        if confirm:
            if confirm.lower() == "yes":
                e = st.session_state.pending_expense
                cur.execute("""
                    INSERT INTO expenses(date,amount,category,paid_by,notes)
                    VALUES(%s,%s,%s,%s,%s)
                """, (today, e["amount"], e["category"], e["paid_by"], e["notes"]))
                conn.commit()
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": "✅ Expense saved!"}
                )
            else:
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": "❌ Cancelled"}
                )
            st.session_state.pending_expense = None
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
