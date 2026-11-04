"""Owned PDF business-report generation and persistence."""

from datetime import datetime, timezone
from html import escape
import io
import logging
import os
import uuid

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import storage
from analytics.business_intelligence import (
    calculate_business_kpis,
    calculate_date_trends,
    calculate_group_analysis,
    discover_business_kpis,
    generate_deterministic_insights,
)
from analytics.data_quality import detect_date_columns, generate_quality_report
from analytics.forecasting import forecast_series
from analytics.root_cause import analyze_root_cause
from database import SessionLocal
from models import BusinessReport, Dataset

logger = logging.getLogger("csv_dashboard")


def _paragraph(value, style):
    return Paragraph(escape(str(value)), style)


def _section(elements, title, rows, styles):
    elements.append(Paragraph(escape(title), styles["Heading2"]))
    if not rows:
        elements.append(Paragraph("No supported results were available for this section.", styles["BodyText"]))
        elements.append(Spacer(1, 0.12 * inch))
        return
    table = Table(rows, repeatRows=1, hAlign="LEFT", colWidths=[2.1 * inch, 4.7 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eaf7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172554")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.extend([table, Spacer(1, 0.18 * inch)])


def _make_pdf(
    dataset_name: str,
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    options: dict,
) -> bytes:
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("Business Intelligence Report", styles["Title"]),
        Paragraph(f"Generated: {datetime.now(timezone.utc).isoformat()}", styles["BodyText"]),
        Paragraph(f"Dataset: {dataset_name}", styles["BodyText"]),
        Spacer(1, 0.2 * inch),
    ]

    overview = [
        ["Dataset overview", "Calculated value"],
        ["Rows", f"{len(raw_df):,}"],
        ["Columns", f"{len(raw_df.columns):,}"],
        ["Numeric columns", f"{len(cleaned_df.select_dtypes(include=['number']).columns):,}"],
    ]
    _section(elements, "1. Dataset overview", overview, styles)

    quality = generate_quality_report(raw_df)
    quality_score = quality["quality_score"]
    _section(
        elements,
        "2. Data quality",
        [
            ["Measure", "Calculated value"],
            ["Heuristic score", f"{quality_score['score']}/100 ({quality_score['grade']})"],
            ["Missing cells", quality["overview"]["total_missing_cells"]],
            ["Duplicate rows", quality["duplicate_analysis"]["duplicate_rows_count"]],
            ["Potential IQR outliers", quality["outlier_analysis"]["total_outliers_count"]],
        ],
        styles,
    )
    elements.append(Paragraph(escape(quality_score["limitations"]), styles["BodyText"]))
    elements.append(Spacer(1, 0.16 * inch))

    discovery = discover_business_kpis(cleaned_df)
    mappings = discovery.get("inferred_mappings", {})
    kpis = calculate_business_kpis(
        cleaned_df,
        revenue_col=mappings.get("revenue_col"),
        profit_col=mappings.get("profit_col"),
        quantity_col=mappings.get("quantity_col"),
        order_id_col=mappings.get("order_id_col"),
        discount_col=mappings.get("discount_col"),
    )
    kpi_rows = [["KPI", "Calculated value"]]
    kpi_rows.extend(
        [
            (item["metric_name"], item["formatted_value"])
            for item in kpis[:12]
        ]
    )
    _section(elements, "3. Business KPIs", kpi_rows, styles)

    date_col = options.get("date_col")
    if date_col not in cleaned_df.columns:
        detected_dates = detect_date_columns(cleaned_df)
        date_col = detected_dates[0] if detected_dates else None
    measure_col = options.get("measure_col") or mappings.get("revenue_col")
    if measure_col not in cleaned_df.columns:
        additive = [row["column"] for row in discovery.get("candidate_measures", []) if row["is_additive"]]
        measure_col = additive[0] if additive else None

    segment_rows = [["Segment", "Calculated value"]]
    categorical = [
        str(column)
        for column in cleaned_df.columns
        if column != measure_col
        and not pd.api.types.is_numeric_dtype(cleaned_df[column])
        and not pd.api.types.is_datetime64_any_dtype(cleaned_df[column])
    ]
    if categorical and measure_col in cleaned_df.columns:
        segments = calculate_group_analysis(
            cleaned_df,
            group_col=categorical[0],
            measure_col=measure_col,
            aggregation="sum",
            limit=5,
        )
        segment_rows.extend(
            [(row["group"], row["value"]) for row in segments.get("records", [])]
        )
    _section(elements, "4. Segment performance", segment_rows, styles)

    insights = generate_deterministic_insights(
        cleaned_df,
        revenue_col=mappings.get("revenue_col"),
        profit_col=mappings.get("profit_col"),
        date_col=date_col,
    )
    insight_rows = [["Observation", "Evidence / recommended action"]]
    insight_rows.extend(
        [
            (
                f"{item['title']} ({item['category']})",
                f"{item['explanation']} Action: {item['recommended_action']}",
            )
            for item in insights[:10]
        ]
    )
    _section(elements, "5. Evidence-based insights and actions", insight_rows, styles)

    if date_col and measure_col and date_col in cleaned_df.columns and measure_col in cleaned_df.columns:
        try:
            trends = calculate_date_trends(
                cleaned_df,
                date_col=date_col,
                measure_col=measure_col,
                granularity=options.get("granularity", "monthly"),
            )
            trend_rows = [["Period", f"Total {measure_col}"]]
            trend_rows.extend(
                [(point["period"], point["value"]) for point in trends["data_points"][-12:]]
            )
            _section(elements, "6. Recent trend", trend_rows, styles)
        except ValueError as exc:
            logger.info("Trend section omitted from report: %s", exc)

        dimensions = options.get("dimensions") or categorical[:3]
        try:
            root = analyze_root_cause(
                cleaned_df,
                date_col=date_col,
                measure_col=measure_col,
                dimensions=dimensions,
                granularity=options.get("granularity", "monthly"),
            )
            cause_rows = [["Period comparison", "Calculated result"]]
            cause_rows.extend(
                [
                    ["Previous period", f"{root['previous_period']}: {root['previous_value']:,.2f}"],
                    ["Current period", f"{root['current_period']}: {root['current_value']:,.2f}"],
                    ["Observed change", f"{root['direction']}: {root['absolute_change']:,.2f}"],
                ]
            )
            for dimension_result in root["dimensions"]:
                for item in dimension_result["contributors"][:3]:
                    cause_rows.append(
                        [
                            f"{dimension_result['dimension']}: {item['group']}",
                            f"Change {item['change']:,.2f}; association only",
                        ]
                    )
            _section(elements, "7. Root-cause contributors (associations, not causation)", cause_rows, styles)
        except ValueError as exc:
            logger.info("Root-cause section omitted from report: %s", exc)

        try:
            forecast = forecast_series(
                cleaned_df,
                date_col=date_col,
                measure_col=measure_col,
                granularity=options.get("granularity", "monthly"),
                horizon=options.get("horizon", 3),
            )
            forecast_rows = [["Forecast period", "Baseline and uncertainty range"]]
            forecast_rows.extend(
                [
                    (
                        item["period"],
                        f"{item['prediction']:,.2f} ({item['lower_bound']:,.2f} to {item['upper_bound']:,.2f})",
                    )
                    for item in forecast["forecast"]
                ]
            )
            _section(elements, "8. Baseline forecast (not guaranteed)", forecast_rows, styles)
        except ValueError as exc:
            logger.info("Forecast section omitted from report: %s", exc)

    elements.append(
        Paragraph(
            "All measures are calculated from the uploaded dataset. Heuristic scores, "
            "segment comparisons, and forecasts have limitations; verify definitions and "
            "business context before making decisions.",
            styles["Italic"],
        )
    )
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Business Intelligence Report",
    ).build(elements)
    return buffer.getvalue()


def create_business_report(
    user_id: str,
    dataset_id: str,
    dataset_name: str,
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    options: dict | None = None,
) -> BusinessReport:
    """Write a generated PDF and commit owner-scoped report metadata."""
    report_id = str(uuid.uuid4())
    report_dir = os.path.dirname(storage.get_report_path(report_id))
    os.makedirs(report_dir, exist_ok=True)
    report_path = storage.get_report_path(report_id)
    temporary_path = f"{report_path}.tmp"
    db = SessionLocal()
    file_created = False
    try:
        now = datetime.now(timezone.utc)
        dataset = (
            db.query(Dataset)
            .filter(
                Dataset.id == dataset_id,
                Dataset.user_id == user_id,
                Dataset.deletion_pending.is_(False),
                Dataset.expires_at > now,
            )
            .with_for_update()
            .first()
        )
        if not dataset:
            raise LookupError("The dataset is no longer available.")

        pdf_content = _make_pdf(dataset_name, raw_df, cleaned_df, options or {})
        with open(temporary_path, "xb") as report_file:
            report_file.write(pdf_content)
        os.replace(temporary_path, report_path)
        file_created = True
        still_available = (
            db.query(Dataset.id)
            .filter(
                Dataset.id == dataset_id,
                Dataset.user_id == user_id,
                Dataset.deletion_pending.is_(False),
                Dataset.expires_at > datetime.now(timezone.utc),
            )
            .with_for_update()
            .scalar()
        )
        if not still_available:
            raise LookupError("The dataset is no longer available.")
        report = BusinessReport(
            id=report_id,
            user_id=user_id,
            dataset_id=dataset_id,
            storage_path=report_path,
            created_at=now,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
    except Exception:
        db.rollback()
        for path in (temporary_path, report_path if file_created else None):
            if not path:
                continue
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.exception("Could not remove report files after metadata failure.")
        raise
    finally:
        db.close()
