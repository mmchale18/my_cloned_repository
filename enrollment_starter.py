"""
Module 8 Student Enrollment backend starter.

This file has been refactored into a layered backend architecture.
The database layer is responsible for SQLite operations only, and the
service layer is responsible for business logic.

App idea:
    - a student opens a dashboard
    - the dashboard shows enrolled classes
    - the student enters an enrollment key to join another class
    - the database stores courses and enrollment records
    - a JSON snapshot is exported so students can inspect the seeded data

Focus:
    - student enrollment behavior
    - local SQLite database
    - enrollment keys
    - soft unenroll using status = "unenrolled"

Out of scope:
    - Streamlit UI
    - authentication/session state
    - caching
    - export formatting
    - production health checks

Run with:
    enrollment_starter.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


DB_PATH = Path(__file__).with_name("student_enrollment_practice.db")
SNAPSHOT_PATH = Path(__file__).with_name("student_enrollment_snapshot.json")

CURRENT_STUDENT = {
    "user_id": "u100",
    "name": "Maya Patel",
    "email": "maya.patel@example.edu",
}

STATUS_ENROLLED = "enrolled"
STATUS_UNENROLLED = "unenrolled"

AVAILABLE_COURSE_KEYS = [
    {
        "course_id": "MISY350",
        "course_name": "Python for Business Analytics",
        "instructor": "Dr. Rivera",
        "enrollment_key": "MISY350-SPRING",
    },
    {
        "course_id": "DATA210",
        "course_name": "Data Storytelling",
        "instructor": "Prof. Morgan",
        "enrollment_key": "DATA210-SPRING",
    },
    {
        "course_id": "WEB220",
        "course_name": "Web Apps With Streamlit",
        "instructor": "Dr. Chen",
        "enrollment_key": "WEB220-SPRING",
    },
]

SAMPLE_ENROLLMENTS = [
    ("u100", "maya.patel@example.edu", "MISY350", STATUS_ENROLLED),
    ("u100", "maya.patel@example.edu", "DATA210", STATUS_UNENROLLED),
    ("u101", "alex@example.edu", "MISY350", STATUS_ENROLLED),
    ("u102", "blair@example.edu", "WEB220", STATUS_ENROLLED),
]


class DatabaseManager:
    """Handle SQLite database operations only."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._connect() as connection:
            cursor = connection.execute(sql, params)
            connection.commit()
            return cursor

    def executemany(self, sql: str, param_sequence: Iterable[Sequence[Any]]) -> None:
        with self._connect() as connection:
            connection.executemany(sql, param_sequence)
            connection.commit()

    def create_tables(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                course_name TEXT NOT NULL,
                instructor TEXT NOT NULL,
                enrollment_key TEXT NOT NULL UNIQUE
            )
            """
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS enrollments (
                enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                course_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'enrolled',
                enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, course_id),
                FOREIGN KEY(course_id) REFERENCES courses(course_id)
            )
            """
        )

    def seed_courses(self, course_rows: list[dict[str, Any]]) -> None:
        self.executemany(
            """
            INSERT OR IGNORE INTO courses (
                course_id, course_name, instructor, enrollment_key
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    course["course_id"],
                    course["course_name"],
                    course["instructor"],
                    course["enrollment_key"],
                )
                for course in course_rows
            ],
        )

    def seed_enrollments(self, enrollment_rows: list[tuple[str, str, str, str]]) -> None:
        self.executemany(
            """
            INSERT OR IGNORE INTO enrollments (user_id, email, course_id, status)
            VALUES (?, ?, ?, ?)
            """,
            enrollment_rows,
        )


class EnrollmentService:
    """Handle business logic for student enrollment workflows."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    @staticmethod
    def normalize_enrollment_key(enrollment_key: str) -> str:
        return enrollment_key.strip().upper()

    def get_available_course_keys(self) -> list[dict[str, Any]]:
        rows = self.db_manager.fetch_all(
            """
            SELECT course_id, course_name, instructor, enrollment_key
            FROM courses
            ORDER BY course_id
            """
        )
        return DatabaseManager.rows_to_dicts(rows)

    def get_course_by_key(self, enrollment_key: str) -> Optional[dict[str, Any]]:
        if not enrollment_key:
            return None

        normalized_key = self.normalize_enrollment_key(enrollment_key)
        row = self.db_manager.fetch_one(
            """
            SELECT course_id, course_name, instructor, enrollment_key
            FROM courses
            WHERE enrollment_key = ?
            """,
            (normalized_key,),
        )
        return dict(row) if row else None

    def get_student_enrollments(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id:
            return []

        rows = self.db_manager.fetch_all(
            """
            SELECT
                e.enrollment_id,
                e.user_id,
                e.email,
                e.course_id,
                c.course_name,
                c.instructor,
                e.status,
                e.enrolled_at
            FROM enrollments e
            JOIN courses c ON c.course_id = e.course_id
            WHERE e.user_id = ? AND e.status = ?
            ORDER BY c.course_id
            """,
            (user_id, STATUS_ENROLLED),
        )
        return DatabaseManager.rows_to_dicts(rows)

    def get_student_enrollment_history(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id:
            return []

        rows = self.db_manager.fetch_all(
            """
            SELECT
                e.enrollment_id,
                e.user_id,
                e.email,
                e.course_id,
                c.course_name,
                c.instructor,
                e.status,
                e.enrolled_at
            FROM enrollments e
            JOIN courses c ON c.course_id = e.course_id
            WHERE e.user_id = ?
            ORDER BY c.course_id
            """,
            (user_id,),
        )
        return DatabaseManager.rows_to_dicts(rows)

    def get_student_course_record(
        self,
        user_id: str,
        course_id: str,
    ) -> Optional[dict[str, Any]]:
        if not user_id or not course_id:
            return None

        row = self.db_manager.fetch_one(
            """
            SELECT enrollment_id, user_id, email, course_id, status, enrolled_at
            FROM enrollments
            WHERE user_id = ? AND course_id = ?
            """,
            (user_id, course_id),
        )
        return dict(row) if row else None

    def enroll_with_key(
        self,
        user_id: str,
        email: str,
        enrollment_key: str,
    ) -> Optional[dict[str, Any]]:
        if not user_id or not email or "@" not in email or not enrollment_key:
            return None

        course = self.get_course_by_key(enrollment_key)
        if not course:
            return None

        self.db_manager.execute(
            """
            INSERT INTO enrollments (user_id, email, course_id, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, course_id)
            DO UPDATE SET
                email = excluded.email,
                status = excluded.status,
                enrolled_at = CURRENT_TIMESTAMP
            """,
            (user_id, email, course["course_id"], STATUS_ENROLLED),
        )
        return self.get_student_course_record(user_id, course["course_id"])

    def soft_unenroll_student(self, user_id: str, course_id: str) -> bool:
        if not user_id or not course_id:
            return False

        cursor = self.db_manager.execute(
            """
            UPDATE enrollments
            SET status = ?
            WHERE user_id = ? AND course_id = ?
            """,
            (STATUS_UNENROLLED, user_id, course_id),
        )
        return cursor.rowcount > 0

    def get_student_summary(self, user_id: str) -> dict[str, int]:
        summary = {
            "total_records": 0,
            STATUS_ENROLLED: 0,
            STATUS_UNENROLLED: 0,
        }

        for record in self.get_student_enrollment_history(user_id):
            summary["total_records"] += 1
            status = record["status"]
            if status in summary:
                summary[status] += 1

        return summary

    def get_all_enrollment_records(self) -> list[dict[str, Any]]:
        rows = self.db_manager.fetch_all(
            """
            SELECT
                e.enrollment_id,
                e.user_id,
                e.email,
                e.course_id,
                c.course_name,
                c.instructor,
                e.status,
                e.enrolled_at
            FROM enrollments e
            JOIN courses c ON c.course_id = e.course_id
            ORDER BY e.user_id, e.course_id
            """
        )
        return DatabaseManager.rows_to_dicts(rows)


def export_database_snapshot(
    service: EnrollmentService,
    current_student: dict[str, Any],
    path: Path = SNAPSHOT_PATH,
) -> None:
    snapshot = {
        "current_student": current_student,
        "available_course_keys": service.get_available_course_keys(),
        "enrollment_table": service.get_all_enrollment_records(),
    }
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def main() -> None:
    db_manager = DatabaseManager(DB_PATH)
    service = EnrollmentService(db_manager)

    db_manager.create_tables()
    db_manager.seed_courses(AVAILABLE_COURSE_KEYS)
    db_manager.seed_enrollments(SAMPLE_ENROLLMENTS)

    user_id = CURRENT_STUDENT["user_id"]
    email = CURRENT_STUDENT["email"]

    print("Current student:")
    print(CURRENT_STUDENT)

    print("\nAvailable enrollment keys:")
    print(service.get_available_course_keys())

    print("\nInitial enrolled classes:")
    print(service.get_student_enrollments(user_id))

    print("\nStudent enters key DATA210-SPRING:")
    print(service.enroll_with_key(user_id, email, "DATA210-SPRING"))

    print("\nUpdated enrolled classes:")
    print(service.get_student_enrollments(user_id))

    print("\nStudent summary:")
    print(service.get_student_summary(user_id))

    export_database_snapshot(service, CURRENT_STUDENT)
    print(f"\nDatabase snapshot written to: {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
