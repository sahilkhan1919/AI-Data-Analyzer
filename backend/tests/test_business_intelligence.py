"""
test_business_intelligence.py – Unit tests for the Business Intelligence Engine.

Tests functions in backend.analytics.business_intelligence directly:
  - Candidate measure discovery and non-additive filtering
  - KPI calculations (revenue, profit, profit margin, quantity, AOV)
  - Division-by-zero protection (profit margin with 0 revenue)
  - Repeated order identifiers in AOV calculation
  - Group-wise analysis (sum, mean, null labels, ranking)
  - Date trends across granularities (monthly, quarterly, daily)
  - Period-over-period calculations (valid, zero previous value, insufficient data)
  - Deterministic insights generation
"""

import pandas as pd
import pytest

from analytics.business_intelligence import (
    calculate_business_kpis,
    calculate_date_trends,
    calculate_group_analysis,
    calculate_period_over_period,
    discover_business_kpis,
    generate_deterministic_insights,
)


@pytest.fixture()
def ecommerce_df():
    """Deterministic retail/ecommerce dataset with repeated orders and negative profit."""
    return pd.DataFrame({
        "order_id": [101, 101, 102, 103, 104],  # 101 appears twice
        "order_date": ["2023-01-15", "2023-01-20", "2023-02-10", "2023-03-05", "2023-03-25"],
        "region": ["North", "North", "South", "East", "West"],
        "sales": [100.0, 50.0, 200.0, 300.0, 150.0],  # total = 800
        "profit": [20.0, 10.0, 40.0, -30.0, 20.0],     # total = 60
        "quantity": [2, 1, 4, 6, 3],                    # total = 16
        "discount": [0.05, 0.05, 0.10, 0.20, 0.0],
    })


class TestKPIDiscovery:
    def test_identifies_additive_measures(self, ecommerce_df):
        discovery = discover_business_kpis(ecommerce_df)
        mappings = discovery["inferred_mappings"]
        assert mappings["revenue_col"] == "sales"
        assert mappings["profit_col"] == "profit"
        assert mappings["quantity_col"] == "quantity"
        assert mappings["order_id_col"] == "order_id"

    def test_non_additive_identifier_not_summed(self):
        df = pd.DataFrame({
            "customer_id": [1001, 1002, 1003, 1004],
            "zip_code": [90210, 90211, 90212, 90213],
            "sales_amount": [50.0, 100.0, 150.0, 200.0],
        })
        discovery = discover_business_kpis(df)
        candidates = {c["column"]: c for c in discovery["candidate_measures"]}
        # sales_amount should have a valid sum
        assert candidates["sales_amount"]["is_additive"] is True
        assert candidates["sales_amount"]["sum"] == 500.0
        # id and zip should not be summed
        assert candidates["customer_id"]["is_additive"] is False
        assert candidates["zip_code"]["is_additive"] is False


class TestKPICalculations:
    def test_revenue_and_profit_totals(self, ecommerce_df):
        kpis = calculate_business_kpis(ecommerce_df)
        kpi_dict = {k["metric_name"]: k for k in kpis}

        assert "Total sales" in kpi_dict
        assert kpi_dict["Total sales"]["metric_value"] == 800.0

        assert "Total profit" in kpi_dict
        assert kpi_dict["Total profit"]["metric_value"] == 60.0

    def test_profit_margin_calculation(self, ecommerce_df):
        kpis = calculate_business_kpis(ecommerce_df)
        kpi_dict = {k["metric_name"]: k for k in kpis}

        assert "Profit Margin" in kpi_dict
        # 60 / 800 * 100 = 7.5%
        assert kpi_dict["Profit Margin"]["metric_value"] == 7.5

    def test_profit_margin_zero_revenue_safe(self):
        df = pd.DataFrame({"sales": [0.0, 0.0], "profit": [10.0, -5.0]})
        kpis = calculate_business_kpis(df, revenue_col="sales", profit_col="profit")
        kpi_dict = {k["metric_name"]: k for k in kpis}
        assert kpi_dict["Profit Margin"]["metric_value"] is None
        assert "zero" in kpi_dict["Profit Margin"]["calculation_explanation"].lower()

    def test_aov_uses_distinct_order_count(self, ecommerce_df):
        # 5 rows, but 4 distinct orders (101 repeated twice)
        # Total sales = 800. AOV = 800 / 4 = 200.0 (NOT 800 / 5 = 160.0)
        kpis = calculate_business_kpis(ecommerce_df)
        kpi_dict = {k["metric_name"]: k for k in kpis}

        assert "Average Order Value (AOV)" in kpi_dict
        assert kpi_dict["Average Order Value (AOV)"]["metric_value"] == 200.0


class TestGroupAnalysis:
    def test_group_sum_and_ranking(self, ecommerce_df):
        res = calculate_group_analysis(
            ecommerce_df, group_col="region", measure_col="sales", aggregation="sum"
        )
        assert res["group_column"] == "region"
        assert res["measure_column"] == "sales"
        assert res["total_groups"] == 4
        # East has 300 (highest)
        assert res["highest_performing"]["group"] == "East"
        assert res["highest_performing"]["value"] == 300.0

    def test_null_group_label_handled(self):
        df = pd.DataFrame({
            "department": ["Sales", None, "Sales"],
            "expenses": [100.0, 50.0, 150.0],
        })
        res = calculate_group_analysis(df, group_col="department", measure_col="expenses", aggregation="sum")
        groups = [r["group"] for r in res["records"]]
        assert "(Missing / None)" in groups

    def test_tracks_negative_groups(self, ecommerce_df):
        res = calculate_group_analysis(
            ecommerce_df, group_col="region", measure_col="profit", aggregation="sum"
        )
        # East profit is -30
        assert len(res["negative_groups"]) == 1
        assert res["negative_groups"][0]["group"] == "East"
        assert res["negative_groups"][0]["value"] == -30.0

    def test_invalid_group_col_raises(self, ecommerce_df):
        with pytest.raises(ValueError, match="Grouping column"):
            calculate_group_analysis(ecommerce_df, group_col="nonexistent", measure_col="sales")

    def test_invalid_agg_raises(self, ecommerce_df):
        with pytest.raises(ValueError, match="Unsupported aggregation"):
            calculate_group_analysis(ecommerce_df, group_col="region", measure_col="sales", aggregation="stdev")


class TestDateTrends:
    def test_monthly_trends_chronological(self, ecommerce_df):
        res = calculate_date_trends(
            ecommerce_df,
            date_col="order_date",
            measure_col="sales",
            granularity="monthly",
            aggregation="sum",
        )
        assert res["labels"] == ["2023-01", "2023-02", "2023-03"]
        # Jan: 100 + 50 = 150; Feb: 200; Mar: 300 + 150 = 450
        assert res["values"] == [150.0, 200.0, 450.0]

    def test_invalid_dates_filtered_transparently(self):
        df = pd.DataFrame({
            "date": ["2023-01-01", "corrupt_date", "2023-01-02"],
            "val": [10.0, 20.0, 30.0],
        })
        res = calculate_date_trends(df, date_col="date", measure_col="val", granularity="daily")
        assert res["invalid_dates_count"] == 1
        assert res["valid_records_count"] == 2


class TestPeriodOverPeriod:
    def test_valid_monthly_pop(self, ecommerce_df):
        # Jan (150) -> Feb (200) -> Mar (450)
        # Comparison compares latest (Mar: 450) against prev (Feb: 200)
        # Absolute change = 450 - 200 = 250
        # Percentage change = 250 / 200 * 100 = 125.0%
        pop = calculate_period_over_period(
            ecommerce_df, date_col="order_date", measure_col="sales", granularity="monthly"
        )
        assert pop["is_valid_comparison"] is True
        assert pop["current_period"] == "2023-03"
        assert pop["previous_period"] == "2023-02"
        assert pop["current_value"] == 450.0
        assert pop["previous_value"] == 200.0
        assert pop["absolute_change"] == 250.0
        assert pop["percentage_change"] == 125.0
        assert pop["direction"] == "increase"

    def test_insufficient_periods_handled(self):
        df = pd.DataFrame({
            "date": ["2023-01-10", "2023-01-20"],
            "val": [10.0, 20.0],
        })
        # Both in Jan 2023 -> only 1 monthly period
        pop = calculate_period_over_period(df, date_col="date", measure_col="val", granularity="monthly")
        assert pop["is_valid_comparison"] is False
        assert "Insufficient periods" in pop["message"]

    def test_zero_previous_period_safe(self):
        df = pd.DataFrame({
            "date": ["2023-01-01", "2023-02-01"],
            "val": [0.0, 50.0],
        })
        pop = calculate_period_over_period(df, date_col="date", measure_col="val", granularity="monthly")
        assert pop["is_valid_comparison"] is True
        assert pop["previous_value"] == 0.0
        assert pop["current_value"] == 50.0
        assert pop["percentage_change"] is None  # no ZeroDivisionError


class TestDeterministicInsights:
    def test_generates_evidence_based_insights(self, ecommerce_df):
        insights = generate_deterministic_insights(ecommerce_df)
        assert len(insights) > 0
        categories = {i["category"] for i in insights}
        assert "Performance" in categories
        for item in insights:
            assert "title" in item
            assert "explanation" in item
            assert "severity" in item
            assert "recommended_action" in item
