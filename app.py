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
    cursor: pointer;
    z-index: 1000;
    box-shadow: 0 8px 20px rgba(0,0,0,0.25);
}

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
    animation: slideUp 0.3s ease-out;
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
    return [r[0] for r in cur.fetchall()]

def export_excel(exp_df, bud_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        exp_df.to_excel(writer, sheet_name="Expenses", index=False)
        bud_df.to_excel(writer, sheet_name="Budget", index=False)
    output.seek(0)
    return output

def parse_expense_text(text, categories, users):
    t = text.lower()
    amount = float(re.search(r'\b(\d+)\b', t).group(1)) if re.search(r'\b(\d+)\b', t) else None
    paid_by = next((u for u in users if u.lower() in t), None)

    category = next((c for c in categories if c.lower() in t), None)
    if not category:
        if any(x in t for x in ["uber","ola","cab","bus","train"]): category = "Travel"
        elif any(x in t for x in ["food","pizza","zomato","swiggy","chai"]): category = "Food"
        elif any(x in t for x in ["doctor","hospital","medicine"]): category = "Medical"
        elif any(x in t for x in ["amazon","flipkart","shopping"]): category = "Shopping"
        else: category = "Other"

    return amount, category, paid_by, text

# ======================================================
# SESSION STATE
# ======================================================
st.session_state.setdefault("chat_open", False)
st.session_state.setdefault("chat_messages", [])

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
    ["Add Expense", "Dashboard", "Expenses", "Budget & Categories", "Export Data"]
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
    total_budget = cur.fetchone()[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Spent", f"₹{spent:.0f}")
    c2.metric("Total Budget", f"₹{total_budget:.0f}")
    c3.metric("Remaining", f"₹{total_budget - spent:.0f}", delta_color="inverse")

# ======================================================
# ADD EXPENSE
# ======================================================
if menu == "Add Expense":
    st.header("⚡ Quick Add Expense")

    amount = st.number_input("Amount (₹)", min_value=1.0)
    categories = get_categories()

    cols = st.columns(4)
    for i, cat in enumerate(categories):
        if cols[i % 4].button(cat):
            st.session_state["selected_category"] = cat

    category = st.session_state.get("selected_category")
    paid_by = st.radio("Paid By", USERS, horizontal=True)
    notes = st.text_input("Note")

    if st.button("💾 Save Expense") and category:
        cur.execute("""
            INSERT INTO expenses(date,amount,category,paid_by,notes)
            VALUES(%s,%s,%s,%s,%s)
        """, (today, amount, category, paid_by, notes))
        conn.commit()
        st.success("Expense added")
        st.session_state.pop("selected_category", None)
        st.rerun()

# ======================================================
# EXPENSE LIST (EDIT / DELETE)
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
    categories = get_categories()

    if not rows:
        st.info("No expenses found")
    else:
        for r in rows:
            eid, d, amt, cat, paid, note = r
            with st.expander(f"₹{amt} | {cat} | {d}"):
                with st.form(f"edit_{eid}"):
                    new_date = st.date_input("Date", d)
                    new_amt = st.number_input("Amount", value=float(amt))
                    new_cat = st.selectbox("Category", categories, index=categories.index(cat))
                    new_paid = st.selectbox("Paid By", USERS, index=USERS.index(paid))
                    new_note = st.text_input("Notes", value=note or "")

                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("✏️ Update"):
                        cur.execute("""
                            UPDATE expenses
                            SET date=%s,amount=%s,category=%s,paid_by=%s,notes=%s
                            WHERE id=%s
                        """, (new_date,new_amt,new_cat,new_paid,new_note,eid))
                        conn.commit()
                        st.success("Updated")
                        st.rerun()

                    if c2.form_submit_button("🗑️ Delete"):
                        cur.execute("DELETE FROM expenses WHERE id=%s", (eid,))
                        conn.commit()
                        st.warning("Deleted")
                        st.rerun()

# ======================================================
# BUDGET + CATEGORY MANAGEMENT
# ======================================================
if menu == "Budget & Categories":
    st.header("🎯 Monthly Budget (Customizable)")
    categories = get_categories()

    for cat in categories:
        cur.execute("SELECT monthly_budget FROM budget WHERE category=%s", (cat,))
        row = cur.fetchone()
        value = row[0] if row else 0.0

        amt = st.number_input(f"{cat} Budget (₹)", value=float(value), key=f"bud_{cat}")
        if st.button(f"Save {cat}", key=f"save_{cat}"):
            cur.execute("""
                INSERT INTO budget(category,monthly_budget)
                VALUES(%s,%s)
                ON CONFLICT(category)
                DO UPDATE SET monthly_budget=EXCLUDED.monthly_budget
            """, (cat, amt))
            conn.commit()
            st.success(f"{cat} saved")

    st.divider()
    st.subheader("🛠️ Manage Categories")

    new_cat = st.text_input("Add new category")
    if st.button("➕ Add Category") and new_cat:
        try:
            cur.execute("INSERT INTO categories(name) VALUES(%s)", (new_cat,))
            conn.commit()
            st.success("Category added")
            st.rerun()
        except:
            st.warning("Category already exists")

    del_cat = st.selectbox("Delete category", categories)
    if st.button("🗑️ Delete Category"):
        cur.execute("DELETE FROM categories WHERE name=%s", (del_cat,))
        conn.commit()
        st.warning("Category deleted")
        st.rerun()

# ======================================================
# EXPORT DATA
# ======================================================
if menu == "Export Data":
    cur.execute("SELECT date,amount,category,paid_by,notes FROM expenses")
    exp_df = pd.DataFrame(cur.fetchall(), columns=["Date","Amount","Category","Paid By","Notes"])

    cur.execute("SELECT category,monthly_budget FROM budget")
    bud_df = pd.DataFrame(cur.fetchall(), columns=["Category","Monthly Budget"])

    if not exp_df.empty:
        file = export_excel(exp_df, bud_df)
        st.download_button("⬇️ Download Excel", file, "finance_data.xlsx")

# ======================================================
# FLOATING CHAT BUTTON
# ======================================================


# ======================================================
# CHATBOT – AUTO SAVE (FIXED INPUT)
# ======================================================
if st.session_state.chat_open:
    st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

    st.markdown("### 🤖 Expense Chat")
    st.caption("Example: `450 uber Megha`")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_input(
            "Type expense",
            placeholder="450 uber Megha",
            label_visibility="collapsed"
        )
        send = st.form_submit_button("➤ Send")

    if send and user_input:
        st.session_state.chat_messages.append({"role":"user","content":user_input})

        cats = get_categories()
        amt, cat, paid, note = parse_expense_text(user_input, cats, USERS)

        if not amt or not paid:
            st.session_state.chat_messages.append({
                "role":"assistant",
                "content":"❌ Please include amount & who paid"
            })
        else:
            cur.execute("""
                INSERT INTO expenses(date,amount,category,paid_by,notes)
                VALUES(%s,%s,%s,%s,%s)
            """, (today, amt, cat, paid, note))
            conn.commit()

            st.session_state.chat_messages.append({
                "role":"assistant",
                "content":f"✅ Added ₹{amt} | {cat} | {paid}"
            })

        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
