import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

# ----------------------------
# Basic setup
# ----------------------------

st.set_page_config(
    page_title="Payment Rail Cost Scenarios",
    layout="wide",
)

st.title("Payment rail cost scenario explorer")

st.markdown(
    """
This MVP lets you explore **monthly payment costs** based on:
- a baseline transaction mix per payment method  
- scenario sliders for growth and mix shifts  
- cost parameters per payment method (fees, process costs, write-offs, etc.)
"""
)

# Payment methods in the canonical order you requested
PAYMENT_METHODS = [
    "Invoice (no fee)",
    "Installments",
    "Prepayment",
    "TWINT",
    "Visa",
    "Mastercard",
    "PayPal",
]

# Average basket size used to translate write-off rates into CHF per transaction
AVERAGE_BASKET_VALUE = 200.0  # CHF


# ----------------------------
# Baseline data & cost params
# ----------------------------

# 👉 Replace these numbers with your current baseline if you want
baseline_transactions = {
    "Invoice (no fee)": 600_000,
    "Installments": 40_000,
    "Prepayment": 30_000,
    "TWINT": 350_000,
    "Visa": 220_000,
    "Mastercard": 140_000,
    "PayPal": 80_000,
}

# Per-transaction cost parameters (default values – adjust in sidebar)
# Values in CHF per transaction, except write_off_rate (fraction of basket)
default_cost_params = {
    "Invoice (no fee)": {
        "psp_fee": 0.00,
        "process_cost": 0.10,
        "dev_maintenance": 0.10,
        "write_off_rate": 0.008,      # 0.8 % of transaction amount
        "dunning_fee_per_tx": 0.30,   # average revenue per transaction (will reduce total cost)
    },
    "Installments": {
        "psp_fee": 0.00,
        "process_cost": 0.10,
        "dev_maintenance": 0.10,
        "write_off_rate": 0.010,
        "dunning_fee_per_tx": 0.40,
    },
    "Prepayment": {
        "psp_fee": 0.00,
        "process_cost": 0.08,
        "dev_maintenance": 0.05,
        "write_off_rate": 0.000,      # practically no write-offs
        "dunning_fee_per_tx": 0.00,
    },
    "TWINT": {
        "psp_fee": 0.020,
        "process_cost": 0.05,
        "dev_maintenance": 0.05,
        "write_off_rate": 0.000,
        "dunning_fee_per_tx": 0.00,
    },
    "Visa": {
        "psp_fee": 0.018,
        "process_cost": 0.05,
        "dev_maintenance": 0.05,
        "write_off_rate": 0.000,
        "dunning_fee_per_tx": 0.00,
    },
    "Mastercard": {
        "psp_fee": 0.018,
        "process_cost": 0.05,
        "dev_maintenance": 0.05,
        "write_off_rate": 0.000,
        "dunning_fee_per_tx": 0.00,
    },
    "PayPal": {
        "psp_fee": 0.030,
        "process_cost": 0.05,
        "dev_maintenance": 0.05,
        "write_off_rate": 0.000,
        "dunning_fee_per_tx": 0.00,
    },
}


# ----------------------------
# Sidebar – scenario & cost controls
# ----------------------------

st.sidebar.header("Scenario controls")

growth_factor = st.sidebar.slider(
    "Overall growth factor vs. baseline",
    min_value=0.5,
    max_value=2.0,
    value=1.0,
    step=0.05,
)

st.sidebar.subheader("Transaction mix (change vs. baseline in %)")

relative_changes = {}
for pm in PAYMENT_METHODS:
    relative_changes[pm] = st.sidebar.slider(
        f"{pm} – change (%)",
        min_value=-50,
        max_value=50,
        value=0,
        step=1,
    )

st.sidebar.subheader("Cost parameters per payment method")

cost_params = {}

for pm in PAYMENT_METHODS:
    defaults = default_cost_params[pm]
    with st.sidebar.expander(pm, expanded=False):
        psp_fee = st.number_input(
            f"{pm} – PSP / transaction fee (CHF)",
            value=float(defaults["psp_fee"]),
            step=0.005,
            format="%.3f",
        )
        process_cost = st.number_input(
            f"{pm} – process cost per transaction (CHF)",
            value=float(defaults["process_cost"]),
            step=0.01,
            format="%.2f",
        )
        dev_maintenance = st.number_input(
            f"{pm} – dev & maintenance per transaction (CHF)",
            value=float(defaults["dev_maintenance"]),
            step=0.01,
            format="%.2f",
        )
        write_off_rate = st.number_input(
            f"{pm} – write-off rate (share of basket, e.g. 0.008 = 0.8%)",
            value=float(defaults["write_off_rate"]),
            step=0.001,
            format="%.3f",
        )
        dunning_fee_per_tx = st.number_input(
            f"{pm} – average dunning fee revenue per transaction (CHF)",
            value=float(defaults["dunning_fee_per_tx"]),
            step=0.05,
            format="%.2f",
        )

    cost_params[pm] = {
        "psp_fee": psp_fee,
        "process_cost": process_cost,
        "dev_maintenance": dev_maintenance,
        "write_off_rate": write_off_rate,
        "dunning_fee_per_tx": dunning_fee_per_tx,
    }


# ----------------------------
# Cost engine
# ----------------------------

cost_blocks = [
    "PSP fees",
    "Process costs",
    "Dev & maintenance",
    "Write-offs",
    "Dunning fee revenue",
]


def compute_per_tx_cost_blocks(params):
    """Return per-transaction cost per block (CHF, revenue as negative)."""
    psp = params["psp_fee"]
    process = params["process_cost"]
    dev = params["dev_maintenance"]
    write_off = params["write_off_rate"] * AVERAGE_BASKET_VALUE
    # Revenue reduces the total cost
    dunning_revenue = -params["dunning_fee_per_tx"]

    return {
        "PSP fees": psp,
        "Process costs": process,
        "Dev & maintenance": dev,
        "Write-offs": write_off,
        "Dunning fee revenue": dunning_revenue,
    }


def compute_costs(transactions_dict):
    """Compute per payment method total cost and breakdown."""
    rows = []
    breakdown = {pm: {cb: 0.0 for cb in cost_blocks} for pm in PAYMENT_METHODS}

    for pm in PAYMENT_METHODS:
        tx = transactions_dict[pm]
        per_tx_blocks = compute_per_tx_cost_blocks(cost_params[pm])

        total_cost_pm = 0.0
        for cb in cost_blocks:
            block_cost = per_tx_blocks[cb] * tx
            breakdown[pm][cb] += block_cost
            total_cost_pm += block_cost

        avg_cost_pm = total_cost_pm / tx if tx > 0 else 0.0

        rows.append(
            {
                "Payment method": pm,
                "Transactions": tx,
                "Total cost (CHF)": total_cost_pm,
                "Average cost per transaction (CHF)": avg_cost_pm,
            }
        )

    df = pd.DataFrame(rows).set_index("Payment method")
    breakdown_df = pd.DataFrame(breakdown).T  # index = payment method

    return df, breakdown_df


# ----------------------------
# Build baseline & scenario
# ----------------------------

# Baseline transactions (fixed)
baseline_tx = {pm: baseline_transactions[pm] for pm in PAYMENT_METHODS}

# Scenario transactions (growth + mix sliders)
scenario_tx = {}
for pm in PAYMENT_METHODS:
    factor = 1.0 + relative_changes[pm] / 100.0
    scenario_tx[pm] = int(baseline_tx[pm] * growth_factor * factor)

baseline_df, baseline_breakdown = compute_costs(baseline_tx)
scenario_df, scenario_breakdown = compute_costs(scenario_tx)

# Totals & averages
baseline_total_transactions = baseline_df["Transactions"].sum()
scenario_total_transactions = scenario_df["Transactions"].sum()

baseline_total_cost = baseline_df["Total cost (CHF)"].sum()
scenario_total_cost = scenario_df["Total cost (CHF)"].sum()

baseline_avg_cost = (
    baseline_total_cost / baseline_total_transactions
    if baseline_total_transactions > 0
    else 0.0
)
scenario_avg_cost = (
    scenario_total_cost / scenario_total_transactions
    if scenario_total_transactions > 0
    else 0.0
)


# ----------------------------
# Key metrics
# ----------------------------

st.markdown("### Key monthly cost metrics")

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "Total baseline cost (CHF / month)",
    f"{baseline_total_cost:,.0f}",
)

m2.metric(
    "Total scenario cost (CHF / month)",
    f"{scenario_total_cost:,.0f}",
    delta=f"{scenario_total_cost - baseline_total_cost:,.0f}",
    delta_color="inverse",  # lower cost = green
)

m3.metric(
    "Average cost per transaction – baseline (CHF)",
    f"{baseline_avg_cost:,.2f}",
)

m4.metric(
    "Average cost per transaction – scenario (CHF)",
    f"{scenario_avg_cost:,.2f}",
    delta=f"{scenario_avg_cost - baseline_avg_cost:,.2f}",
    delta_color="inverse",  # lower cost per tx = green
)


# ----------------------------
# Tables: baseline vs scenario & cost blocks
# ----------------------------

st.markdown("### Baseline vs. scenario by payment method")

comparison_df = pd.DataFrame(index=PAYMENT_METHODS)
comparison_df["Baseline transactions"] = baseline_df["Transactions"]
comparison_df["Scenario transactions"] = scenario_df["Transactions"]
comparison_df["Baseline cost (CHF)"] = baseline_df["Total cost (CHF)"]
comparison_df["Scenario cost (CHF)"] = scenario_df["Total cost (CHF)"]
comparison_df["Cost delta (CHF)"] = (
    comparison_df["Scenario cost (CHF)"] - comparison_df["Baseline cost (CHF)"]
)
comparison_df["Cost delta (%)"] = np.where(
    comparison_df["Baseline cost (CHF)"] > 0,
    comparison_df["Cost delta (CHF)"]
    / comparison_df["Baseline cost (CHF)"]
    * 100,
    0.0,
)

# Add TOTAL row
total_row = pd.DataFrame(
    {
        "Baseline transactions": [comparison_df["Baseline transactions"].sum()],
        "Scenario transactions": [comparison_df["Scenario transactions"].sum()],
        "Baseline cost (CHF)": [comparison_df["Baseline cost (CHF)"].sum()],
        "Scenario cost (CHF)": [comparison_df["Scenario cost (CHF)"].sum()],
        "Cost delta (CHF)": [comparison_df["Cost delta (CHF)"].sum()],
        "Cost delta (%)": [
            (
                comparison_df["Scenario cost (CHF)"].sum()
                - comparison_df["Baseline cost (CHF)"].sum()
            )
            / comparison_df["Baseline cost (CHF)"].sum()
            * 100
            if comparison_df["Baseline cost (CHF)"].sum() > 0
            else 0.0
        ],
    },
    index=["TOTAL"],
)

comparison_with_total = pd.concat([comparison_df, total_row])

st.dataframe(
    comparison_with_total.style.format(
        {
            "Baseline transactions": "{:,.0f}",
            "Scenario transactions": "{:,.0f}",
            "Baseline cost (CHF)": "{:,.0f}",
            "Scenario cost (CHF)": "{:,.0f}",
            "Cost delta (CHF)": "{:,.0f}",
            "Cost delta (%)": "{:,.1f}",
        }
    ),
    use_container_width=True,
)


st.markdown("### Scenario cost breakdown by payment method and cost block")

# Add total column and total row for scenario breakdown
scenario_breakdown_ordered = scenario_breakdown.loc[PAYMENT_METHODS, cost_blocks].copy()
scenario_breakdown_ordered["Total"] = scenario_breakdown_ordered.sum(axis=1)

total_breakdown_row = pd.DataFrame(
    scenario_breakdown_ordered.sum(axis=0).to_dict(), index=["TOTAL"]
)

scenario_breakdown_with_total = pd.concat(
    [scenario_breakdown_ordered, total_breakdown_row]
)

st.dataframe(
    scenario_breakdown_with_total.style.format("{:,.0f}"),
    use_container_width=True,
)


# ----------------------------
# Charts (scenario)
# ----------------------------

st.markdown("### Visual comparison of scenario costs and transaction mix")

# Prepare scenario data with shares
scenario_chart_df = scenario_df.copy()
scenario_chart_df = scenario_chart_df.loc[PAYMENT_METHODS].reset_index()
scenario_chart_df["Cost share (%)"] = (
    scenario_chart_df["Total cost (CHF)"] / scenario_total_cost * 100
    if scenario_total_cost > 0
    else 0.0
)
scenario_chart_df["Transaction share (%)"] = (
    scenario_chart_df["Transactions"] / scenario_total_transactions * 100
    if scenario_total_transactions > 0
    else 0.0
)

# Colour scale (keeps colours consistent across charts)
color_scale = alt.Scale(
    domain=PAYMENT_METHODS,
)

c1, c2, c3, c4 = st.columns(4)

# Fixed height for all charts
CHART_HEIGHT = 220

# 1) Total cost per payment method (bar)
cost_bar = (
    alt.Chart(scenario_chart_df)
    .mark_bar()
    .encode(
        y=alt.Y("Payment method:N", sort=PAYMENT_METHODS, title=None),
        x=alt.X("Total cost (CHF):Q", title="Total cost (CHF)"),
        color=alt.Color("Payment method:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("Payment method:N", title="Payment method"),
            alt.Tooltip("Total cost (CHF):Q", format=",.0f"),
        ],
    )
    .properties(height=CHART_HEIGHT)
)

c1.altair_chart(cost_bar, use_container_width=True)
c1.caption("Scenario – total cost per payment method (CHF)")

# 2) Cost share per payment method (pie)
cost_pie = (
    alt.Chart(scenario_chart_df)
    .mark_arc()
    .encode(
        theta=alt.Theta("Total cost (CHF):Q"),
        color=alt.Color("Payment method:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("Payment method:N", title="Payment method"),
            alt.Tooltip("Cost share (%):Q", format=",.1f"),
            alt.Tooltip("Total cost (CHF):Q", format=",.0f"),
        ],
    )
    .properties(height=CHART_HEIGHT)
)

c2.altair_chart(cost_pie, use_container_width=True)
c2.caption("Scenario – cost share per payment method (%)")

# 3) Transactions per payment method (bar)
tx_bar = (
    alt.Chart(scenario_chart_df)
    .mark_bar()
    .encode(
        y=alt.Y("Payment method:N", sort=PAYMENT_METHODS, title=None),
        x=alt.X("Transactions:Q", title="Transactions"),
        color=alt.Color("Payment method:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("Payment method:N", title="Payment method"),
            alt.Tooltip("Transactions:Q", format=",.0f"),
        ],
    )
    .properties(height=CHART_HEIGHT)
)

c3.altair_chart(tx_bar, use_container_width=True)
c3.caption("Scenario – transactions per payment method")

# 4) Transaction share per payment method (pie)
tx_pie = (
    alt.Chart(scenario_chart_df)
    .mark_arc()
    .encode(
        theta=alt.Theta("Transactions:Q"),
        color=alt.Color("Payment method:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("Payment method:N", title="Payment method"),
            alt.Tooltip("Transaction share (%):Q", format=",.1f"),
            alt.Tooltip("Transactions:Q", format=",.0f"),
        ],
    )
    .properties(height=CHART_HEIGHT)
)

c4.altair_chart(tx_pie, use_container_width=True)
c4.caption("Scenario – transaction share per payment method (%)")
