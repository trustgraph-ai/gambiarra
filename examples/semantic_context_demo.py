"""
Demo script for Semantic Context Management.

This demonstrates how the semantic context manager intelligently selects
relevant files based on semantic similarity, dependencies, and access patterns.
"""

import sys
from pathlib import Path
import tempfile
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gambiarra.server.core.context import (
    SemanticContextManager,
    FileEmbeddingSystem
)
from gambiarra.server.core.session.context import ContextManager


def create_sample_files(temp_dir: Path) -> dict:
    """Create sample Python files for demonstration."""

    files = {}

    # Main application file
    files['main.py'] = """
import logging
from database import Database
from api import create_app

logger = logging.getLogger(__name__)

def main():
    '''Main application entry point.'''
    db = Database()
    app = create_app(db)
    app.run()

if __name__ == '__main__':
    main()
"""

    # Database module
    files['database.py'] = """
import sqlite3
from typing import List, Dict, Any

class Database:
    '''Database connection and query handling.'''

    def __init__(self, db_path: str = 'app.db'):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def query(self, sql: str, params: tuple = ()) -> List[Dict]:
        '''Execute query and return results.'''
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    def close(self):
        '''Close database connection.'''
        self.conn.close()
"""

    # API module
    files['api.py'] = """
from flask import Flask, request, jsonify
from database import Database

def create_app(database: Database) -> Flask:
    '''Create and configure Flask application.'''
    app = Flask(__name__)

    @app.route('/users', methods=['GET'])
    def get_users():
        users = database.query('SELECT * FROM users')
        return jsonify(users)

    @app.route('/users/<int:user_id>', methods=['GET'])
    def get_user(user_id):
        user = database.query('SELECT * FROM users WHERE id = ?', (user_id,))
        return jsonify(user[0] if user else {})

    return app
"""

    # Utility module
    files['utils.py'] = """
import hashlib
from datetime import datetime

def hash_password(password: str) -> str:
    '''Hash a password using SHA256.'''
    return hashlib.sha256(password.encode()).hexdigest()

def format_timestamp(ts: float) -> str:
    '''Format Unix timestamp as ISO string.'''
    return datetime.fromtimestamp(ts).isoformat()

def validate_email(email: str) -> bool:
    '''Validate email address format.'''
    return '@' in email and '.' in email.split('@')[1]
"""

    # Tests
    files['test_database.py'] = """
import pytest
from database import Database

def test_database_connection():
    '''Test database connection.'''
    db = Database(':memory:')
    assert db.conn is not None
    db.close()

def test_query():
    '''Test database query execution.'''
    db = Database(':memory:')
    db.cursor.execute('CREATE TABLE test (id INT, name TEXT)')
    db.cursor.execute('INSERT INTO test VALUES (1, "test")')
    results = db.query('SELECT * FROM test')
    assert len(results) == 1
    db.close()
"""

    # README
    files['README.md'] = """
# Sample Application

This is a sample Flask application with database connectivity.

## Features
- RESTful API endpoints
- SQLite database
- User management
- Password hashing

## Setup
1. Install dependencies: `pip install flask`
2. Run application: `python main.py`
"""

    # Write files to temp directory
    file_paths = {}
    for filename, content in files.items():
        filepath = temp_dir / filename
        filepath.write_text(content)
        file_paths[filename] = str(filepath)

    return file_paths


def main():
    """Demonstrate semantic context management."""

    print("=" * 80)
    print("SEMANTIC CONTEXT MANAGEMENT DEMO")
    print("=" * 80)
    print()

    # Create temporary directory with sample files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        file_paths = create_sample_files(temp_path)

        print(f"Created {len(file_paths)} sample files in {temp_dir}")
        print()

        # Initialize managers
        from gambiarra.server.core.context import SimpleEmbeddingBackend, FileEmbeddingSystem

        # Use simple backend for demo (no dependencies required)
        simple_backend = SimpleEmbeddingBackend(embedding_dim=100)
        embedding_system = FileEmbeddingSystem(backend=simple_backend)

        context_manager = ContextManager()
        semantic_manager = SemanticContextManager(
            context_manager=context_manager,
            embedding_system=embedding_system,
            max_files=5,  # Limit context to 5 files
            min_relevance_score=0.2
        )

        session_id = "demo-session"

        # Create context
        context_manager.create_context(session_id, str(temp_path))

        # Simulate accessing files
        print("Step 1: Simulating file access...")
        print("-" * 80)

        for filename, filepath in file_paths.items():
            content = Path(filepath).read_text()
            context_manager.track_file_access(session_id, filepath, content)
            print(f"  Tracked: {filename}")

        print()

        # Select relevant files based on main.py
        print("Step 2: Finding files relevant to main.py...")
        print("-" * 80)

        main_file = file_paths['main.py']
        relevant_files = semantic_manager.select_relevant_files(
            session_id=session_id,
            query_files=[main_file],
            task_description="Understanding the main application entry point"
        )

        print(f"\nSelected {len(relevant_files)} relevant files:\n")

        for i, file_score in enumerate(relevant_files, 1):
            filename = Path(file_score.file_path).name
            print(f"{i}. {filename}")
            print(f"   Total Score: {file_score.total_score:.3f}")
            print(f"   - Semantic:   {file_score.semantic_score:.3f}")
            print(f"   - Dependency: {file_score.dependency_score:.3f}")
            print(f"   - Access:     {file_score.access_score:.3f}")
            print(f"   - Recency:    {file_score.recency_score:.3f}")
            if file_score.reasons:
                print(f"   Reasons: {', '.join(file_score.reasons)}")
            print()

        # Select files relevant to database work
        print("Step 3: Finding files relevant to database operations...")
        print("-" * 80)

        db_file = file_paths['database.py']
        relevant_files = semantic_manager.select_relevant_files(
            session_id=session_id,
            query_files=[db_file],
            task_description="Working on database query optimization"
        )

        print(f"\nSelected {len(relevant_files)} relevant files:\n")

        for i, file_score in enumerate(relevant_files, 1):
            filename = Path(file_score.file_path).name
            print(f"{i}. {filename} (score: {file_score.total_score:.3f})")

        print()

        # Get context summary
        print("Step 4: Context Summary")
        print("-" * 80)

        summary = semantic_manager.get_context_summary(session_id)

        print(f"Session ID: {summary['session_id']}")
        print(f"Total files tracked: {summary['total_files']}")
        print(f"Embeddings generated: {summary['embeddings_generated']}")
        print(f"Max context files: {summary['max_context_files']}")
        print(f"Min relevance score: {summary['min_relevance_score']}")
        print()

        # Show benefit
        print("=" * 80)
        print("KEY BENEFIT")
        print("=" * 80)
        print()
        print("Instead of blindly including all files (or limiting to 200 files),")
        print("the semantic context manager intelligently selects the MOST RELEVANT")
        print("files based on:")
        print()
        print("  1. Semantic similarity (what the code does)")
        print("  2. Dependency relationships (imports, requires)")
        print("  3. Access patterns (frequently used files)")
        print("  4. Recency (recently accessed)")
        print("  5. Task relevance (matches current task)")
        print()
        print("This means:")
        print("  ✓ Smaller, more focused context windows")
        print("  ✓ More relevant information for the LLM")
        print("  ✓ Better performance (fewer tokens)")
        print("  ✓ More accurate responses")
        print()

    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
