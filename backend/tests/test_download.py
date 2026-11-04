"""
test_download.py – Tests for the /download/<dataset_id> endpoint.

Covers: valid download, nonexistent dataset, invalid UUID,
response headers, CSV content structure.
"""

import io
import pytest


class TestDownloadValid:
    def test_returns_200(self, client, uploaded_dataset_id):
        resp = client.get(f"/download/{uploaded_dataset_id}")
        assert resp.status_code == 200

    def test_content_type_is_csv(self, client, uploaded_dataset_id):
        resp = client.get(f"/download/{uploaded_dataset_id}")
        ct = resp.content_type.lower()
        assert "csv" in ct or "octet-stream" in ct or "text/" in ct

    def test_download_name_header(self, client, uploaded_dataset_id):
        resp = client.get(f"/download/{uploaded_dataset_id}")
        cd = resp.headers.get("Content-Disposition", "")
        # Should include attachment and a filename
        assert "attachment" in cd.lower()

    def test_csv_content_contains_original_columns(self, client):
        """Downloaded CSV should contain the same columns as the uploaded data."""
        csv_content = b"Product,Sales\nWidget,100\nGadget,200\n"
        data = {"file": (io.BytesIO(csv_content), "data.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.get(f"/download/{dataset_id}")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Product" in body
        assert "Sales" in body

    def test_xlsx_download_works(self, client, uploaded_xlsx_dataset_id):
        resp = client.get(f"/download/{uploaded_xlsx_dataset_id}")
        assert resp.status_code == 200


class TestDownloadInvalidDataset:
    def test_nonexistent_dataset_returns_404(self, client):
        import uuid
        resp = client.get(f"/download/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_nonexistent_returns_json_error(self, client):
        import uuid
        resp = client.get(f"/download/{uuid.uuid4()}")
        body = resp.get_json()
        assert "error" in body

    def test_invalid_uuid_returns_400(self, client):
        resp = client.get("/download/not-a-valid-uuid")
        assert resp.status_code == 400

    def test_empty_string_id_returns_404(self, client):
        # Flask router won't match empty segment, returns 404
        resp = client.get("/download/")
        assert resp.status_code == 404

    def test_path_traversal_attempt_returns_400(self, client):
        resp = client.get("/download/../etc/passwd")
        # Either 404 (route not matched) or 400 (UUID validation)
        assert resp.status_code in (400, 404)
