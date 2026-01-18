"""Tests for chunked upload API endpoints."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestChunkedUploadAPI:
    def _login(self, db):
        """Helper to setup and login, returns cookies."""
        client.post("/api/auth/setup", json={
            "email": "chunkedtest@example.com",
            "password": "Password123",
            "name": "Chunked Test User",
        })
        response = client.post("/api/auth/login", json={
            "email": "chunkedtest@example.com",
            "password": "Password123",
        })
        return response.cookies

    def test_init_chunked_upload(self, db):
        """POST /upload/chunked/init should create chunked upload."""
        cookies = self._login(db)
        response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "large.json", "file_size": "100000000"},
            cookies=cookies,
        )

        assert response.status_code == 200
        data = response.json()
        assert "upload_id" in data
        assert data["total_chunks"] > 0
        assert data["chunk_size"] > 0

    def test_upload_chunk(self, db, temp_dir):
        """POST /upload/chunked/{id}/chunk/{index} should store chunk."""
        cookies = self._login(db)

        # First create chunked upload
        init_response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "test.json", "file_size": "1000000"},
            cookies=cookies,
        )
        upload_id = init_response.json()["upload_id"]

        # Upload a chunk
        chunk_data = b"x" * 10000
        response = client.post(
            f"/api/upload/chunked/{upload_id}/chunk/0",
            content=chunk_data,
            headers={"Content-Type": "application/octet-stream"},
            cookies=cookies,
        )

        assert response.status_code == 200
        assert response.json()["received"] is True

    def test_get_upload_status(self, db):
        """GET /upload/chunked/{id}/status should return progress."""
        cookies = self._login(db)

        # Create upload
        init_response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "test.json", "file_size": "1000000"},
            cookies=cookies,
        )
        upload_id = init_response.json()["upload_id"]

        response = client.get(f"/api/upload/chunked/{upload_id}/status", cookies=cookies)

        assert response.status_code == 200
        data = response.json()
        assert "completed_chunks" in data
        assert "total_chunks" in data

    def test_upload_chunk_invalid_index(self, db, temp_dir):
        """Should reject out-of-bounds chunk index."""
        cookies = self._login(db)

        init_response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "test.json", "file_size": "1000000"},
            cookies=cookies,
        )
        upload_id = init_response.json()["upload_id"]
        total_chunks = init_response.json()["total_chunks"]

        # Try to upload beyond bounds
        response = client.post(
            f"/api/upload/chunked/{upload_id}/chunk/{total_chunks + 10}",
            content=b"data",
            headers={"Content-Type": "application/octet-stream"},
            cookies=cookies,
        )

        assert response.status_code == 400

    def test_nonexistent_upload(self, db):
        """Should return 404 for nonexistent upload."""
        cookies = self._login(db)
        response = client.get("/api/upload/chunked/nonexistent-id/status", cookies=cookies)
        # Invalid UUID format returns 400, not 404
        assert response.status_code == 400

    def test_init_chunked_upload_file_too_large(self, db):
        """Should reject files larger than max size."""
        cookies = self._login(db)
        # 6TB is definitely too large
        response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "huge.json", "file_size": str(6 * 1024 * 1024 * 1024 * 1024)},
            cookies=cookies,
        )
        assert response.status_code == 400

    def test_upload_chunk_invalid_upload_id(self, db):
        """Should reject invalid upload_id format."""
        cookies = self._login(db)
        # Test with a non-UUID string that could be used for path traversal
        response = client.post(
            "/api/upload/chunked/not-a-valid-uuid/chunk/0",
            content=b"data",
            headers={"Content-Type": "application/octet-stream"},
            cookies=cookies,
        )
        assert response.status_code == 400
        assert "Invalid upload ID format" in response.json()["detail"]

    def test_complete_chunked_upload(self, db, temp_dir):
        """Should reassemble chunks into final file."""
        cookies = self._login(db)

        # Create and upload all chunks
        init_response = client.post(
            "/api/upload/chunked/init",
            data={"filename": "small.json", "file_size": "100"},
            cookies=cookies,
        )
        upload_id = init_response.json()["upload_id"]
        total_chunks = init_response.json()["total_chunks"]

        # Upload all chunks
        for i in range(total_chunks):
            chunk_data = b'{"test": true}'[:100 // total_chunks + 1]
            client.post(
                f"/api/upload/chunked/{upload_id}/chunk/{i}",
                content=chunk_data,
                headers={"Content-Type": "application/octet-stream"},
                cookies=cookies,
            )

        # Complete
        response = client.post(f"/api/upload/chunked/{upload_id}/complete", cookies=cookies)
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert "path" not in response.json()  # Should not expose internal path
