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

# UI tweaks
st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            min-width: 200px;
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

    # Amount
    amount = None
    m = re.search(r'\b(\d+)\b', t)
    if m:
        amount = float(m.group(1))

    # Paid by
    paid_by = None
    for u in users:
        if u.lower() in t:
            paid_by = u
            break

    # Category (explicit)
    category = None
    for c in categories:
        if c.lower() in t:
            category = c
            break

    # Fallback category
    if not category:
        if any(x in t for x in ["uber", "ola", "cab", "train", "bus"]):
            category = "Travel"
        elif any(x in t for x in ["food", "pizza", "swiggy", "zomato", "chai"]):
            category = "Food"
        elif any(x in t for x in ["medicine", "doctor", "hospital"]):
            category = "Medical"
        elif any(x in t for x in ["amazon", "flipkart", "shopping"]):
            category = "Shopping"
        else:
            category = "Other"

    return amount, category, paid_by, text

# ======================================================
# CHAT STATE
# ======================================================
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
months = pd.date_range(
    start="2024-01-01",
    end=today,
    freq="MS"
).strftime("%Y-%m").tolist()

selected_month = st.sidebar.selectbox(
    "📅 Select Month",
    sorted(months, reverse=True)
)

# ======================================================
# SIDEBAR MENU
# ======================================================
menu = st.sidebar.selectbox(
    "Menu",
    ["Add Expense", "Dashboard", "Expenses", "Budget", "AI Chat", "Export Data"]
)

# ======================================================
# DASHBOARD
# ======================================================
if menu == "Dashboard":
    st.header("📊 Monthly Dashboard")

    cur.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE to_char(date,'YYYY-MM') = %s",
        (selected_month,)
    )
    total_spent = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(monthly_budget),0) FROM budget")
    total_budget = cur.fetchone()[0]

    balance = total_budget - total_spent

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Spent", f"₹{total_spent:.0f}")
    c2.metric("Monthly Budget", f"₹{total_budget:.0f}")
    c3.metric("Remaining", f"₹{balance:.0f}", delta_color="inverse")

    st.subheader("📂 Category-wise Spend")

    cur.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE to_char(date,'YYYY-MM') = %s
        GROUP BY category
    """, (selected_month,))
    data = cur.fetchall()

    if data:
        df = pd.DataFrame(data, columns=["Category", "Amount"])
        st.bar_chart(df.set_index("Category"))
    else:
        st.info("No expenses for this month")

# ======================================================
# ADD EXPENSE
# ======================================================
if menu == "Add Expense":
    st.subheader("👋 Quick entry – add expense first")
    st.header("⚡ Quick Add Expense")

    amount = st.number_input("Amount (₹)", min_value=1.0, step=10.0, format="%.0f")

    st.subheader("Category")
    categories = get_categories()
    cols = st.columns(4)

    for i, cat in enumerate(categories):
        if cols[i % 4].button(cat):
            st.session_state["selected_category"] = cat

    category = st.session_state.get("selected_category")
    paid_by = st.radio("Paid By", USERS, horizontal=True)
    notes = st.text_input("Note (optional)")

    if st.button("💾 Save Expense", use_container_width=True):
        if not category:
            st.warning("Please select a category")
        else:
            cur.execute("""
                INSERT INTO expenses (date, amount, category, paid_by, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (today, amount, category, paid_by, notes))
            conn.commit()
            st.session_state.pop("selected_category", None)
            st.success("Expense added")
            st.rerun()

# ======================================================
# EXPENSE LIST
# ======================================================
if menu == "Expenses":
    st.header("📋 Expense List")

    cur.execute("""
        SELECT id, date, amount, category, paid_by, notes
        FROM expenses
        WHERE to_char(date,'YYYY-MM') = %s
        ORDER BY date DESC
    """, (selected_month,))
    rows = cur.fetchall()
    categories = get_categories()

    if not rows:
        st.info("No expenses found")
    else:
        for r in rows:
            exp_id, d, amt, cat, paid, note = r
            with st.expander(f"₹{amt} | {cat} | {d}"):
                with st.form(key=f"form_{exp_id}"):
                    new_date = st.date_input("Date", value=d)
                    new_amount = st.number_input("Amount", value=float(amt))
                    new_category = st.selectbox(
                        "Category",
                        categories,
                        index=categories.index(cat) if cat in categories else 0
                    )
                    new_paid = st.selectbox("Paid By", USERS, index=USERS.index(paid))
                    new_note = st.text_input("Notes", value=note or "")

                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("✏️ Update"):
                        cur.execute("""
                            UPDATE expenses
                            SET date=%s, amount=%s, category=%s, paid_by=%s, notes=%s
                            WHERE id=%s
                        """, (new_date, new_amount, new_category, new_paid, new_note, exp_id))
                        conn.commit()
                        st.success("Updated")
                        st.rerun()

                    if c2.form_submit_button("🗑️ Delete"):
                        cur.execute("DELETE FROM expenses WHERE id=%s", (exp_id,))
                        conn.commit()
                        st.warning("Deleted")
                        st.rerun()

# ======================================================
# BUDGET + CATEGORY MANAGEMENT
# ======================================================
if menu == "Budget":
    st.header("🎯 Monthly Budget")
    categories = get_categories()

    for cat in categories:
        cur.execute("SELECT monthly_budget FROM budget WHERE category=%s", (cat,))
        row = cur.fetchone()
        value = row[0] if row else 0.0

        new_val = st.number_input(
            f"{cat} Budget (₹)",
            min_value=0.0,
            value=float(value),
            key=f"budget_{cat}"
        )

        if st.button(f"Save {cat}", key=f"btn_{cat}"):
            cur.execute("""
                INSERT INTO budget (category, monthly_budget)
                VALUES (%s, %s)
                ON CONFLICT (category)
                DO UPDATE SET monthly_budget = EXCLUDED.monthly_budget
            """, (cat, new_val))
            conn.commit()
            st.success(f"{cat} saved")

    st.divider()
    st.subheader("🛠️ Manage Categories")

    new_cat = st.text_input("Add new category")
    if st.button("➕ Add Category"):
        try:
            cur.execute("INSERT INTO categories (name) VALUES (%s)", (new_cat,))
            conn.commit()
            st.success("Category added")
            st.rerun()
        except:
            st.warning("Category already exists")

    del_cat = st.selectbox("Delete category", categories)
    if st.button("🗑️ Delete Category"):
        cur.execute("DELETE FROM categories WHERE name=%s", (del_cat,))
        conn.commit()
        st.warning(f"{del_cat} deleted")
        st.rerun()

# ======================================================
# EXPORT ALL DATA
# ======================================================
if menu == "Export Data":
    st.header("📤 Export All Data")

    cur.execute("SELECT date, amount, category, paid_by, notes FROM expenses ORDER BY date")
    expenses_df = pd.DataFrame(
        cur.fetchall(),
        columns=["Date", "Amount", "Category", "Paid By", "Notes"]
    )

    cur.execute("SELECT category, monthly_budget FROM budget ORDER BY category")
    budget_df = pd.DataFrame(
        cur.fetchall(),
        columns=["Category", "Monthly Budget"]
    )

    if not expenses_df.empty or not budget_df.empty:
        excel_file = export_excel(expenses_df, budget_df)
        st.download_button(
            "⬇️ Download Excel (All Data)",
            excel_file,
            "couple_finance_all_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No data to export")

# ======================================================
# AI CHAT – REAL CHATBOT PANEL
# ======================================================
if menu == "AI Chat":
    st.header("🤖 Expense Chatbot")
    st.caption("Type like WhatsApp → `450 uber paid by Megha`")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Type your expense...")

    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})

        cats = get_categories()
        amt, cat, paid, notes = parse_expense_text(user_input, cats, USERS)

        if not amt or not paid:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "❌ Please include **amount** and **who paid**."
            })
        else:
            st.session_state.pending_expense = {
                "amount": amt,
                "category": cat,
                "paid_by": paid,
                "notes": notes
            }
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": (
                    f"🧾 **I understood:**\n\n"
                    f"- Amount: ₹{amt}\n"
                    f"- Category: {cat}\n"
                    f"- Paid by: {paid}\n\n"
                    f"Reply **Yes** to save or **No** to cancel."
                )
            })
        st.rerun()

    if st.session_state.pending_expense:
        confirm = st.chat_input("Type Yes or No")
        if confirm:
            if confirm.lower() == "yes":
                e = st.session_state.pending_expense
                cur.execute("""
                    INSERT INTO expenses (date, amount, category, paid_by, notes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (date.today(), e["amount"], e["category"], e["paid_by"], e["notes"]))
                conn.commit()
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": "✅ Expense saved!"
                })
            else:
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": "❌ Cancelled."
                })
            st.session_state.pending_expense = None
            st.rerun()
