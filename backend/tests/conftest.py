import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import database


@pytest.fixture
def db(tmp_path):
    """Use a temporary database for tests."""
    db_path = tmp_path / "test.db"
    with patch.object(database, "get_db_path", return_value=db_path):
        database.init_db()
        yield db_path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def json_array_file(temp_dir):
    """Create a sample JSON array file."""
    file_path = temp_dir / "test.json"
    file_path.write_text("""[
  {"name": "Alice", "age": 30, "active": true},
  {"name": "Bob", "age": 25, "active": false},
  {"name": "Charlie", "age": 35, "active": true}
]""")
    return file_path


@pytest.fixture
def ndjson_file(temp_dir):
    """Create a sample NDJSON file."""
    file_path = temp_dir / "test.ndjson"
    file_path.write_text("""{"name": "Alice", "age": 30, "active": true}
{"name": "Bob", "age": 25, "active": false}
{"name": "Charlie", "age": 35, "active": true}
""")
    return file_path


@pytest.fixture
def csv_file(temp_dir):
    """Create a sample CSV file."""
    file_path = temp_dir / "test.csv"
    file_path.write_text("""name,age,active
Alice,30,true
Bob,25,false
Charlie,35,true
""")
    return file_path


@pytest.fixture
def empty_file(temp_dir):
    """Create an empty file."""
    file_path = temp_dir / "empty.json"
    file_path.write_text("")
    return file_path


@pytest.fixture
def csv_semicolon_file(temp_dir):
    """Create a CSV file with semicolon delimiter."""
    file_path = temp_dir / "test_semicolon.csv"
    file_path.write_text("""name;age;active
Alice;30;true
Bob;25;false
""")
    return file_path
