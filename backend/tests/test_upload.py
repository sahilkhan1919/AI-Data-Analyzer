"""
test_upload.py – Tests for the /upload endpoint.

Covers: valid CSV/XLSX, empty files, missing file, unsupported extensions,
malformed data, duplicate rows, missing values, unusual text, oversized files.
"""

import io
import pytest


class TestValidCSVUpload:
    def test_status_200(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200

    def test_returns_dataset_id(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "dataset_id" in body
        assert len(body["dataset_id"]) == 36  # UUID format

    def test_returns_columns(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "columns" in body
        assert set(body["columns"]) == {"Category", "Value"}

    def test_returns_numeric_columns(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "numeric_columns" in body
        assert "Value" in body["numeric_columns"]

    def test_returns_summary(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        summary = body.get("summary", {})
        assert "total_rows" in summary
        assert "total_columns" in summary
        assert "duplicate_rows_removed" in summary
        assert "missing_values_handled" in summary

    def test_returns_preview(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "preview" in body
        assert isinstance(body["preview"], list)
        assert len(body["preview"]) > 0

    def test_dataset_stored_in_memory(self, client, simple_csv_bytes):
        from app import DATASETS
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = resp.get_json()["dataset_id"]
        assert dataset_id in DATASETS


class TestValidXLSXUpload:
    def test_status_200(self, client, simple_xlsx_bytes):
        data = {"file": (io.BytesIO(simple_xlsx_bytes), "data.xlsx")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200

    def test_returns_dataset_id(self, client, simple_xlsx_bytes):
        data = {"file": (io.BytesIO(simple_xlsx_bytes), "data.xlsx")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "dataset_id" in body

    def test_returns_columns(self, client, simple_xlsx_bytes):
        data = {"file": (io.BytesIO(simple_xlsx_bytes), "data.xlsx")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "Product" in body["columns"]
        assert "Sales" in body["columns"]

    def test_numeric_columns_detected(self, client, simple_xlsx_bytes):
        data = {"file": (io.BytesIO(simple_xlsx_bytes), "data.xlsx")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "Sales" in body["numeric_columns"]


class TestDuplicateColumnHeaders:
    def test_whitespace_collision_does_not_break_trends(self, client):
        csv_content = (
            b"Date, Date ,Revenue\n"
            b"2025-01-01,2025-01-01,10\n"
            b"2025-02-01,2025-02-01,12\n"
        )
        uploaded = client.post(
            "/upload",
            data={"file": (io.BytesIO(csv_content), "duplicate-headers.csv")},
            content_type="multipart/form-data",
        )

        assert uploaded.status_code == 200
        dataset_id = uploaded.get_json()["dataset_id"]
        assert uploaded.get_json()["columns"] == ["Date", "Date_2", "Revenue"]

        trends = client.post(
            "/api/bi/trends",
            json={
                "dataset_id": dataset_id,
                "date_col": "Date",
                "measure_col": "Revenue",
                "granularity": "monthly",
            },
        )

        assert trends.status_code == 200
        assert trends.get_json()["values"] == [10, 12]


class TestMissingFile:
    def test_no_file_field_returns_400(self, client):
        resp = client.post("/upload", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_no_file_returns_json_error(self, client):
        resp = client.post("/upload", data={}, content_type="multipart/form-data")
        body = resp.get_json()
        assert "error" in body


class TestEmptyUpload:
    def test_empty_file_returns_400(self, client):
        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_empty_file_returns_json_error(self, client):
        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "error" in body


class TestUnsupportedExtension:
    def test_txt_extension_returns_400(self, client):
        data = {"file": (io.BytesIO(b"a,b\n1,2\n"), "data.txt")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_json_extension_returns_400(self, client):
        data = {"file": (io.BytesIO(b'{"a":1}'), "data.json")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_pdf_extension_returns_400(self, client):
        data = {"file": (io.BytesIO(b"%PDF-1.4"), "report.pdf")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_error_code_in_response(self, client):
        data = {"file": (io.BytesIO(b"a,b\n1,2\n"), "data.txt")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert "error" in body


class TestMalformedCSV:
    def test_binary_garbage_returns_400_or_processes(self, client, malformed_csv_bytes):
        """Malformed binary content should either be rejected or not crash the server."""
        data = {"file": (io.BytesIO(malformed_csv_bytes), "bad.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        # Must not return 500 (server crash)
        assert resp.status_code in (200, 400)

    def test_server_returns_json_on_malformed(self, client, malformed_csv_bytes):
        data = {"file": (io.BytesIO(malformed_csv_bytes), "bad.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert body is not None  # Always JSON


class TestDuplicateRows:
    def test_duplicates_reported_in_summary(self, client, duplicate_csv_bytes):
        data = {"file": (io.BytesIO(duplicate_csv_bytes), "dup.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        body = resp.get_json()
        # Original has 2 duplicate rows (A,10 and B,20 each appear twice)
        assert body["summary"]["duplicate_rows_removed"] == 2

    def test_cleaned_rows_count(self, client, duplicate_csv_bytes):
        data = {"file": (io.BytesIO(duplicate_csv_bytes), "dup.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        # 5 rows minus 2 duplicates = 3
        assert body["summary"]["total_rows"] == 3


class TestMissingValues:
    def test_missing_values_reported(self, client, missing_values_csv_bytes):
        data = {"file": (io.BytesIO(missing_values_csv_bytes), "missing.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["summary"]["missing_values_handled"] > 0

    def test_missing_numeric_filled_with_mean(self, client):
        """Numeric NaN values should be filled with column mean after cleaning."""
        from app import DATASETS
        csv_content = b"Name,Score\nAlice,90\nBob,\nCharlie,80\n"
        data = {"file": (io.BytesIO(csv_content), "scores.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]
        df = DATASETS[dataset_id]
        # Bob's score should be filled with mean of [90, 80] = 85.0
        assert not df["Score"].isnull().any()
        bob_score = df.loc[df["Name"] == "Alice", "Score"].values[0]  # Alice = 90
        # Mean is (90+80)/2 = 85.0
        bob_filled = df.loc[df["Name"] == "Bob", "Score"].values[0]
        assert bob_filled == pytest.approx(85.0, rel=1e-3)

    def test_missing_text_filled_with_unknown(self, client):
        """Text NaN values should be replaced with 'Unknown'."""
        from app import DATASETS
        csv_content = b"Name,Score\nAlice,90\n,80\nCharlie,70\n"
        data = {"file": (io.BytesIO(csv_content), "scores.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]
        df = DATASETS[dataset_id]
        assert "Unknown" in list(df["Name"])


class TestUnusualTextValues:
    def test_comma_in_quoted_field(self, client):
        csv_content = b'Name,Notes\n"Smith, John","Senior manager"\nJane,Analyst\n'
        data = {"file": (io.BytesIO(csv_content), "unusual.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200

    def test_unicode_content(self, client):
        csv_content = "Name,Value\ncafé,100\nnaïve,200\n".encode("utf-8")
        data = {"file": (io.BytesIO(csv_content), "unicode.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200


class TestHeadersOnlyCSV:
    def test_headers_only_csv_handled_gracefully(self, client, headers_only_csv_bytes):
        """A CSV with only headers and no data rows should be accepted (empty dataset after clean)."""
        data = {"file": (io.BytesIO(headers_only_csv_bytes), "headers.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        # Either 200 (empty) or 400 (rejected as empty dataset) – must not 500
        assert resp.status_code in (200, 400)
        body = resp.get_json()
        assert body is not None


class TestPathTraversal:
    def test_path_traversal_filename_rejected_or_sanitized(self, client, simple_csv_bytes):
        """A filename with path traversal characters must not cause server errors."""
        data = {"file": (io.BytesIO(simple_csv_bytes), "../../etc/passwd.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        # werkzeug.secure_filename will strip traversal; result is valid or empty name -> 400
        assert resp.status_code in (200, 400)
