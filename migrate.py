"""Safe production database migration for AI Sales Assistant.

This script is intentionally idempotent and is safe to run on every Render deploy.
"""
from main import init_database

if __name__ == "__main__":
    print("Starting database migration...")
    init_database()
    print("Database migration completed successfully.")
