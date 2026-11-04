import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import axios from "axios";
import App from "../App";
import AdvancedAnalytics from "../AdvancedAnalytics";

// Mock Chart.js elements and react-chartjs-2 components for jsdom
vi.mock("react-chartjs-2", () => ({
  Bar: () => <div data-testid="mock-bar-chart">Bar Chart</div>,
  Line: () => <div data-testid="mock-line-chart">Line Chart</div>,
  Pie: () => <div data-testid="mock-pie-chart">Pie Chart</div>,
  Scatter: () => <div data-testid="mock-scatter-chart">Scatter Chart</div>,
}));

vi.mock("html2canvas", () => ({
  default: vi.fn().mockResolvedValue({
    toDataURL: () => "data:image/png;base64,mock",
  }),
}));

describe("AI Data Analyzer Frontend – Phase 3 Test Suite", () => {
  let originalAxiosAdapter;

  beforeEach(() => {
    originalAxiosAdapter = axios.defaults.adapter;
    vi.clearAllMocks();
  });

  afterEach(() => {
    axios.defaults.adapter = originalAxiosAdapter;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe("Authentication & Session Initialization", () => {
    it("renders unauthenticated login screen when session check fails (401)", async () => {
      vi.spyOn(axios, "get").mockRejectedValueOnce({
        response: { status: 401, data: { error: { code: "UNAUTHORIZED", message: "Not authenticated" } } },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Login to Dashboard/i })).toBeInTheDocument();
      });

      expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^Password/i)).toBeInTheDocument();
      expect(screen.getByTestId("auth-submit-btn")).toBeInTheDocument();
    });

    it("automatically restores authenticated session if /api/auth/me succeeds", async () => {
      vi.spyOn(axios, "get").mockResolvedValueOnce({
        data: { user: { id: "u-123", email: "active_user@example.com" } },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByText("active_user@example.com")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Logout/i })).toBeInTheDocument();
      });

      expect(screen.getByText(/Upload CSV \/ Excel/i)).toBeInTheDocument();
    });
  });

  describe("Business Report Downloads", () => {
    it("uses the generated report ID instead of the click event when downloading", async () => {
      const reportId = "report-123";
      const getSpy = vi.spyOn(axios, "get").mockImplementation((url) => {
        if (url.endsWith("/api/reports")) {
          return Promise.resolve({ data: { reports: [] } });
        }
        return Promise.resolve({ data: new Blob(["%PDF-1.4 test"]) });
      });
      vi.spyOn(axios, "post").mockResolvedValue({
        data: {
          report_id: reportId,
          dataset_id: "dataset-1",
          dataset_name: "audit.csv",
          created_at: "2025-01-01T00:00:00Z",
        },
      });
      const createObjectURL = vi.fn(() => "blob:business-report");
      const revokeObjectURL = vi.fn();
      vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
      const anchorClick = vi
        .spyOn(HTMLAnchorElement.prototype, "click")
        .mockImplementation(() => {});

      render(
        <AdvancedAnalytics
          activeTab="reports"
          apiUrl="http://api.test"
          datasetId="dataset-1"
          columns={["Date", "Sales"]}
          numericColumns={["Sales"]}
          dateColumns={["Date"]}
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /Generate PDF report/i }));
      await screen.findByText(/is ready for download/i);
      fireEvent.click(screen.getAllByRole("button", { name: /^Download PDF$/i })[0]);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledWith(
          `http://api.test/api/reports/${reportId}/download`,
          { responseType: "blob" }
        );
      });
      expect(createObjectURL).toHaveBeenCalled();
      expect(anchorClick).toHaveBeenCalled();
      await new Promise((resolve) => window.setTimeout(resolve, 1100));
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:business-report");
    });
  });

  describe("Form Validation", () => {
    beforeEach(() => {
      vi.spyOn(axios, "get").mockRejectedValue({
        response: { status: 401 },
      });
    });

    it("validates invalid email format and empty password on login submit", async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      });

      const submitBtn = screen.getByTestId("auth-submit-btn");
      const emailInput = screen.getByLabelText(/Email Address/i);

      // Submit with empty email
      fireEvent.click(submitBtn);
      expect(await screen.findByText(/Please enter a valid email address/i)).toBeInTheDocument();

      // Submit with valid email but empty password
      fireEvent.change(emailInput, { target: { value: "valid@example.com" } });
      fireEvent.click(submitBtn);
      expect(await screen.findByText(/Password cannot be empty/i)).toBeInTheDocument();
    });

    it("switches to registration mode and enforces password match and minimum length", async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /^Register$/i })).toBeInTheDocument();
      });

      // Switch to Register tab
      fireEvent.click(screen.getByRole("button", { name: /^Register$/i }));

      expect(screen.getByRole("heading", { name: /Create an Account/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/Confirm Password/i)).toBeInTheDocument();

      const emailInput = screen.getByLabelText(/Email Address/i);
      const passwordInput = screen.getByLabelText(/^Password/i);
      const confirmInput = screen.getByLabelText(/Confirm Password/i);
      const submitBtn = screen.getByTestId("auth-submit-btn");

      // Password < 6 chars
      fireEvent.change(emailInput, { target: { value: "newuser@example.com" } });
      fireEvent.change(passwordInput, { target: { value: "123" } });
      fireEvent.click(submitBtn);

      expect(await screen.findByText(/Password must be at least 6 characters/i)).toBeInTheDocument();

      // Mismatched passwords
      fireEvent.change(passwordInput, { target: { value: "Password123!" } });
      fireEvent.change(confirmInput, { target: { value: "DifferentPassword!" } });
      fireEvent.click(submitBtn);

      expect(await screen.findByText(/Passwords do not match/i)).toBeInTheDocument();
    });
  });

  describe("Authentication Flow & Error Display", () => {
    beforeEach(() => {
      vi.spyOn(axios, "get").mockRejectedValue({
        response: { status: 401 },
      });
    });

    it("displays error banner when login fails with invalid credentials", async () => {
      vi.spyOn(axios, "post").mockRejectedValueOnce({
        response: {
          data: { error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password." } },
        },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      });

      fireEvent.change(screen.getByLabelText(/Email Address/i), { target: { value: "user@example.com" } });
      fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: "WrongPass123!" } });
      fireEvent.click(screen.getByTestId("auth-submit-btn"));

      expect(await screen.findByText(/Invalid email or password/i)).toBeInTheDocument();
    });

    it("logs in successfully and displays dashboard with user email", async () => {
      vi.spyOn(axios, "post").mockResolvedValueOnce({
        data: { user: { id: "user-1", email: "successful_user@example.com" } },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      });

      fireEvent.change(screen.getByLabelText(/Email Address/i), { target: { value: "successful_user@example.com" } });
      fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: "Password123!" } });
      fireEvent.click(screen.getByTestId("auth-submit-btn"));

      await waitFor(() => {
        expect(screen.getByText("successful_user@example.com")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Logout/i })).toBeInTheDocument();
      });
    });

    it("restores the authenticated session after refreshing following login", async () => {
      const authCheck = vi
        .spyOn(axios, "get")
        .mockRejectedValueOnce({ response: { status: 401 } })
        .mockResolvedValueOnce({
          data: { user: { id: "user-1", email: "refreshed_user@example.com" } },
        });
      vi.spyOn(axios, "post").mockResolvedValueOnce({
        data: { user: { id: "user-1", email: "refreshed_user@example.com" } },
      });

      expect(axios.defaults.withCredentials).toBe(true);

      const firstRender = render(<App />);
      await screen.findByLabelText(/Email Address/i);
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "refreshed_user@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^Password/i), {
        target: { value: "Password123!" },
      });
      fireEvent.click(screen.getByTestId("auth-submit-btn"));
      await screen.findByText("refreshed_user@example.com");

      firstRender.unmount();
      render(<App />);

      await screen.findByText("refreshed_user@example.com");
      expect(authCheck).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("button", { name: /Logout/i })).toBeInTheDocument();
    });

    it("logs out cleanly and redirects to login card", async () => {
      vi.spyOn(axios, "get").mockResolvedValueOnce({
        data: { user: { id: "user-1", email: "logout_test@example.com" } },
      });
      vi.spyOn(axios, "post").mockResolvedValueOnce({
        data: { message: "Logged out successfully" },
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Logout/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole("button", { name: /Logout/i }));

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Login to Dashboard/i })).toBeInTheDocument();
      });
    });

    it("clears the dashboard and returns to login after a later protected 401", async () => {
      vi.spyOn(axios, "get").mockResolvedValueOnce({
        data: {
          user: { id: "user-1", email: "expired_session@example.com" },
          csrf_token: "test-csrf-token",
        },
      });
      axios.defaults.adapter = (requestConfig) => {
        const error = new Error("Session expired");
        error.config = requestConfig;
        error.response = {
          status: 401,
          data: { error: { code: "UNAUTHORIZED", message: "Session expired" } },
          config: requestConfig,
          headers: {},
        };
        return Promise.reject(error);
      };

      render(<App />);
      await screen.findByText("expired_session@example.com");
      fireEvent.change(screen.getByLabelText(/Upload CSV \/ Excel/i), {
        target: { files: [new File(["a,b\n1,2"], "expired.csv", { type: "text/csv" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /Upload & Clean/i }));

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Login to Dashboard/i })).toBeInTheDocument();
        expect(screen.getByText(/Your session has expired/i)).toBeInTheDocument();
      });
    });
  });

  describe("Protected Dashboard Tabs and Dataset Operations", () => {
    beforeEach(() => {
      vi.spyOn(axios, "get").mockImplementation((url) => {
        if (url.includes("/api/auth/me")) {
          return Promise.resolve({ data: { user: { id: "user-1", email: "analytics_user@example.com" } } });
        }
        if (url.includes("/api/data-quality")) {
          return Promise.resolve({
            data: {
              health_score: 98,
              score_rating: "Excellent",
              overview: { total_rows: 10, total_columns: 2 },
              duplicate_analysis: { duplicate_rows_count: 0 },
              column_profiles: [],
              iqr_outliers: [],
              insights: [],
            },
          });
        }
        return Promise.reject(new Error("Not found"));
      });

      vi.spyOn(axios, "post").mockImplementation((url) => {
        if (url.includes("/upload")) {
          return Promise.resolve({
            data: {
              dataset_id: "test-ds-uuid",
              columns: ["Region", "Sales"],
              numeric_columns: ["Sales"],
              date_columns: [],
              summary: { total_rows: 10, total_columns: 2, duplicate_rows_removed: 0, missing_values_handled: 0 },
              preview: [{ Region: "North", Sales: 500 }],
            },
          });
        }
        if (url.includes("/chart-data")) {
          return Promise.resolve({
            data: {
              labels: ["North", "South"],
              values: [500, 300],
            },
          });
        }
        if (url.includes("/api/bi/trends")) {
          return Promise.resolve({
            data: {
              labels: ["2025-01"],
              values: [500],
              data_points: [{ period: "2025-01", value: 500 }],
            },
          });
        }
        if (url.includes("/api/bi/period-comparison")) {
          return Promise.resolve({ data: { is_valid_comparison: false } });
        }
        return Promise.resolve({ data: {} });
      });
    });

    it("uploads dataset and navigates across all four analytics tabs", async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText("analytics_user@example.com")).toBeInTheDocument();
      });

      // Upload file
      const fileInput = screen.getByLabelText(/Upload CSV \/ Excel/i);
      const testFile = new File(["Region,Sales\nNorth,500"], "test.csv", { type: "text/csv" });
      fireEvent.change(fileInput, { target: { files: [testFile] } });

      const uploadBtn = screen.getByRole("button", { name: /Upload & Clean/i });
      fireEvent.click(uploadBtn);

      // Verify tabs appear after successful upload
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Overview & Charts/i })).toBeInTheDocument();
      });

      const chartsTab = screen.getByRole("button", { name: /Overview & Charts/i });
      const qualityTab = screen.getByRole("button", { name: /Data Quality & Profile/i });
      const biTab = screen.getByRole("button", { name: /Business Intelligence/i });
      const trendsTab = screen.getByRole("button", { name: /Trends & Comparisons/i });

      // Navigate to Data Quality tab
      fireEvent.click(qualityTab);
      expect(qualityTab).toHaveClass("active");

      // Navigate to Business Intelligence tab
      fireEvent.click(biTab);
      expect(biTab).toHaveClass("active");

      // Navigate to Trends tab
      fireEvent.click(trendsTab);
      expect(trendsTab).toHaveClass("active");

      // Navigate back to Charts tab
      fireEvent.click(chartsTab);
      expect(chartsTab).toHaveClass("active");

      // Generate a chart
      const generateChartBtn = screen.getByRole("button", { name: /Generate Chart/i });
      fireEvent.click(generateChartBtn);

      await waitFor(() => {
        expect(screen.getByTestId("mock-bar-chart")).toBeInTheDocument();
      });
    });

    it("renders each sidebar module separately without leaking overview KPIs", async () => {
      render(<App />);
      await screen.findByText("analytics_user@example.com");

      fireEvent.change(screen.getByLabelText(/Upload CSV \/ Excel/i), {
        target: { files: [new File(["Region,Sales\nNorth,500"], "navigation.csv", { type: "text/csv" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /Upload & Clean/i }));

      const modules = [
        { label: /Overview & Charts/i, heading: /Cleaned Data Preview/i, hasOverviewKpis: true },
        { label: /Data Quality & Profile/i, heading: /Data Quality Health Score/i },
        { label: /Business Intelligence/i, heading: /Group-Wise Performance Comparison/i },
        { label: /Trends & Comparisons/i, heading: /Time-Based Trend & Period Analysis/i },
        { label: /✨ AI Analyst/i, heading: /AI Business Analyst/i },
        { label: /🔎 Root Cause Analysis/i, heading: /Root Cause Analysis/i },
        { label: /🔮 Forecast/i, heading: /Predictive Analytics/i },
        { label: /📄 Reports/i, heading: /Business Reports/i },
        { label: /Upload Dataset/i, heading: /Upload a dataset/i },
        { label: /🗂 Datasets/i, heading: /Account & Dataset Management/i },
        { label: /Settings/i, heading: /Workspace settings/i },
      ];

      for (const module of modules) {
        const navigationButton = screen.getByRole("button", { name: module.label });
        fireEvent.click(navigationButton);

        expect(navigationButton).toHaveClass("active");
        expect(await screen.findByRole("heading", { name: module.heading })).toBeInTheDocument();

        if (module.hasOverviewKpis) {
          expect(screen.getByTestId("overview-kpis")).toBeInTheDocument();
          expect(screen.getByRole("heading", { name: "Total Rows" })).toBeInTheDocument();
        } else {
          expect(screen.queryByTestId("overview-kpis")).not.toBeInTheDocument();
        }
      }

      expect(screen.getByText("10 rows · 2 columns")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Overview & Charts/i }));
      expect(screen.getByTestId("overview-kpis")).toBeInTheDocument();
    });

    it("submits a question to the evidence-backed AI analyst and renders its result", async () => {
      vi.spyOn(axios, "get").mockImplementation((url) => {
        if (url.includes("/api/auth/me")) {
          return Promise.resolve({
            data: {
              user: { id: "user-1", email: "analyst_user@example.com" },
              csrf_token: "test-csrf-token",
            },
          });
        }
        return Promise.reject(new Error("Not found"));
      });
      const postSpy = vi.spyOn(axios, "post").mockImplementation((url) => {
        if (url.includes("/upload")) {
          return Promise.resolve({
            data: {
              dataset_id: "analyst-dataset",
              columns: ["Region", "Profit"],
              numeric_columns: ["Profit"],
              date_columns: [],
              summary: { total_rows: 2, total_columns: 2, duplicate_rows_removed: 0, missing_values_handled: 0 },
              preview: [{ Region: "North", Profit: 100 }],
            },
          });
        }
        if (url.includes("/api/ai/analyze")) {
          return Promise.resolve({
            data: {
              interpreted_question: "Rank Region values by total Profit.",
              analytical_method: "Summed Profit by Region.",
              result: { records: [{ group: "North", value: 100 }] },
              explanation: "North has the highest observed total in this dataset.",
              business_implications: "This is descriptive, not causal.",
              recommended_next_action: "Review regional context.",
            },
          });
        }
        return Promise.resolve({ data: {} });
      });

      render(<App />);
      await screen.findByText("analyst_user@example.com");
      fireEvent.change(screen.getByLabelText(/Upload CSV \/ Excel/i), {
        target: { files: [new File(["Region,Profit\nNorth,100"], "analyst.csv", { type: "text/csv" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /Upload & Clean/i }));
      await screen.findByRole("button", { name: /✨ AI Analyst/i });
      fireEvent.click(screen.getByRole("button", { name: /✨ AI Analyst/i }));
      fireEvent.change(screen.getByLabelText(/Your question/i), {
        target: { value: "Which region generated the highest profit?" },
      });
      fireEvent.click(screen.getByRole("button", { name: /Analyze dataset/i }));

      expect(await screen.findByText("North has the highest observed total in this dataset.")).toBeInTheDocument();
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining("/api/ai/analyze"),
        {
          dataset_id: "analyst-dataset",
          question: "Which region generated the highest profit?",
        }
      );
    });

    it("renders root-cause and evaluated forecast results from their APIs", async () => {
      vi.spyOn(axios, "get").mockImplementation((url) => {
        if (url.includes("/api/auth/me")) {
          return Promise.resolve({
            data: { user: { id: "user-1", email: "forecast_user@example.com" } },
          });
        }
        return Promise.reject(new Error("Not found"));
      });
      vi.spyOn(axios, "post").mockImplementation((url) => {
        if (url.includes("/upload")) {
          return Promise.resolve({
            data: {
              dataset_id: "time-dataset",
              columns: ["Date", "Region", "Sales"],
              numeric_columns: ["Sales"],
              date_columns: ["Date"],
              summary: { total_rows: 12, total_columns: 3, duplicate_rows_removed: 0, missing_values_handled: 0 },
              preview: [{ Date: "2025-01-01", Region: "North", Sales: 100 }],
            },
          });
        }
        if (url.includes("/api/analytics/root-cause")) {
          return Promise.resolve({
            data: {
              previous_period: "2025-01",
              current_period: "2025-02",
              direction: "decrease",
              metric: "Sales",
              previous_value: 150,
              current_value: 90,
              absolute_change: -60,
              dimensions: [{ dimension: "Region", contributors: [{ group: "North", change: -50, direction: "decrease" }] }],
              limitations: ["Observed association; not causation."],
            },
          });
        }
        if (url.includes("/api/analytics/forecast")) {
          return Promise.resolve({
            data: {
              metrics: { mae: 10, rmse: 12, mape_percent: 8, mape_excluded_zero_actuals: 0 },
              historical: [{ period: "2025-01", value: 100 }],
              forecast: [{ period: "2025-02", prediction: 100, lower_bound: 80, upper_bound: 120 }],
              missing_period_policy: "No periods were missing.",
              uncertainty: "Approximate baseline interval; not guaranteed.",
            },
          });
        }
        return Promise.resolve({ data: {} });
      });

      render(<App />);
      await screen.findByText("forecast_user@example.com");
      fireEvent.change(screen.getByLabelText(/Upload CSV \/ Excel/i), {
        target: { files: [new File(["Date,Region,Sales\n2025-01-01,North,100"], "time.csv", { type: "text/csv" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /Upload & Clean/i }));
      await screen.findByRole("button", { name: /🔎 Root Cause/i });
      fireEvent.click(screen.getByRole("button", { name: /🔎 Root Cause/i }));
      fireEvent.click(await screen.findByRole("button", { name: /Analyze contributors/i }));
      expect(await screen.findByText("2025-01 to 2025-02: decrease")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /🔮 Forecast/i }));
      fireEvent.click(await screen.findByRole("button", { name: /Generate forecast/i }));
      expect(await screen.findByText(/MAE: 10\.00/)).toBeInTheDocument();
      expect(screen.getByTestId("mock-line-chart")).toBeInTheDocument();
    });

    it("lists and opens an existing user-owned dataset", async () => {
      vi.spyOn(axios, "get").mockImplementation((url) => {
        if (url.includes("/api/auth/me")) {
          return Promise.resolve({
            data: { user: { id: "user-1", email: "datasets_user@example.com" } },
          });
        }
        if (url.includes("/api/datasets")) {
          return Promise.resolve({
            data: {
              datasets: [{
                dataset_id: "saved-dataset",
                original_filename: "saved.csv",
                upload_timestamp: "2025-01-01T00:00:00Z",
                expires_at: "2030-01-01T00:00:00Z",
                columns: ["Region", "Sales"],
                numeric_columns: ["Sales"],
                date_columns: [],
                summary: { total_rows: 5, total_columns: 2 },
                preview: [{ Region: "North", Sales: 10 }],
              }],
            },
          });
        }
        if (url.includes("/api/reports")) {
          return Promise.resolve({
            data: {
              reports: [{
                report_id: "saved-report",
                dataset_id: "saved-dataset",
                dataset_name: "saved.csv",
                created_at: "2025-01-02T00:00:00Z",
              }],
            },
          });
        }
        return Promise.reject(new Error("Not found"));
      });

      render(<App />);
      await screen.findByText("datasets_user@example.com");
      fireEvent.click(screen.getByRole("button", { name: /🗂 Datasets/i }));
      expect(await screen.findByText("saved.csv")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /^Open$/i }));
      expect(await screen.findByText("Total Rows")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /📄 Reports/i }));
      expect(await screen.findByText("Saved reports")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Download PDF/i })).toBeInTheDocument();
    });
  });
});
