import React, { useCallback, useEffect, useState, useRef } from "react";
import axios from "axios";
import html2canvas from "html2canvas";
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  Database,
  FileText,
  FolderKanban,
  LayoutGrid,
  LogOut,
  Menu,
  SearchCheck,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRound,
} from "lucide-react";
import AdvancedAnalytics from "./AdvancedAnalytics.jsx";
import { resolveApiUrl } from "./apiConfig.js";
import {
  Bar,
  Line,
  Pie,
  Scatter
} from "react-chartjs-2";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler
} from "chart.js";

import ChartDataLabels from "chartjs-plugin-datalabels";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Tooltip,
  Legend,
  ChartDataLabels,
  Filler
);

const CHART_THEME = {
  primary: "#4F46E5",
  secondary: "#06B6D4",
  accent: "#F59E0B",
  success: "#10B981",
  danger: "#EF4444",
  background: "#0F172A",
  card: "#1E293B",
  text: "#F8FAFC",
  grid: "rgba(148,163,184,0.18)",
  palette: [
    "#4F46E5",
    "#06B6D4",
    "#F59E0B",
    "#10B981",
    "#EF4444",
    "#A855F7",
    "#22D3EE",
    "#FBBF24"
  ]
};

const getChartPalette = (count) =>
  Array.from({ length: count }, (_, index) => CHART_THEME.palette[index % CHART_THEME.palette.length]);

const getChartOptions = (title, isPie = false) => ({
  responsive: true,
  maintainAspectRatio: false,
  layout: {
    padding: 16
  },
  plugins: {
    title: {
      display: true,
      text: title,
      color: CHART_THEME.text,
      font: {
        size: 18,
        weight: "700"
      },
      padding: {
        bottom: 14
      },
      align: "center"
    },
    legend: {
      display: true,
      position: "bottom",
      labels: {
        color: CHART_THEME.text,
        boxWidth: 12,
        boxHeight: 12,
        padding: 16,
        usePointStyle: true
      }
    },
    tooltip: {
      enabled: true,
      backgroundColor: "#111827",
      titleColor: "#F8FAFC",
      bodyColor: "#F8FAFC",
      borderColor: "#475569",
      borderWidth: 1,
      cornerRadius: 10,
      padding: 12,
      callbacks: {
        label: function (context) {
          const label = context.dataset.label ? `${context.dataset.label}: ` : "";
          const value = context.parsed?.y ?? context.parsed ?? context.raw ?? "";
          return `${label}${value}`;
        }
      }
    },
    datalabels: {
      display: false
    }
  },
  scales: isPie
    ? {}
    : {
        x: {
          grid: {
            color: CHART_THEME.grid,
            drawBorder: false
          },
          ticks: {
            color: CHART_THEME.text
          },
          title: {
            color: CHART_THEME.text,
            font: {
              size: 14,
              weight: "600"
            }
          }
        },
        y: {
          grid: {
            color: CHART_THEME.grid,
            drawBorder: false
          },
          ticks: {
            color: CHART_THEME.text
          },
          title: {
            color: CHART_THEME.text,
            font: {
              size: 14,
              weight: "600"
            }
          }
        }
      },
  elements: {
    bar: {
      borderRadius: 14,
      borderSkipped: false,
      backgroundColor: CHART_THEME.primary
    },
    line: {
      tension: 0.32,
      borderWidth: 3,
      fill: true
    },
    point: {
      radius: 4,
      hoverRadius: 7
    }
  }
});

const chartWrapperStyle = {
  backgroundColor: CHART_THEME.background,
  padding: "18px",
  borderRadius: "22px",
  boxShadow: "0 18px 60px rgba(15,23,42,0.45)",
  color: CHART_THEME.text,
  minHeight: "360px"
};

const API_URL = resolveApiUrl({
  apiUrl: import.meta.env.VITE_API_URL,
  mode: import.meta.env.MODE,
  location: window.location,
});
axios.defaults.withCredentials = true;

// Helper: extract a human-readable message from backend error responses.
function extractErrorMessage(err, fallback = "An unexpected error occurred.") {
  const data = err.response?.data;
  if (!data) {
    if (err.code === "ERR_NETWORK") return "Cannot reach the server. Check that the backend is running.";
    if (err.code === "ERR_CANCELED") return "Request was cancelled.";
    return err.message || fallback;
  }
  if (data.error && typeof data.error === "object" && data.error.message) {
    return data.error.message;
  }
  if (data.error && typeof data.error === "string") {
    return data.error;
  }
  return fallback;
}

function App() {
  const chartBoxRef = useRef(null);
  
  // Real Backend Auth State (Phase 3)
  const [authMode, setAuthMode] = useState("login"); // "login" | "register"
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [confirmPasswordError, setConfirmPasswordError] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [loggedInEmail, setLoggedInEmail] = useState("");
  const [csrfToken, setCsrfToken] = useState("");

  // Check existing session on mount
  useEffect(() => {
    let isMounted = true;
    axios
      .get(`${API_URL}/api/auth/me`)
      .then((res) => {
        if (isMounted && res.data?.user?.email) {
          setIsLoggedIn(true);
          setLoggedInEmail(res.data.user.email);
          setCsrfToken(res.data.csrf_token || "");
        }
      })
      .catch(() => {
        if (isMounted) {
          setIsLoggedIn(false);
          setLoggedInEmail("");
        }
      })
      .finally(() => {
        if (isMounted) {
          setAuthChecking(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);
  
  // Dataset and Core Phase 1 State
  const [file, setFile] = useState(null);
  const [datasetId, setDatasetId] = useState("");
  const [columns, setColumns] = useState([]);
  const [numericColumns, setNumericColumns] = useState([]);
  const [dateColumns, setDateColumns] = useState([]);
  const [preview, setPreview] = useState([]);
  const [filteredPreview, setFilteredPreview] = useState([]);
  const [searchFilter, setSearchFilter] = useState("");
  const [summary, setSummary] = useState(null);

  const [chartType, setChartType] = useState("Bar");
  const [xAxis, setXAxis] = useState("");
  const [yAxis, setYAxis] = useState("");
  const [chartData, setChartData] = useState(null);

  const [insights, setInsights] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [askTable, setAskTable] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Phase 2 Navigation & Engine States
  const [activeTab, setActiveTab] = useState("charts");

  // Data Quality State
  const [qualityReport, setQualityReport] = useState(null);
  const [qualityLoading, setQualityLoading] = useState(false);

  // Business Intelligence State
  const [biKpis, setBiKpis] = useState([]);
  const [biInsights, setBiInsights] = useState([]);
  const [biLoading, setBiLoading] = useState(false);
  const [groupCol, setGroupCol] = useState("");
  const [groupMeasureCol, setGroupMeasureCol] = useState("");
  const [groupAgg, setGroupAgg] = useState("sum");
  const [groupResult, setGroupResult] = useState(null);
  const [groupLoading, setGroupLoading] = useState(false);
  const [groupChartData, setGroupChartData] = useState(null);

  // Trends & Comparisons State
  const [trendDateCol, setTrendDateCol] = useState("");
  const [trendMeasureCol, setTrendMeasureCol] = useState("");
  const [trendGranularity, setTrendGranularity] = useState("monthly");
  const [trendAgg, setTrendAgg] = useState("sum");
  const [trendResult, setTrendResult] = useState(null);
  const [popResult, setPopResult] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendChartData, setTrendChartData] = useState(null);

  const resetDashboardState = useCallback(() => {
    setFile(null);
    setDatasetId("");
    setColumns([]);
    setNumericColumns([]);
    setDateColumns([]);
    setPreview([]);
    setFilteredPreview([]);
    setSearchFilter("");
    setSummary(null);
    setChartType("Bar");
    setXAxis("");
    setYAxis("");
    setChartData(null);
    setInsights([]);
    setQuestion("");
    setAnswer("");
    setAskTable([]);
    setLoading(false);
    setError("");
    setActiveTab("charts");
    setQualityReport(null);
    setQualityLoading(false);
    setBiKpis([]);
    setBiInsights([]);
    setBiLoading(false);
    setGroupResult(null);
    setGroupChartData(null);
    setGroupLoading(false);
    setTrendResult(null);
    setPopResult(null);
    setTrendChartData(null);
    setTrendLoading(false);
  }, []);

  useEffect(() => {
    const headerName = "X-CSRF-Token";
    if (csrfToken) {
      axios.defaults.headers.common[headerName] = csrfToken;
    } else {
      delete axios.defaults.headers.common[headerName];
    }
    return () => {
      delete axios.defaults.headers.common[headerName];
    };
  }, [csrfToken]);

  useEffect(() => {
    const interceptorId = axios.interceptors.response.use(
      (response) => response,
      (err) => {
        if (err.response?.status === 401) {
          let pathname = "";
          try {
            pathname = new URL(err.config?.url || "", API_URL).pathname;
          } catch {
            pathname = "";
          }
          const expectedAuthEndpoints = new Set([
            "/api/auth/me",
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/logout",
            "/api/auth/csrf",
          ]);
          if (!expectedAuthEndpoints.has(pathname)) {
            setIsLoggedIn(false);
            setLoggedInEmail("");
            setLoginPassword("");
            setConfirmPassword("");
            setAuthMode("login");
            setCsrfToken("");
            setAuthError("Your session has expired. Please sign in again.");
            resetDashboardState();
          }
        }
        return Promise.reject(err);
      }
    );
    return () => axios.interceptors.response.eject(interceptorId);
  }, [resetDashboardState]);

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setEmailError("");
    setPasswordError("");
    setConfirmPasswordError("");
    setAuthError("");

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const normalizedEmail = loginEmail.trim();
    let hasError = false;

    if (!emailRegex.test(normalizedEmail)) {
      setEmailError("Please enter a valid email address.");
      hasError = true;
    }

    if (!loginPassword.trim()) {
      setPasswordError("Password cannot be empty.");
      hasError = true;
    } else if (loginPassword.length < 6) {
      setPasswordError("Password must be at least 6 characters.");
      hasError = true;
    }

    if (authMode === "register") {
      if (!confirmPassword.trim()) {
        setConfirmPasswordError("Please confirm your password.");
        hasError = true;
      } else if (loginPassword !== confirmPassword) {
        setConfirmPasswordError("Passwords do not match.");
        hasError = true;
      }
    }

    if (hasError) return;

    try {
      setAuthLoading(true);
      const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
      const resp = await axios.post(`${API_URL}${endpoint}`, {
        email: normalizedEmail,
        password: loginPassword,
      });

      const user = resp.data?.user;
      setIsLoggedIn(true);
      setLoggedInEmail(user?.email || normalizedEmail);
      setCsrfToken(resp.data?.csrf_token || "");
      setLoginPassword("");
      setConfirmPassword("");
      setAuthError("");
    } catch (err) {
      const msg = extractErrorMessage(
        err,
        authMode === "register" ? "Registration failed." : "Invalid credentials."
      );
      setAuthError(msg);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API_URL}/api/auth/logout`);
    } catch (err) {
      // Gracefully clear state on logout error
    }
    setIsLoggedIn(false);
    setLoggedInEmail("");
    setCsrfToken("");
    setLoginEmail("");
    setLoginPassword("");
    setConfirmPassword("");
    setEmailError("");
    setPasswordError("");
    setConfirmPasswordError("");
    setAuthError("");
    
    // Reset dashboard state
    setFile(null);
    setDatasetId("");
    setColumns([]);
    setNumericColumns([]);
    setDateColumns([]);
    setPreview([]);
    setFilteredPreview([]);
    setSearchFilter("");
    setSummary(null);
    setChartType("Bar");
    setXAxis("");
    setYAxis("");
    setChartData(null);
    setInsights([]);
    setQuestion("");
    setAnswer("");
    setAskTable([]);

    // Reset Phase 2 states
    setActiveTab("charts");
    setQualityReport(null);
    setBiKpis([]);
    setBiInsights([]);
    setGroupResult(null);
    setGroupChartData(null);
    setTrendResult(null);
    setPopResult(null);
    setTrendChartData(null);
  };

  const uploadFile = async () => {
    if (!file) {
      setError("Please select a CSV or Excel file.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(`${API_URL}/upload`, formData);

      const dId = response.data.dataset_id;
      const cols = response.data.columns;
      const numCols = response.data.numeric_columns;
      const dtCols = response.data.date_columns || [];

      setDatasetId(dId);
      setColumns(cols);
      setNumericColumns(numCols);
      setDateColumns(dtCols);
      setPreview(response.data.preview);
      setFilteredPreview(response.data.preview);
      setSummary(response.data.summary);
      setSearchFilter("");

      setXAxis(cols[0] || "");
      setYAxis(numCols[0] || cols[0] || "");

      setChartData(null);
      setInsights([]);
      setAnswer("");
      setAskTable([]);

      // Phase 2 resets and pre-selections
      setQualityReport(null);
      setBiKpis([]);
      setBiInsights([]);
      setGroupResult(null);
      setGroupChartData(null);
      setTrendResult(null);
      setPopResult(null);
      setTrendChartData(null);

      // Pre-select group column (first non-numeric) & measure (first numeric)
      const firstCategorical = cols.find(c => !numCols.includes(c)) || cols[0] || "";
      setGroupCol(firstCategorical);
      setGroupMeasureCol(numCols[0] || "");

      // Pre-select date column
      const firstDate = (dtCols.length > 0 ? dtCols[0] : (cols.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("year") || c.toLowerCase().includes("day")) || cols[0])) || "";
      setTrendDateCol(firstDate);
      setTrendMeasureCol(numCols[0] || "");

      setActiveTab("charts");
    } catch (err) {
      const errorMsg = extractErrorMessage(err, "File upload failed.");
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const fetchDataQuality = async (targetId = datasetId) => {
    if (!targetId) return;
    try {
      setQualityLoading(true);
      setError("");
      const resp = await axios.get(`${API_URL}/api/data-quality?dataset_id=${targetId}`);
      setQualityReport(resp.data);
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to load data quality report."));
    } finally {
      setQualityLoading(false);
    }
  };

  const fetchBIKpis = async (targetId = datasetId) => {
    if (!targetId) return;
    try {
      setBiLoading(true);
      setError("");
      const resp = await axios.post(`${API_URL}/api/bi/kpis`, { dataset_id: targetId });
      setBiKpis(resp.data.kpis || []);
      setBiInsights(resp.data.insights || []);
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to calculate business KPIs."));
    } finally {
      setBiLoading(false);
    }
  };

  const runGroupAnalysis = async () => {
    if (!datasetId || !groupCol || !groupMeasureCol) {
      setError("Please select both a grouping column and a measure column.");
      return;
    }
    try {
      setGroupLoading(true);
      setError("");
      const resp = await axios.post(`${API_URL}/api/bi/group-analysis`, {
        dataset_id: datasetId,
        group_col: groupCol,
        measure_col: groupMeasureCol,
        aggregation: groupAgg,
        limit: 15
      });
      setGroupResult(resp.data);

      const labels = (resp.data.records || []).map(r => r.group);
      const values = (resp.data.records || []).map(r => r.value);
      const palette = getChartPalette(labels.length);

      setGroupChartData({
        labels,
        datasets: [{
          label: `${groupAgg.toUpperCase()} of ${groupMeasureCol}`,
          data: values,
          backgroundColor: palette,
          borderRadius: 8
        }]
      });
    } catch (err) {
      setError(extractErrorMessage(err, "Group analysis failed."));
    } finally {
      setGroupLoading(false);
    }
  };

  const runTrendAnalysis = async () => {
    if (!datasetId || !trendDateCol || !trendMeasureCol) {
      setError("Please select both a date column and a measure column.");
      return;
    }
    try {
      setTrendLoading(true);
      setError("");
      const [trendResp, popResp] = await Promise.all([
        axios.post(`${API_URL}/api/bi/trends`, {
          dataset_id: datasetId,
          date_col: trendDateCol,
          measure_col: trendMeasureCol,
          granularity: trendGranularity,
          aggregation: trendAgg
        }),
        axios.post(`${API_URL}/api/bi/period-comparison`, {
          dataset_id: datasetId,
          date_col: trendDateCol,
          measure_col: trendMeasureCol,
          granularity: trendGranularity,
          aggregation: trendAgg
        })
      ]);

      setTrendResult(trendResp.data);
      setPopResult(popResp.data);

      setTrendChartData({
        labels: trendResp.data.labels || [],
        datasets: [{
          label: `${trendGranularity.toUpperCase()} ${trendAgg.toUpperCase()} of ${trendMeasureCol}`,
          data: trendResp.data.values || [],
          borderColor: CHART_THEME.secondary,
          backgroundColor: "rgba(6, 182, 212, 0.2)",
          tension: 0.32,
          fill: true,
          pointBackgroundColor: CHART_THEME.secondary,
          pointRadius: 5
        }]
      });
    } catch (err) {
      setError(extractErrorMessage(err, "Trend analysis failed."));
    } finally {
      setTrendLoading(false);
    }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setError("");
    setIsSidebarOpen(false);
    if (tab === "quality" && !qualityReport && datasetId) {
      fetchDataQuality(datasetId);
    } else if (tab === "bi" && biKpis.length === 0 && datasetId) {
      fetchBIKpis(datasetId);
    } else if (tab === "trends" && !trendResult && datasetId) {
      if (trendDateCol && trendMeasureCol) {
        runTrendAnalysis();
      }
    }
  };

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 980) {
        setIsSidebarOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const sidebarSections = [
    {
      title: "WORKSPACE",
      items: [
        { key: "charts", label: "Overview & Charts", icon: LayoutGrid },
        { key: "quality", label: "Data Quality & Profile", icon: ShieldCheck },
        { key: "bi", label: "Business Intelligence", icon: BriefcaseBusiness },
        { key: "trends", label: "Trends & Comparisons", icon: Activity },
      ],
    },
    {
      title: "AI & INTELLIGENCE",
      items: [
        { key: "ai", label: "AI Analyst", icon: Sparkles },
        { key: "rootcause", label: "Root Cause Analysis", icon: SearchCheck },
        { key: "forecast", label: "Predictive Analytics", icon: BarChart3 },
      ],
    },
    {
      title: "REPORTING",
      items: [{ key: "reports", label: "Business Reports", icon: FileText }],
    },
    {
      title: "DATA MANAGEMENT",
      items: [
        { key: "upload", label: "Upload Dataset", icon: UploadCloud },
        { key: "datasets", label: "Dataset Management", icon: FolderKanban },
      ],
    },
    {
      title: "PREFERENCES",
      items: [{ key: "settings", label: "Settings", icon: Settings }],
    },
  ];

  const openSavedDataset = (dataset) => {
    resetDashboardState();
    setDatasetId(dataset.dataset_id);
    setColumns(dataset.columns || []);
    setNumericColumns(dataset.numeric_columns || []);
    setDateColumns(dataset.date_columns || []);
    setPreview(dataset.preview || []);
    setFilteredPreview(dataset.preview || []);
    setSummary(dataset.summary || null);
    setXAxis(dataset.columns?.[0] || "");
    setYAxis(dataset.numeric_columns?.[0] || dataset.columns?.[0] || "");
    setGroupCol(dataset.columns?.find((column) => !(dataset.numeric_columns || []).includes(column)) || "");
    setGroupMeasureCol(dataset.numeric_columns?.[0] || "");
    setTrendDateCol(dataset.date_columns?.[0] || "");
    setTrendMeasureCol(dataset.numeric_columns?.[0] || "");
  };

  const handleSavedDatasetDeleted = (deletedDatasetId) => {
    if (deletedDatasetId === datasetId) {
      resetDashboardState();
    }
  };

  const generateChart = async () => {
    if (!datasetId || !xAxis) {
      setError("Please upload data and select X-axis.");
      return;
    }

    if (chartType !== "Histogram" && !yAxis) {
      setError("Please select Y-axis.");
      return;
    }

    try {
      setError("");

      const response = await axios.post(`${API_URL}/chart-data`, {
        dataset_id: datasetId,
        chart_type: chartType,
        x_axis: xAxis,
        y_axis: yAxis
      });

      const values = response.data.values;
      const palette = getChartPalette(response.data.labels.length);
      const baseDataset = {
        label: yAxis || xAxis,
        data: values,
        borderColor: CHART_THEME.primary,
        borderWidth: 2,
        hoverBorderColor: "#ffffff",
        hoverBorderWidth: 2,
        borderRadius: 14,
        tension: 0.32
      };

      if (chartType === "Line") {
        baseDataset.backgroundColor = "rgba(79,70,229,0.22)";
        baseDataset.pointBackgroundColor = CHART_THEME.primary;
        baseDataset.pointHoverBackgroundColor = CHART_THEME.accent;
        baseDataset.pointBorderColor = "#ffffff";
      } else if (chartType === "Scatter") {
        baseDataset.backgroundColor = CHART_THEME.secondary;
        baseDataset.pointRadius = 6;
      } else {
        baseDataset.backgroundColor = palette;
        baseDataset.hoverBackgroundColor = palette.map((color) => color);
      }

      setChartData({
        labels: response.data.labels,
        datasets: [baseDataset]
      });
    } catch (err) {
      setError(extractErrorMessage(err, "Chart generation failed."));
    }
  };

  const generateInsights = async () => {
    try {
      setError("");

      const response = await axios.post(`${API_URL}/insights`, {
        dataset_id: datasetId,
        x_axis: xAxis,
        y_axis: yAxis
      });

      setInsights(response.data.insights);
    } catch (err) {
      setError(extractErrorMessage(err, "Insights generation failed."));
    }
  };

  const askData = async () => {
    if (!question.trim()) {
      setError("Please enter a question.");
      return;
    }

    try {
      setError("");

      const response = await axios.post(`${API_URL}/ask`, {
        dataset_id: datasetId,
        question
      });

      setAnswer(response.data.answer);
      setAskTable(response.data.table || []);
    } catch (err) {
      setError(extractErrorMessage(err, "Ask Your Data failed."));
    }
  };

  const downloadCleanedData = () => {
    if (!datasetId) return;
    window.open(`${API_URL}/download/${datasetId}`, "_blank");
  };

  const handleSearch = (e) => {
    const searchTerm = e.target.value.toLowerCase();
    setSearchFilter(searchTerm);
    
    if (searchTerm === "") {
      setFilteredPreview(preview);
    } else {
      const filtered = preview.filter((row) => {
        return columns.some((col) => {
          const cellValue = String(row[col]).toLowerCase();
          return cellValue.includes(searchTerm);
        });
      });
      setFilteredPreview(filtered);
    }
  };

  const downloadChart = async () => {
    if (!chartBoxRef.current) {
      setError("No chart to download");
      return;
    }
    
    try {
      setError("");
      const canvas = await html2canvas(chartBoxRef.current, {
        backgroundColor: CHART_THEME.background,
        scale: 2
      });
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = `chart_${new Date().getTime()}.png`;
      link.click();
    } catch (err) {
      setError("Failed to download chart: " + err.message);
    }
  };

  const getColumnDataTypes = () => {
    return columns.map((col) => ({
      name: col,
      type: numericColumns.includes(col) ? "Numeric" : (dateColumns.includes(col) ? "Date" : "Text")
    }));
  };

  const renderChart = () => {
    if (!chartData) {
      return <p className="empty-text">Generate a chart to view visualization.</p>;
    }

    const chartTitle = chartType === "Pie"
      ? `${yAxis || xAxis} Distribution`
      : chartType === "Histogram"
      ? `Histogram of ${xAxis}`
      : `${yAxis || xAxis} by ${xAxis}`;

    const pieOptions = {
      ...getChartOptions(chartTitle, true),
      plugins: {
        ...getChartOptions(chartTitle, true).plugins,
        tooltip: {
          enabled: true,
          backgroundColor: "#111827",
          titleColor: "#F8FAFC",
          bodyColor: "#F8FAFC",
          borderColor: "#475569",
          borderWidth: 1,
          cornerRadius: 10,
          padding: 12,
          callbacks: {
            label: function (context) {
              const value = context.raw;
              const data = context.chart.data.datasets[0].data;
              const total = data.reduce((a, b) => a + b, 0);
              const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
              return `${context.label}: ${value} (${percentage}%)`;
            }
          }
        }
      }
    };

    if (chartType === "Bar") return <Bar data={chartData} options={getChartOptions(chartTitle)} />;
    if (chartType === "Line") return <Line data={chartData} options={getChartOptions(chartTitle)} />;
    if (chartType === "Pie") return <Pie data={chartData} options={pieOptions} />;
    if (chartType === "Scatter") {
      const scatterData = {
        datasets: [
          {
            label: `${xAxis} vs ${yAxis}`,
            data: chartData.labels.map((label, index) => ({
              x: Number(label),
              y: chartData.datasets[0].data[index]
            })),
            backgroundColor: CHART_THEME.secondary,
            borderColor: CHART_THEME.primary,
            borderWidth: 2,
            pointRadius: 6,
            pointHoverRadius: 8,
            pointHoverBorderColor: "#ffffff"
          }
        ]
      };
      return <Scatter data={scatterData} options={getChartOptions(chartTitle)} />;
    }
    if (chartType === "Histogram") return <Bar data={chartData} options={getChartOptions(chartTitle)} />;

    return null;
  };

  const qualityScore = qualityReport?.quality_score;
  const qualityScoreValue = qualityScore?.score ?? qualityReport?.health_score;
  const qualityGrade = qualityScore?.grade ?? qualityReport?.score_rating;
  const qualityInsights = qualityReport?.quality_insights ?? qualityReport?.insights ?? [];
  const missingColumns = qualityReport?.missing_analysis?.columns_with_missing ?? [];
  const outlierColumns = qualityReport?.outlier_analysis?.columns ?? qualityReport?.iqr_outliers ?? [];
  const columnProfiles = qualityReport?.column_profiles ?? [];

  // Authentication Screen
  if (authChecking) {
    return (
      <div className="login-container">
        <div className="login-card" style={{ textAlign: "center", padding: "50px 30px" }}>
          <h1 style={{ marginBottom: "12px" }}>📊 CSV Dashboard</h1>
          <p style={{ color: "#94a3b8" }}>Verifying session status...</p>
        </div>
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <h1>📊 CSV Dashboard</h1>
            <h2>{authMode === "register" ? "Create an Account" : "Login to Dashboard"}</h2>
            <p>
              {authMode === "register"
                ? "Register a secure account to persist and analyze your datasets"
                : "Sign in to access your saved datasets and analytics"}
            </p>
          </div>

          <div className="auth-tab-switch" style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
            <button
              type="button"
              className={`auth-toggle-btn ${authMode === "login" ? "active" : ""}`}
              onClick={() => {
                setAuthMode("login");
                setAuthError("");
                setEmailError("");
                setPasswordError("");
                setConfirmPasswordError("");
              }}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "8px",
                border: "none",
                fontWeight: "600",
                cursor: "pointer",
                background: authMode === "login" ? "#4F46E5" : "#334155",
                color: "#ffffff"
              }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`auth-toggle-btn ${authMode === "register" ? "active" : ""}`}
              onClick={() => {
                setAuthMode("register");
                setAuthError("");
                setEmailError("");
                setPasswordError("");
                setConfirmPasswordError("");
              }}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "8px",
                border: "none",
                fontWeight: "600",
                cursor: "pointer",
                background: authMode === "register" ? "#4F46E5" : "#334155",
                color: "#ffffff"
              }}
            >
              Register
            </button>
          </div>

          {authError && (
            <div
              className="auth-error-banner"
              style={{
                background: "rgba(239, 68, 68, 0.15)",
                border: "1px solid #ef4444",
                color: "#fca5a5",
                padding: "12px 16px",
                borderRadius: "8px",
                marginBottom: "18px",
                fontSize: "14px",
                lineHeight: "1.4"
              }}
            >
              {authError}
            </div>
          )}

          <form onSubmit={handleAuthSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="email">Email Address</label>
              <input
                id="email"
                type="email"
                placeholder="name@example.com"
                value={loginEmail}
                onChange={(e) => {
                  setLoginEmail(e.target.value);
                  setEmailError("");
                  setAuthError("");
                }}
                className={emailError ? "input-error" : ""}
              />
              {emailError && <span className="field-error">{emailError}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                value={loginPassword}
                onChange={(e) => {
                  setLoginPassword(e.target.value);
                  setPasswordError("");
                  setAuthError("");
                }}
                className={passwordError ? "input-error" : ""}
              />
              {passwordError && <span className="field-error">{passwordError}</span>}
            </div>

            {authMode === "register" && (
              <div className="form-group">
                <label htmlFor="confirmPassword">Confirm Password</label>
                <input
                  id="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    setConfirmPasswordError("");
                    setAuthError("");
                  }}
                  className={confirmPasswordError ? "input-error" : ""}
                />
                {confirmPasswordError && (
                  <span className="field-error">{confirmPasswordError}</span>
                )}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              data-testid="auth-submit-btn"
              disabled={authLoading}
            >
              {authLoading
                ? "Processing..."
                : authMode === "register"
                ? "Create Account"
                : "Sign In"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: "18px" }}>
            {authMode === "login" ? (
              <p style={{ color: "#94a3b8", fontSize: "14px" }}>
                Don't have an account?{" "}
                <button
                  type="button"
                  onClick={() => {
                    setAuthMode("register");
                    setAuthError("");
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#38bdf8",
                    fontWeight: "600",
                    cursor: "pointer",
                    textDecoration: "underline"
                  }}
                >
                  Create one here
                </button>
              </p>
            ) : (
              <p style={{ color: "#94a3b8", fontSize: "14px" }}>
                Already registered?{" "}
                <button
                  type="button"
                  onClick={() => {
                    setAuthMode("login");
                    setAuthError("");
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#38bdf8",
                    fontWeight: "600",
                    cursor: "pointer",
                    textDecoration: "underline"
                  }}
                >
                  Sign in to your account
                </button>
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Authenticated Dashboard
  return (
    <div className="app-container">
      <div className="dashboard-shell">
        <aside className={`sidebar ${isSidebarOpen ? "open" : ""}`}>
          <div className="sidebar-header">
            <div className="brand">
              <div className="brand-mark">
                <BarChart3 size={20} />
              </div>
              <div className="brand-copy">
                <span className="brand-name">AI Data Analyzer</span>
                <span className="brand-subtitle">Analytics Suite</span>
              </div>
            </div>
            <button
              type="button"
              className="sidebar-close-btn"
              onClick={() => setIsSidebarOpen(false)}
              aria-label="Close sidebar"
            >
              <Menu size={18} />
            </button>
          </div>

          <div className="sidebar-nav">
            {sidebarSections.map((section) => (
              <div key={section.title} className="nav-section">
                <div className="nav-section-title">{section.title}</div>
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.key;
                  return (
                    <button
                      key={`${section.title}-${item.label}`}
                      type="button"
                      className={`nav-item ${isActive ? "active" : ""}`}
                      onClick={() => handleTabChange(item.key)}
                      aria-current={isActive ? "page" : undefined}
                      aria-label={{
                        ai: "✨ AI Analyst",
                        rootcause: "🔎 Root Cause Analysis",
                        forecast: "🔮 Forecast · Predictive Analytics",
                        reports: "📄 Reports · Business Reports",
                        datasets: "🗂 Datasets · Dataset Management",
                      }[item.key] || item.label}
                    >
                      <span className="nav-icon">
                        <Icon size={18} />
                      </span>
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>

          <div className="sidebar-footer">
            <div className="user-pill">
              <div className="user-avatar">{loggedInEmail?.charAt(0)?.toUpperCase() || "U"}</div>
              <div className="user-meta">
                <span className="user-label">Signed in</span>
                <span className="user-role">Workspace</span>
              </div>
            </div>
            <button type="button" className="sidebar-logout-btn" onClick={handleLogout}>
              <LogOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        </aside>

        {isSidebarOpen && <button type="button" className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)} aria-label="Close sidebar overlay" />}

        <main className="main">
          <header className="main-header">
            <div className="main-header-left">
              <button
                type="button"
                className="mobile-menu-toggle"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                aria-label="Toggle sidebar"
              >
                <Menu size={18} />
              </button>
              <div>
                <p className="eyebrow">Workspace</p>
                <h1 className="header-title">CSV Analytics Dashboard</h1>
              </div>
            </div>
            <div className="header-user-section">
              <span className="user-email">{loggedInEmail}</span>
            </div>
          </header>
          <p className="subtitle">
            Upload, clean, profile data quality, discover business KPIs, and analyze time trends.
          </p>

          {error && <div className="error">{error}</div>}

          {activeTab === "charts" && summary && (
            <div className="cards" data-testid="overview-kpis">
              <div className="card">
                <h3>Total Rows</h3>
                <p>{summary.total_rows}</p>
              </div>
              <div className="card">
                <h3>Total Columns</h3>
                <p>{summary.total_columns}</p>
              </div>
              <div className="card">
                <h3>Duplicates Removed</h3>
                <p>{summary.duplicate_rows_removed}</p>
              </div>
              <div className="card">
                <h3>Missing Values Handled</h3>
                <p>{summary.missing_values_handled}</p>
              </div>
            </div>
          )}

          {activeTab === "upload" && (
            <section className="content-card upload-workspace">
              <div className="section-heading">
                <span className="section-kicker">Data management</span>
                <h2>Upload a dataset</h2>
                <p>Import a CSV or Excel workbook. Your existing cleaning and dataset persistence workflow remains unchanged.</p>
              </div>
              <div className="upload-dropzone">
                <span className="upload-icon"><UploadCloud size={26} /></span>
                <div>
                  <label htmlFor="dataset-upload-file">Choose a CSV or Excel file</label>
                  <input
                    id="dataset-upload-file"
                    type="file"
                    accept=".csv,.xlsx"
                    onChange={(event) => setFile(event.target.files[0])}
                  />
                  <span className="metric-caption">{file?.name || "CSV and .xlsx files are supported"}</span>
                </div>
                <button type="button" onClick={uploadFile} disabled={loading}>
                  {loading ? "Uploading..." : "Upload & Clean"}
                </button>
              </div>
              {datasetId && (
                <div className="active-dataset-note" role="status">
                  <Database size={17} />
                  <span>An active dataset is selected. Uploading another file switches the workspace to the new dataset.</span>
                </div>
              )}
            </section>
          )}

          {activeTab === "charts" && (
            <section className="content-card chart-config-card">
              <div className="section-header compact-header">
                <div>
                  <p className="eyebrow">Workspace controls</p>
                  <h2>Dataset & Chart Configuration</h2>
                </div>
              </div>

              <div className="chart-controls-grid">
                <div className="field-group">
                  <label htmlFor="file-upload">Upload CSV / Excel</label>
                  <input
                    id="file-upload"
                    type="file"
                    accept=".csv,.xlsx"
                    onChange={(e) => setFile(e.target.files[0])}
                  />
                  <button type="button" onClick={uploadFile}>
                    {loading ? "Uploading..." : "Upload & Clean"}
                  </button>
                </div>

                {datasetId && (
                  <>
                    <div className="field-group">
                      <label>Chart Type</label>
                      <select value={chartType} onChange={(e) => setChartType(e.target.value)}>
                        <option>Bar</option>
                        <option>Line</option>
                        <option>Pie</option>
                        <option>Scatter</option>
                        <option>Histogram</option>
                      </select>
                    </div>

                    <div className="field-group">
                      <label>X-axis</label>
                      <select value={xAxis} onChange={(e) => setXAxis(e.target.value)}>
                        {columns.map((col) => (
                          <option key={col}>{col}</option>
                        ))}
                      </select>
                    </div>

                    {chartType !== "Histogram" && (
                      <div className="field-group">
                        <label>Y-axis</label>
                        <select value={yAxis} onChange={(e) => setYAxis(e.target.value)}>
                          {(numericColumns.length ? numericColumns : columns).map((col) => (
                            <option key={col}>{col}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="field-group field-group-actions">
                      <button type="button" onClick={generateChart}>Generate Chart</button>
                      <button type="button" className="secondary-btn" onClick={downloadCleanedData}>
                        Download Cleaned CSV
                      </button>
                    </div>
                  </>
                )}
              </div>
            </section>
          )}

          {/* TAB 1: OVERVIEW & CHARTS */}
          {activeTab === "charts" && (
            <>
              {summary && (
                <section className="section">
                  <h2>📋 Column Types Summary</h2>
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Column Name</th>
                          <th>Data Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {getColumnDataTypes().map((col) => (
                          <tr key={col.name}>
                            <td>{col.name}</td>
                            <td>
                              <span className={`data-type ${col.type.toLowerCase()}`}>
                                {col.type}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="quality-stats">
                    <p>✅ Duplicate rows removed: <strong>{summary.duplicate_rows_removed}</strong></p>
                    <p>✅ Missing values handled: <strong>{summary.missing_values_handled}</strong></p>
                  </div>
                </section>
              )}

              {preview.length > 0 && (
                <section className="section">
                  <div className="section-header">
                    <h2>🧹 Cleaned Data Preview</h2>
                    <input
                      type="text"
                      className="search-box"
                      placeholder="🔍 Search in data..."
                      value={searchFilter}
                      onChange={handleSearch}
                    />
                  </div>
                  {filteredPreview.length === 0 ? (
                    <p className="empty-text">No data matching your search.</p>
                  ) : (
                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            {columns.map((col) => (
                              <th key={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {filteredPreview.map((row, index) => (
                            <tr key={index}>
                              {columns.map((col) => (
                                <td key={col}>{String(row[col])}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}

              {datasetId && (
                <>
                  <section className="section chart-section">
                    <div className="chart-header">
                      <h2>📈 Chart Output</h2>
                      <button className="export-btn" onClick={downloadChart}>
                        📥 Download Chart (PNG)
                      </button>
                    </div>
                    <div className="chart-box" ref={chartBoxRef} style={chartWrapperStyle}>
                      {renderChart()}
                    </div>
                  </section>

                  <section className="section">
                    <h2>💡 Statistical Insights</h2>
                    <button onClick={generateInsights}>Generate Statistical Insights</button>

                    <div className="insights">
                      {insights.map((item, index) => (
                        <div className="insight-card" key={index}>
                          {item}
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="section">
                    <h2>💬 Ask Your Data</h2>
                    <div className="ask-box">
                      <input
                        type="text"
                        placeholder="Ask a question (e.g., 'total sales', 'how many rows', 'max value')..."
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                      />
                      <button onClick={askData}>Get Answer</button>
                    </div>

                    {answer && <div className="answer">{answer}</div>}

                    {askTable.length > 0 && (
                      <div className="table-wrapper">
                        <table>
                          <thead>
                            <tr>
                              {Object.keys(askTable[0]).map((key) => (
                                <th key={key}>{key}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {askTable.map((row, index) => (
                              <tr key={index}>
                                {Object.keys(row).map((key) => (
                                  <td key={key}>{String(row[key])}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                </>
              )}
            </>
          )}

          {/* TAB 2: DATA QUALITY & PROFILE */}
          {activeTab === "quality" && (
            <>
              {qualityLoading && <p className="empty-text">⏳ Analyzing data quality and profiling columns...</p>}

              {qualityReport && (
                <>
                  {/* Quality Score Hero Banner */}
                  <div className="quality-hero-card">
                    <div className="quality-score-left">
                      <div className="quality-score-circle">
                        <span className="quality-score-num">{qualityScoreValue ?? "—"}</span>
                        <span className="quality-score-max">/ 100</span>
                      </div>
                      <div className="quality-title-group">
                        <h3>Data Quality Health Score</h3>
                        <p>{qualityScore?.limitations || "Score provided by the data-quality service."}</p>
                        <span className={`quality-grade-badge grade-${String(qualityGrade || "unrated").toLowerCase().replace(" ", "-")}`}>
                          Grade: {qualityGrade || "Not provided"}
                        </span>
                      </div>
                    </div>

                    <div className="quality-penalties-box">
                      <div className="penalty-item">
                        <span>Missing Cells Penalty:</span>
                        <span className="penalty-val">{qualityScore?.penalties?.missing_penalty != null ? `-${qualityScore.penalties.missing_penalty} pts` : "Not provided"}</span>
                      </div>
                      <div className="penalty-item">
                        <span>Duplicate Rows Penalty:</span>
                        <span className="penalty-val">{qualityScore?.penalties?.duplicate_penalty != null ? `-${qualityScore.penalties.duplicate_penalty} pts` : "Not provided"}</span>
                      </div>
                      <div className="penalty-item">
                        <span>IQR Outliers Penalty:</span>
                        <span className="penalty-val">{qualityScore?.penalties?.outlier_penalty != null ? `-${qualityScore.penalties.outlier_penalty} pts` : "Not provided"}</span>
                      </div>
                    </div>
                  </div>

                  {/* Structural Overview */}
                  <section className="section">
                    <h2>📊 Structural Health Overview</h2>
                    <div className="cards">
                      <div className="card">
                        <h3>Total Rows</h3>
                        <p>{qualityReport.overview.total_rows}</p>
                      </div>
                      <div className="card">
                        <h3>Total Columns</h3>
                        <p>{qualityReport.overview.total_columns}</p>
                      </div>
                      <div className="card">
                        <h3>Missing Cells</h3>
                        <p>{qualityReport.overview.total_missing_cells ?? "—"} ({qualityReport.overview.missing_cell_percentage ?? "—"}%)</p>
                      </div>
                      <div className="card">
                        <h3>Duplicate Rows</h3>
                        <p>{qualityReport.overview.duplicate_rows_count ?? qualityReport.duplicate_analysis?.duplicate_rows_count ?? "—"} ({qualityReport.overview.duplicate_rows_percentage ?? "—"}%)</p>
                      </div>
                    </div>
                  </section>

                  {/* Quality Insights */}
                  {qualityInsights.length > 0 && (
                    <section className="section">
                      <h2>🔍 Quality & Anomaly Observations</h2>
                      <div>
                        {qualityInsights.map((qi, idx) => (
                          <div className={`insight-card-rich ${qi.severity}`} key={idx}>
                            <div>
                              <h4>{qi.title}</h4>
                              <p>{qi.explanation}</p>
                              <span className="insight-action">👉 Recommended Action: {qi.recommended_action}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Missing Value Analysis Table */}
                  <section className="section">
                    <h2>⚠️ Missing-Value Analysis & Strategies</h2>
                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            <th>Column Name</th>
                            <th>Data Type</th>
                            <th>Missing Count</th>
                            <th>Missing %</th>
                            <th>Recommended Strategy</th>
                            <th>Technical Rationale</th>
                          </tr>
                        </thead>
                        <tbody>
                          {missingColumns.map((col) => (
                            <tr key={col.column}>
                              <td><strong>{col.column}</strong></td>
                              <td><span className="badge-pill badge-numeric">{col.data_type}</span></td>
                              <td>{col.missing_count}</td>
                              <td>{col.missing_percentage}%</td>
                              <td><strong>{col.recommendation_strategy}</strong></td>
                              <td><small>{col.explanation}</small></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>

                  {/* IQR Outlier Detection Table */}
                  <section className="section">
                    <h2>🎯 Potential Outlier Detection (IQR Method)</h2>
                    <p className="subtitle" style={{ marginTop: 0 }}>
                      Bounds computed via <code>Q1 - 1.5×IQR</code> to <code>Q3 + 1.5×IQR</code>. Outliers reflect extreme statistical variance and should be audited.
                    </p>
                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            <th>Numeric Column</th>
                            <th>Status</th>
                            <th>Q1 (25%)</th>
                            <th>Q3 (75%)</th>
                            <th>IQR</th>
                            <th>Lower Bound</th>
                            <th>Upper Bound</th>
                            <th>Outliers Flagged</th>
                            <th>Sample Outliers</th>
                          </tr>
                        </thead>
                        <tbody>
                          {outlierColumns.map((col) => (
                            <tr key={col.column}>
                              <td><strong>{col.column}</strong></td>
                              <td>
                                <span className={`badge-pill ${col.status === 'has_outliers' ? 'badge-categorical' : 'badge-numeric'}`}>
                                  {col.status}
                                </span>
                              </td>
                              <td>{col.q1 ?? "N/A"}</td>
                              <td>{col.q3 ?? "N/A"}</td>
                              <td>{col.iqr ?? "N/A"}</td>
                              <td>{col.lower_bound ?? "N/A"}</td>
                              <td>{col.upper_bound ?? "N/A"}</td>
                              <td><strong>{col.outlier_count}</strong> ({col.outlier_percentage}%)</td>
                              <td>{col.examples?.length ? col.examples.join(", ") : "None"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>

                  {/* Column-Level Statistical Profiling */}
                  <section className="section">
                    <h2>🔬 Comprehensive Column Profiling</h2>
                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            <th>Column</th>
                            <th>Type</th>
                            <th>Non-Null</th>
                            <th>Missing %</th>
                            <th>Uniques</th>
                            <th>Min / Top</th>
                            <th>Max / Count</th>
                            <th>Mean / Freq</th>
                            <th>Median / Q1</th>
                            <th>Q3 / Std</th>
                            <th>Sample Values</th>
                          </tr>
                        </thead>
                        <tbody>
                          {columnProfiles.map((p) => (
                            <tr key={p.column}>
                              <td><strong>{p.column}</strong></td>
                              <td>
                                <span className={`badge-pill badge-${p.detected_type}`}>
                                  {p.detected_type}
                                </span>
                              </td>
                              <td>{p.non_null_count}</td>
                              <td>{p.missing_percentage}%</td>
                              <td>{p.unique_count}</td>
                              <td>{p.min !== undefined ? p.min : (p.most_frequent_value ?? "—")}</td>
                              <td>{p.max !== undefined ? p.max : (p.most_frequent_count ?? "—")}</td>
                              <td>{p.mean !== undefined ? p.mean : "—"}</td>
                              <td>{p.median !== undefined ? `${p.median} (Q1: ${p.q1})` : "—"}</td>
                              <td>{p.std !== undefined ? `${p.q3} (σ: ${p.std})` : "—"}</td>
                              <td><small>{(p.example_values || []).join(", ")}</small></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
            </>
          )}

          {/* TAB 3: BUSINESS INTELLIGENCE */}
          {activeTab === "bi" && (
            <>
              {biLoading && <p className="empty-text">⏳ Discovering business measures and computing KPIs...</p>}

              {/* KPI Cards Grid */}
              {biKpis.length > 0 && (
                <section className="section">
                  <h2>💼 Discovered Business KPIs</h2>
                  <div className="kpi-grid">
                    {biKpis.map((kpi, idx) => (
                      <div className="kpi-card-rich" key={idx}>
                        <div>
                          <div className="kpi-header">
                            <span className="kpi-title">{kpi.metric_name}</span>
                            <span className="kpi-unit-pill">{kpi.units}</span>
                          </div>
                          <div className="kpi-metric-val">{kpi.formatted_value}</div>
                        </div>
                        <p className="kpi-explanation">{kpi.calculation_explanation}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Deterministic Business Insights */}
              {biInsights.length > 0 && (
                <section className="section">
                  <h2>💡 Deterministic Business Observations</h2>
                  <div>
                    {biInsights.map((bi, idx) => (
                      <div className={`insight-card-rich ${bi.severity}`} key={idx}>
                        <div>
                          <h4>{bi.title}</h4>
                          <p>{bi.explanation}</p>
                          <span className="insight-action">👉 Recommended Action: {bi.recommended_action}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Interactive Group-Wise Analysis */}
              <section className="section">
                <h2>📊 Group-Wise Performance Comparison</h2>
                <div className="controls-row-bi">
                  <div className="control-item-bi">
                    <label>Grouping Column (Category)</label>
                    <select value={groupCol} onChange={(e) => setGroupCol(e.target.value)}>
                      {columns.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="control-item-bi">
                    <label>Measure Column (Numeric)</label>
                    <select value={groupMeasureCol} onChange={(e) => setGroupMeasureCol(e.target.value)}>
                      {(numericColumns.length ? numericColumns : columns).map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="control-item-bi">
                    <label>Aggregation</label>
                    <select value={groupAgg} onChange={(e) => setGroupAgg(e.target.value)}>
                      <option value="sum">Sum</option>
                      <option value="mean">Mean (Average)</option>
                      <option value="median">Median</option>
                      <option value="count">Observation Count</option>
                      <option value="min">Minimum</option>
                      <option value="max">Maximum</option>
                    </select>
                  </div>

                  <button className="btn-run-bi" onClick={runGroupAnalysis} disabled={groupLoading}>
                    {groupLoading ? "Analyzing..." : "Compare Groups"}
                  </button>
                </div>

                {groupResult && (
                  <>
                    <div className="cards" style={{ marginBottom: "20px" }}>
                      <div className="card">
                        <h3>Total Groups</h3>
                        <p>{groupResult.total_groups}</p>
                      </div>
                      <div className="card">
                        <h3>Highest Performing</h3>
                        <p>{groupResult.highest_performing?.group} ({groupResult.highest_performing?.value?.toLocaleString()})</p>
                      </div>
                      <div className="card">
                        <h3>Lowest Performing</h3>
                        <p>{groupResult.lowest_performing?.group} ({groupResult.lowest_performing?.value?.toLocaleString()})</p>
                      </div>
                      <div className="card">
                        <h3>Negative Groups</h3>
                        <p>{groupResult.negative_groups?.length || 0}</p>
                      </div>
                    </div>

                    {groupChartData && (
                      <div className="chart-box" style={{ ...chartWrapperStyle, marginBottom: "24px" }}>
                        <Bar
                          data={groupChartData}
                          options={getChartOptions(`Group Breakdown: ${groupAgg.toUpperCase()} of ${groupMeasureCol} by ${groupCol}`)}
                        />
                      </div>
                    )}

                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            <th>Group ({groupCol})</th>
                            <th>{groupAgg.toUpperCase()} of {groupMeasureCol}</th>
                            <th>Contribution %</th>
                          </tr>
                        </thead>
                        <tbody>
                          {groupResult.records.map((r, i) => (
                            <tr key={i}>
                              <td><strong>{r.group}</strong></td>
                              <td>{r.value.toLocaleString()}</td>
                              <td>{r.percentage_of_total !== null ? `${r.percentage_of_total}%` : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </section>
            </>
          )}

          {/* TAB 4: TRENDS & PERIOD COMPARISONS */}
          {activeTab === "trends" && (
            <>
              <section className="section">
                <h2>📈 Time-Based Trend & Period Analysis</h2>
                <div className="controls-row-bi">
                  <div className="control-item-bi">
                    <label>Date Column</label>
                    <select value={trendDateCol} onChange={(e) => setTrendDateCol(e.target.value)}>
                      {(dateColumns.length ? dateColumns : columns).map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="control-item-bi">
                    <label>Measure Column (Numeric)</label>
                    <select value={trendMeasureCol} onChange={(e) => setTrendMeasureCol(e.target.value)}>
                      {(numericColumns.length ? numericColumns : columns).map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div className="control-item-bi">
                    <label>Granularity</label>
                    <select value={trendGranularity} onChange={(e) => setTrendGranularity(e.target.value)}>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  </div>

                  <div className="control-item-bi">
                    <label>Aggregation</label>
                    <select value={trendAgg} onChange={(e) => setTrendAgg(e.target.value)}>
                      <option value="sum">Sum</option>
                      <option value="mean">Mean (Average)</option>
                      <option value="count">Count</option>
                      <option value="min">Minimum</option>
                      <option value="max">Maximum</option>
                    </select>
                  </div>

                  <button className="btn-run-bi" onClick={runTrendAnalysis} disabled={trendLoading}>
                    {trendLoading ? "Analyzing..." : "Generate Trends"}
                  </button>
                </div>

                {popResult && popResult.is_valid_comparison && (
                  <div className="pop-card">
                    <div className="pop-text-info">
                      <h4>Period-over-Period Performance ({popResult.granularity.toUpperCase()})</h4>
                      <p>{popResult.explanation}</p>
                    </div>
                    <div>
                      <span className={`pop-change-chip pop-${popResult.direction}`}>
                        {popResult.direction === "increase" ? "▲ +" : (popResult.direction === "decrease" ? "▼ " : "● ")}
                        {popResult.percentage_change !== null ? `${popResult.percentage_change}%` : `${popResult.absolute_change}`}
                      </span>
                    </div>
                  </div>
                )}

                {trendResult && trendChartData && (
                  <>
                    <div className="chart-box" style={{ ...chartWrapperStyle, marginBottom: "24px" }}>
                      <Line
                        data={trendChartData}
                        options={getChartOptions(`Time Trend (${trendGranularity.toUpperCase()} ${trendAgg.toUpperCase()}): ${trendMeasureCol} by ${trendDateCol}`)}
                      />
                    </div>

                    <div className="table-wrapper">
                      <table>
                        <thead>
                          <tr>
                            <th>Period ({trendGranularity})</th>
                            <th>{trendAgg.toUpperCase()} of {trendMeasureCol}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trendResult.data_points.map((pt, i) => (
                            <tr key={i}>
                              <td><strong>{pt.period}</strong></td>
                              <td>{pt.value.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </section>
            </>
          )}

          {activeTab === "settings" && (
            <section className="section settings-workspace">
              <div className="section-heading">
                <span className="section-kicker">Preferences</span>
                <h2>Workspace settings</h2>
                <p>Account and dataset status for this authenticated workspace.</p>
              </div>
              <div className="settings-grid">
                <article className="settings-item">
                  <span className="metric-icon"><UserRound size={18} /></span>
                  <div>
                    <span className="settings-label">Signed-in account</span>
                    <strong>{loggedInEmail}</strong>
                  </div>
                </article>
                <article className="settings-item">
                  <span className="metric-icon"><Database size={18} /></span>
                  <div>
                    <span className="settings-label">Active dataset</span>
                    <strong>{datasetId ? `${summary?.total_rows ?? "—"} rows · ${summary?.total_columns ?? "—"} columns` : "No dataset selected"}</strong>
                  </div>
                </article>
              </div>
              <button type="button" className="settings-logout-btn" onClick={handleLogout}>
                <LogOut size={16} /> Sign out of this workspace
              </button>
            </section>
          )}

          {["ai", "rootcause", "forecast", "reports", "datasets"].includes(activeTab) && (
            <AdvancedAnalytics
              key={activeTab}
              activeTab={activeTab}
              apiUrl={API_URL}
              datasetId={datasetId}
              columns={columns}
              numericColumns={numericColumns}
              dateColumns={dateColumns}
              onDatasetDeleted={handleSavedDatasetDeleted}
              onSelectDataset={openSavedDataset}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;