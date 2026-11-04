import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Line } from "react-chartjs-2";

function getErrorMessage(error) {
  return error.response?.data?.error?.message || error.message || "The request failed.";
}

function AdvancedAnalytics({
  activeTab,
  apiUrl,
  datasetId,
  columns,
  numericColumns,
  dateColumns,
  onDatasetDeleted,
  onSelectDataset,
}) {
  const [question, setQuestion] = useState("");
  const [dateColumn, setDateColumn] = useState("");
  const [measureColumn, setMeasureColumn] = useState("");
  const [dimension, setDimension] = useState("");
  const [granularity, setGranularity] = useState("monthly");
  const [horizon, setHorizon] = useState(3);
  const [result, setResult] = useState(null);
  const [reportId, setReportId] = useState("");
  const [datasets, setDatasets] = useState([]);
  const [reports, setReports] = useState([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const reportListRequest = useRef(0);

  const dateOptions = useMemo(
    () => (dateColumns.length ? dateColumns : columns),
    [dateColumns, columns]
  );
  const dimensions = useMemo(
    () => columns.filter((column) => !numericColumns.includes(column) && !dateColumns.includes(column)),
    [columns, numericColumns, dateColumns]
  );

  useEffect(() => {
    setDateColumn(dateOptions[0] || "");
    setMeasureColumn(numericColumns[0] || "");
    setDimension(dimensions[0] || "");
    setResult(null);
    setReportId("");
    setError("");
  }, [datasetId, dateOptions, numericColumns, dimensions]);

  useEffect(() => {
    setResult(null);
    setReportId("");
    setError("");
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== "datasets") return undefined;
    let active = true;
    setDatasetsLoading(true);
    axios.get(`${apiUrl}/api/datasets`)
      .then((response) => {
        if (active) setDatasets(response.data.datasets || []);
      })
      .catch((requestError) => {
        if (active) setError(getErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setDatasetsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [activeTab, apiUrl]);

  useEffect(() => {
    if (activeTab !== "reports") return undefined;
    let active = true;
    const requestId = ++reportListRequest.current;
    axios.get(`${apiUrl}/api/reports`)
      .then((response) => {
        if (active && requestId === reportListRequest.current) {
          setReports(response.data.reports || []);
        }
      })
      .catch((requestError) => {
        if (active) setError(getErrorMessage(requestError));
      });
    return () => {
      active = false;
    };
  }, [activeTab, apiUrl]);

  const submitAnalysis = async (endpoint, payload, resultKey) => {
    if (!datasetId) {
      setError("Upload a dataset before running an analysis.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await axios.post(`${apiUrl}${endpoint}`, {
        dataset_id: datasetId,
        ...payload,
      });
      setResult(response.data);
      if (resultKey === "report") {
        reportListRequest.current += 1;
        setReportId(response.data.report_id);
        setReports((current) => [
          response.data,
          ...current.filter((report) => report.report_id !== response.data.report_id),
        ]);
      }
    } catch (requestError) {
      setResult(null);
      setReportId("");
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = async (targetReportId = reportId) => {
    if (!targetReportId) return;
    setLoading(true);
    setError("");
    try {
      const response = await axios.get(
        `${apiUrl}/api/reports/${targetReportId}/download`,
        { responseType: "blob" }
      );
      const objectUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `business_report_${targetReportId}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  if (activeTab === "ai") {
    return (
      <section className="section advanced-analytics">
        <h2>AI Business Analyst</h2>
        <p>Ask a supported question. The answer is calculated from this dataset; unsupported calculations are reported explicitly.</p>
        <label htmlFor="ai-question">Your question</label>
        <textarea
          id="ai-question"
          rows="3"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="For example: Which region generated the highest profit?"
        />
        <button
          type="button"
          disabled={loading || !question.trim()}
          onClick={() => submitAnalysis("/api/ai/analyze", { question }, "ai")}
        >
          {loading ? "Analyzing..." : "Analyze dataset"}
        </button>
        {error && <p className="advanced-error" role="alert">{error}</p>}
        {!result && !loading && !error && <p className="empty-text">No analysis yet. Ask a question about a numeric measure or dataset column.</p>}
        {result && (
          <div className="advanced-result" aria-live="polite">
            <h3>{result.interpreted_question}</h3>
            <p><strong>Method:</strong> {result.analytical_method}</p>
            <p>{result.explanation}</p>
            <p><strong>Business implication:</strong> {result.business_implications}</p>
            <p><strong>Next action:</strong> {result.recommended_next_action}</p>
            <pre>{JSON.stringify(result.result, null, 2)}</pre>
          </div>
        )}
      </section>
    );
  }

  if (activeTab === "rootcause") {
    return (
      <section className="section advanced-analytics">
        <h2>Root Cause Analysis</h2>
        <p>Compare the latest two observed periods and review dimensional contributors. Associations do not prove causation.</p>
        <div className="advanced-controls">
          <label>Date column<select value={dateColumn} onChange={(event) => setDateColumn(event.target.value)}>{dateOptions.map((column) => <option key={column}>{column}</option>)}</select></label>
          <label>Measure<select value={measureColumn} onChange={(event) => setMeasureColumn(event.target.value)}>{numericColumns.map((column) => <option key={column}>{column}</option>)}</select></label>
          <label>Dimension<select value={dimension} onChange={(event) => setDimension(event.target.value)}>{dimensions.map((column) => <option key={column}>{column}</option>)}</select></label>
          <label>Period<select value={granularity} onChange={(event) => setGranularity(event.target.value)}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option><option value="weekly">Weekly</option><option value="daily">Daily</option></select></label>
        </div>
        <button
          type="button"
          disabled={loading || !dateColumn || !measureColumn}
          onClick={() => submitAnalysis("/api/analytics/root-cause", {
            date_col: dateColumn,
            measure_col: measureColumn,
            dimensions: dimension ? [dimension] : [],
            granularity,
          }, "rootcause")}
        >
          {loading ? "Analyzing..." : "Analyze contributors"}
        </button>
        {error && <p className="advanced-error" role="alert">{error}</p>}
        {result && (
          <div className="advanced-result" aria-live="polite">
            <h3>{result.previous_period} to {result.current_period}: {result.direction}</h3>
            <p>{result.metric}: {Number(result.previous_value).toLocaleString()} to {Number(result.current_value).toLocaleString()} (change {Number(result.absolute_change).toLocaleString()})</p>
            {result.dimensions?.map((item) => (
              <div key={item.dimension}>
                <h4>{item.dimension} contributors</h4>
                <ul>{item.contributors.map((contributor) => (
                  <li key={contributor.group}>{contributor.group}: {Number(contributor.change).toLocaleString()} ({contributor.direction})</li>
                ))}</ul>
              </div>
            ))}
            <p>{result.limitations?.join(" ")}</p>
          </div>
        )}
        {!result && !loading && !error && <p className="empty-text">Select a date, numeric measure, and optional dimension to compare periods.</p>}
      </section>
    );
  }

  if (activeTab === "forecast") {
    const historical = result?.historical || [];
    const predictions = result?.forecast || [];
    const chartData = result ? {
      labels: [...historical.map((point) => point.period), ...predictions.map((point) => point.period)],
      datasets: [
        {
          label: `Historical ${measureColumn}`,
          data: [...historical.map((point) => point.value), ...predictions.map(() => null)],
          borderColor: "#4F46E5",
          tension: 0.25,
        },
        {
          label: "Baseline forecast",
          data: [...historical.map(() => null), ...predictions.map((point) => point.prediction)],
          borderColor: "#F59E0B",
          borderDash: [6, 4],
          tension: 0,
        },
      ],
    } : null;
    return (
      <section className="section advanced-analytics">
        <h2>Predictive Analytics</h2>
        <p>Evaluates a last-observation baseline with a chronological holdout. Forecasts are uncertain and are not guarantees.</p>
        <div className="advanced-controls">
          <label>Date column<select value={dateColumn} onChange={(event) => setDateColumn(event.target.value)}>{dateOptions.map((column) => <option key={column}>{column}</option>)}</select></label>
          <label>Measure<select value={measureColumn} onChange={(event) => setMeasureColumn(event.target.value)}>{numericColumns.map((column) => <option key={column}>{column}</option>)}</select></label>
          <label>Period<select value={granularity} onChange={(event) => setGranularity(event.target.value)}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option><option value="weekly">Weekly</option><option value="daily">Daily</option></select></label>
          <label>Horizon<select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>{[1, 2, 3, 6, 12, 24].map((value) => <option key={value} value={value}>{value} periods</option>)}</select></label>
        </div>
        <button
          type="button"
          disabled={loading || !dateColumn || !measureColumn}
          onClick={() => submitAnalysis("/api/analytics/forecast", {
            date_col: dateColumn,
            measure_col: measureColumn,
            granularity,
            horizon,
          }, "forecast")}
        >
          {loading ? "Forecasting..." : "Generate forecast"}
        </button>
        {error && <p className="advanced-error" role="alert">{error}</p>}
        {result && (
          <div className="advanced-result" aria-live="polite">
            <h3>Baseline validation</h3>
            <p>MAE: {Number(result.metrics.mae).toFixed(2)} · RMSE: {Number(result.metrics.rmse).toFixed(2)} · MAPE: {result.metrics.mape_percent === null ? "N/A" : `${Number(result.metrics.mape_percent).toFixed(2)}%`}</p>
            <p>{result.missing_period_policy}</p>
            {chartData && <div className="advanced-chart"><Line data={chartData} options={{
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: { title: { display: true, text: "Period" } },
                y: { title: { display: true, text: measureColumn } },
              },
            }} /></div>}
            <table><thead><tr><th>Period</th><th>Prediction</th><th>Lower bound</th><th>Upper bound</th></tr></thead>
              <tbody>{predictions.map((point) => <tr key={point.period}><td>{point.period}</td><td>{Number(point.prediction).toLocaleString()}</td><td>{Number(point.lower_bound).toLocaleString()}</td><td>{Number(point.upper_bound).toLocaleString()}</td></tr>)}</tbody>
            </table>
            <p>{result.uncertainty}</p>
          </div>
        )}
        {!result && !loading && !error && <p className="empty-text">At least eight periods of valid date and numeric data are required.</p>}
      </section>
    );
  }

  if (activeTab === "datasets") {
    const deleteDataset = async (targetDatasetId) => {
      if (!window.confirm("Delete this dataset and its generated reports?")) return;
      setLoading(true);
      setError("");
      try {
        await axios.delete(`${apiUrl}/api/datasets/${targetDatasetId}`);
        setDatasets((current) => current.filter((item) => item.dataset_id !== targetDatasetId));
        onDatasetDeleted?.(targetDatasetId);
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      } finally {
        setLoading(false);
      }
    };
    return (
      <section className="section advanced-analytics">
        <h2>Account & Dataset Management</h2>
        <p>Review and open your saved datasets, or permanently delete a dataset and its generated reports.</p>
        {error && <p className="advanced-error" role="alert">{error}</p>}
        {datasetsLoading && <p className="empty-text">Loading your datasets...</p>}
        {!datasetsLoading && datasets.length === 0 && <p className="empty-text">No active datasets are saved to this account.</p>}
        {datasets.length > 0 && (
          <div className="table-wrapper">
            <table>
              <thead><tr><th>Dataset</th><th>Uploaded</th><th>Expires</th><th>Rows</th><th>Actions</th></tr></thead>
              <tbody>{datasets.map((dataset) => (
                <tr key={dataset.dataset_id}>
                  <td>{dataset.original_filename}</td>
                  <td>{dataset.upload_timestamp ? new Date(dataset.upload_timestamp).toLocaleString() : "—"}</td>
                  <td>{dataset.expires_at ? new Date(dataset.expires_at).toLocaleString() : "—"}</td>
                  <td>{dataset.summary?.total_rows ?? "—"}</td>
                  <td className="dataset-actions">
                    <button type="button" onClick={() => onSelectDataset?.(dataset)}>Open</button>
                    <button type="button" className="dataset-delete-btn" disabled={loading} onClick={() => deleteDataset(dataset.dataset_id)}>Delete</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="section advanced-analytics">
      <h2>Business Reports</h2>
      <p>Generate an evidence-based PDF containing data quality, available KPIs, segment results, insights, trends, root-cause comparisons, and forecasts when supported by the dataset.</p>
      <div className="advanced-controls">
        <label>Date column (optional)<select value={dateColumn} onChange={(event) => setDateColumn(event.target.value)}><option value="">Automatic</option>{dateOptions.map((column) => <option key={column}>{column}</option>)}</select></label>
        <label>Measure (optional)<select value={measureColumn} onChange={(event) => setMeasureColumn(event.target.value)}><option value="">Automatic</option>{numericColumns.map((column) => <option key={column}>{column}</option>)}</select></label>
      </div>
      <button type="button" disabled={loading || !datasetId} onClick={() => submitAnalysis("/api/reports", {
        date_col: dateColumn || null,
        measure_col: measureColumn || null,
        dimensions: dimension ? [dimension] : [],
        granularity,
        horizon,
      }, "report")}>
        {loading ? "Generating report..." : "Generate PDF report"}
      </button>
      {reportId && <button type="button" className="report-download-btn" disabled={loading} onClick={() => downloadReport()}>Download PDF</button>}
      {error && <p className="advanced-error" role="alert">{error}</p>}
      {reportId && <p className="advanced-result" role="status">Report {reportId} is ready for download.</p>}
      {!reportId && !loading && !error && <p className="empty-text">Generate a report for the currently selected dataset.</p>}
      {reports.length > 0 && (
        <div className="table-wrapper">
          <h3>Saved reports</h3>
          <table>
            <thead><tr><th>Dataset</th><th>Generated</th><th>Download</th></tr></thead>
            <tbody>{reports.map((report) => (
              <tr key={report.report_id}>
                <td>{report.dataset_name}</td>
                <td>{new Date(report.created_at).toLocaleString()}</td>
                <td><button type="button" onClick={() => downloadReport(report.report_id)}>Download PDF</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default AdvancedAnalytics;
