# imports: bring in libraries we need
import io, csv
from datetime import date
import streamlit as st
import pandas as pd             # Pandas for data tables
import plotly.express as px

# Streamlit app setup
st.set_page_config(page_title="Spending Analyzer", layout="wide")
st.title("Spending Analyzer with Budgeting")
st.write("Upload CSV/TXT/XLS/XLSX OR click **Load sample data**.")

# 1. Robust file loader (handles CSV/TXT/XLS/XLSX, encodings)
def load_table(uploaded_file):
    """Try to load CSV/TXT/Excel with auto delimiter + encoding detection."""
    # if nothing was uploaded, return empty table
    if uploaded_file is None:   
        return pd.DataFrame()

    # get filename (may be empty)
    name = getattr(uploaded_file, "name", "").lower()

    # Handle Excel files
    if name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            return pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Failed to read Excel: {e}")
            return pd.DataFrame()

    # Otherwise treat as text (CSV/TXT)
    raw_bytes = uploaded_file.read()
    uploaded_file.seek(0)
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        st.error("Could not decode file. Save as UTF-8 CSV and retry.")
        return pd.DataFrame()

    stripped = "\n".join([line for line in text.splitlines() if line.strip() != ""])

    # Detect delimiter
    try:
        dialect = csv.Sniffer().sniff(stripped[:4096], delimiters=[",", ";", "\t", "|"])
        sep = dialect.delimiter
    except Exception:
        sep = None

    # first attempt: let pandas parse with the (maybe) detected separator
    try:
        return pd.read_csv(io.StringIO(stripped), sep=sep, engine="python")
    except Exception:
        # fallbacks: try common separators explicitly       
        for trial_sep in [",", ";", "\t", "|"]:
            try:
                return pd.read_csv(io.StringIO(stripped), sep=trial_sep, engine="python")
            except Exception:
                pass
    # if everything fails, return empty table
    return pd.DataFrame()

# ----------------------------------------------------------
# 2. Upload or sample data
# ----------------------------------------------------------
c1, c2 = st.columns([3,1])
with c1:
    file = st.file_uploader("Upload file", type=["csv","txt","xls","xlsx"])
with c2:
    sample_clicked = st.button("Load sample data")

if sample_clicked:
    # Example dataset (no Starbucks anywhere)
    sample_csv = """date,amount,description
2024-09-01,-85.20,Metro Groceries
2024-09-02,-18.70,UBER Ride
2024-09-03,2000.00,Payroll Deposit
2024-09-05,-120.00,Costco Wholesale
2024-09-09,-55.99,Cineplex Movies
2024-09-10,-15.99,Netflix Subscription
2024-09-12,-60.00,Shell Gas Station
2024-09-16,1500.00,Freelance Income
2024-09-19,-12.00,Spotify Premium
"""
    df = pd.read_csv(io.StringIO(sample_csv))
elif file is not None:
    df = load_table(file)
else:
    st.info("Upload a file or click sample to continue.")
    st.stop()

if df.empty:
    st.error("Could not parse file. Check format or try sample.")
    st.stop()

# Normalize headers, make header names consistent
df.columns = [c.strip().lower() for c in df.columns]

# Ensure required columns
# we need these three columns
required = {"date","amount","description"}
if not required.issubset(df.columns):
    # tell the user what’s missing
    st.error(f"File must have columns: {required}")
    st.stop()

# Parse data types
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
df = df.dropna(subset=["date","amount"])

# ----------------------------------------------------------
# 3. Show Transactions
# ----------------------------------------------------------
st.subheader("Transactions")
st.dataframe(df, use_container_width=True)

total = df["amount"].sum()
st.metric("Net Total", f"${total:,.2f}")

# ----------------------------------------------------------
# 4. Charts
# ----------------------------------------------------------
st.subheader("Spending Over Time")
fig = px.line(df.sort_values("date"), x="date", y="amount")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Top Merchants")
top = (
    df.groupby("description")["amount"]
    .sum()
    .reset_index()
    .sort_values("amount", ascending=False)
    .head(10)
)
st.bar_chart(top.set_index("description")["amount"])

# ----------------------------------------------------------
# 5. Budgeting Feature (improved)
# ----------------------------------------------------------
st.subheader("Budgeting")

# create a period column like 2024-09 so we can pick months that exist in the data
df["year_month"] = df["date"].dt.to_period("M")

# get all unique months found in the file, sorted
unique_months = sorted(df["year_month"].dropna().unique().tolist())
# Fallback if somehow empty
if not unique_months:
    st.warning("No valid dates found to build budget months.")
    unique_months = [pd.Timestamp.today().to_period("M")]

# dropdown to pick a month to budget; default to the *latest* month in the data
sel_period = st.selectbox(
    "Select month to budget",
    options=[str(p) for p in unique_months],
    index=len(unique_months) - 1  # default to latest month in the file
)

# convert the chosen text (like "2024-09") back to a Period type
period = pd.Period(sel_period, freq="M")

# filter rows that belong to the chosen month
month_data = df[df["year_month"] == period].copy()

# Keep only expenses (amount < 0) and convert them to positive dollars
expenses = month_data[month_data["amount"] < 0].copy()
expenses["spent"] = -expenses["amount"]  # e.g., -12.45 -> 12.45

# Overall monthly budget
overall_budget = st.number_input(
    "Overall monthly budget ($)",
    min_value=0.0, value=2000.0, step=50.0
)

total_spend = float(expenses["spent"].sum()) if not expenses.empty else 0.0
progress = min(1.0, total_spend / overall_budget) if overall_budget > 0 else 0.0
st.write(f"Total expenses in **{period}**: **${total_spend:,.2f}**")
st.progress(progress)

# ---------------- Category budgets by keyword ----------------
st.subheader("Category Budgets (comma-separated keywords match Description)")

# Helpful defaults that match the sample data (edit freely)
if "rules" not in st.session_state:
    st.session_state.rules = [
        {"category": "Groceries", "keywords": "metro,costco,walmart,superstore", "budget": 300.0},
        {"category": "Transport", "keywords": "uber,lyft,shell,esso,petro,gas", "budget": 150.0},
        {"category": "Entertainment", "keywords": "cineplex,netflix,spotify,steam", "budget": 100.0},
    ]

rules_df = pd.DataFrame(st.session_state.rules)
edited = st.data_editor(
    rules_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "category": st.column_config.TextColumn("Category"),
        "keywords": st.column_config.TextColumn("Keywords (comma-separated)"),
        "budget": st.column_config.NumberColumn("Monthly Budget ($)", min_value=0.0, step=10.0),
    }
)
st.session_state.rules = edited.to_dict("records")

# Evaluate each rule against this month's expenses
if expenses.empty:
    st.info("No expenses found for this month.")
else:
    for rule in st.session_state.rules:
        cat = (rule.get("category") or "").strip() or "(Unnamed)"
        kw_str = (rule.get("keywords") or "").strip()
        limit = float(rule.get("budget") or 0.0)

        # Build a case-insensitive mask that matches ANY of the keywords in Description
        keywords = [k.strip().lower() for k in kw_str.split(",") if k.strip()]
        if not keywords:
            st.write(f"**{cat}** – no keywords set.")
            continue

        desc_lower = expenses["description"].str.lower().fillna("")
        mask = False
        for k in keywords:
            mask = mask | desc_lower.str.contains(k, na=False)

        matched = expenses[mask]
        cat_spent = float(matched["spent"].sum()) if not matched.empty else 0.0

        # Progress bar for the category
        st.write(f"**{cat}** — spent **${cat_spent:,.2f} / ${limit:,.2f}**  (keywords: {', '.join(keywords)})")
        st.progress(min(1.0, cat_spent / limit) if limit > 0 else 0.0)

        # Optional: expand to see which rows matched
        with st.expander(f"Show {cat} transactions"):
            if matched.empty:
                st.write("No matching transactions.")
            else:
                st.dataframe(matched[["date", "description", "spent"]].sort_values("date"), use_container_width=True)

# Clean up helper column
df.drop(columns=["year_month"], errors="ignore", inplace=True)
