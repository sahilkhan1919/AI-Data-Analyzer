"""
test_error_handling.py – Tests for centralised error handling.

Covers: malformed JSON, wrong content-type, unexpected types,
consistent error structure, no traceback leakage.
"""

import io
import pytest


class TestErrorStructure:
    def test_upload_no_file_error_structure(self, client):
        """Error responses should have a nested 'error' dict with code and message."""
        resp = client.post("/upload", data={}, content_type="multipart/form-data")
        body = resp.get_json()
        assert "error" in body
        err = body["error"]
        assert "code" in err
        assert "message" in err

    def test_chart_invalid_dataset_error_structure(self, client):
        import uuid
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": str(uuid.uuid4()),
                "chart_type": "Bar",
                "x_axis": "A",
                "y_axis": "B",
            },
        )
        body = resp.get_json()
        assert "error" in body
        err = body["error"]
        assert "code" in err
        assert "message" in err

    def test_error_message_is_string(self, client):
        import uuid
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": str(uuid.uuid4()),
                "chart_type": "Bar",
                "x_axis": "A",
                "y_axis": "B",
            },
        )
        body = resp.get_json()
        assert isinstance(body["error"]["message"], str)

    def test_error_code_is_string(self, client):
        import uuid
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": str(uuid.uuid4()),
                "chart_type": "Bar",
                "x_axis": "A",
                "y_axis": "B",
            },
        )
        body = resp.get_json()
        assert isinstance(body["error"]["code"], str)


class TestNoTracebackLeakage:
    def test_no_traceback_in_upload_error(self, client):
        """Traceback strings must not appear in API error responses."""
        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        text = resp.get_data(as_text=True)
        assert "Traceback" not in text
        assert "File \"" not in text

    def test_no_filesystem_path_in_error(self, client):
        """Filesystem paths must not appear in API error responses."""
        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        text = resp.get_data(as_text=True)
        # Check that common path patterns are not leaked
        import re
        assert not re.search(r"[A-Za-z]:\\", text)  # Windows paths
        assert "/home/" not in text
        assert "/usr/" not in text

    def test_no_internal_exception_details(self, client):
        import uuid
        resp = client.post(
            "/ask",
            json={"dataset_id": str(uuid.uuid4()), "question": "total sales"},
        )
        text = resp.get_data(as_text=True)
        assert "Traceback" not in text
        assert "Exception" not in text


class TestHTTPStatusCodes:
    def test_missing_file_is_400_not_500(self, client):
        resp = client.post("/upload", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_invalid_dataset_is_404_not_500(self, client):
        import uuid
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": str(uuid.uuid4()),
                "chart_type": "Bar",
                "x_axis": "A",
                "y_axis": "B",
            },
        )
        assert resp.status_code == 404

    def test_wrong_content_type_is_415_not_500(self, client):
        resp = client.post("/chart-data", data="plain text", content_type="text/plain")
        assert resp.status_code == 415

    def test_invalid_uuid_is_400_not_404(self, client):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": "definitely-not-a-uuid",
                "chart_type": "Bar",
                "x_axis": "A",
                "y_axis": "B",
            },
        )
        assert resp.status_code == 400

    def test_unsupported_extension_is_400(self, client):
        data = {"file": (io.BytesIO(b"a,b\n1,2"), "data.xml")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400


class TestDatasetIsolation:
    def test_datasets_isolated_between_uploads(self, client, simple_csv_bytes):
        """Two uploads produce two distinct dataset IDs."""
        data1 = {"file": (io.BytesIO(simple_csv_bytes), "d1.csv")}
        data2 = {"file": (io.BytesIO(simple_csv_bytes), "d2.csv")}
        r1 = client.post("/upload", data=data1, content_type="multipart/form-data")
        r2 = client.post("/upload", data=data2, content_type="multipart/form-data")
        id1 = r1.get_json()["dataset_id"]
        id2 = r2.get_json()["dataset_id"]
        assert id1 != id2
