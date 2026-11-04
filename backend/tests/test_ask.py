"""
test_ask.py – Tests for the /ask (Ask Your Data) endpoint.

Covers: supported question types, edge cases, invalid dataset,
empty question, non-string input.
"""

import io
import pytest


@pytest.fixture()
def ask_dataset_id(client):
    """Upload a cricket-style CSV suitable for count/how-many queries."""
    csv_content = (
        b"Player,Format,Hundreds,Fifties\n"
        b"Alice,T20,5,20\n"
        b"Bob,ODI,3,15\n"
        b"Charlie,T20,8,30\n"
        b"Dave,Test,10,25\n"
    )
    data = {"file": (io.BytesIO(csv_content), "cricket.csv")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    return resp.get_json()["dataset_id"]


@pytest.fixture()
def sales_dataset_id(client):
    """Upload a sales CSV suitable for average/total/max/min/top queries."""
    csv_content = (
        b"Product,Region,Sales\n"
        b"Widget,North,100\n"
        b"Gadget,South,200\n"
        b"Widget,South,150\n"
        b"Gadget,North,250\n"
        b"Doohickey,North,50\n"
    )
    data = {"file": (io.BytesIO(csv_content), "sales.csv")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    return resp.get_json()["dataset_id"]


class TestAskCountRows:
    def test_count_rows_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "count rows"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "5" in body["answer"]  # 5 rows in dataset

    def test_rows_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "how many rows"},
        )
        assert resp.status_code == 200

    def test_returns_answer_and_table_fields(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "count rows"},
        )
        body = resp.get_json()
        assert "answer" in body
        assert "table" in body


class TestAskColumns:
    def test_columns_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "show columns"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "Product" in body["answer"]
        assert "Sales" in body["answer"]


class TestAskStatistical:
    def test_average_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "average sales"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        # Average of [100,200,150,250,50] = 750/5 = 150.0
        assert "150.00" in body["answer"]

    def test_total_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "total sales"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "750.00" in body["answer"]

    def test_maximum_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "maximum sales"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "250.00" in body["answer"]

    def test_minimum_question(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "minimum sales"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "50.00" in body["answer"]


class TestAskTop:
    def test_top_5_returns_table(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "top 5 product by sales"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body["table"], list)
        assert len(body["table"]) > 0

    def test_top_n_respects_number(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "top 2 product by sales"},
        )
        body = resp.get_json()
        assert len(body["table"]) <= 2


class TestAskHowMany:
    def test_how_many_returns_answer(self, client, ask_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": ask_dataset_id, "question": "how many hundreds in t20"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "answer" in body
        # Alice (5) + Charlie (8) = 13 hundreds in T20
        assert "13" in body["answer"]


class TestAskUnknownQuestion:
    def test_unknown_question_returns_hint(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "what is the meaning of life"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        # Should return a hint message
        assert "answer" in body
        assert len(body["answer"]) > 0


class TestAskInvalidInput:
    def test_nonexistent_dataset_returns_404(self, client):
        import uuid
        resp = client.post(
            "/ask",
            json={"dataset_id": str(uuid.uuid4()), "question": "count rows"},
        )
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, client):
        resp = client.post(
            "/ask",
            json={"dataset_id": "not-a-uuid", "question": "count rows"},
        )
        assert resp.status_code == 400

    def test_empty_question_returns_400(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": ""},
        )
        assert resp.status_code == 400

    def test_whitespace_only_question_returns_400(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": "   "},
        )
        assert resp.status_code == 400

    def test_non_string_question_returns_400(self, client, sales_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": sales_dataset_id, "question": 12345},
        )
        assert resp.status_code == 400

    def test_non_json_returns_415(self, client, sales_dataset_id):
        resp = client.post("/ask", data="not json", content_type="text/plain")
        assert resp.status_code == 415
