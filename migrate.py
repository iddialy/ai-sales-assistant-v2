from sqlalchemy import inspect, text

from models import Base, engine


def add_column_if_missing(connection, table_name, column_name, definition):
    inspector = inspect(connection)

    if not inspector.has_table(table_name):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if column_name in columns:
        return

    connection.execute(
        text(
            f'ALTER TABLE "{table_name}" '
            f'ADD COLUMN "{column_name}" {definition}'
        )
    )
    print(f"Added {table_name}.{column_name}")


def migrate():
    print("Starting database migration...")
    Base.metadata.create_all(bind=engine)

    merchant_columns = {
        "password_hash": "VARCHAR(255)",
        "language_preference": "VARCHAR(5)",
        "subscription_status": "VARCHAR(20)",
        "plan_code": "VARCHAR(30)",
        "expiry_date": "TIMESTAMP",
        "message_limit": "INTEGER",
        "messages_used": "INTEGER DEFAULT 0",
        "business_location": "VARCHAR(255)",
        "business_type": "VARCHAR(100)",
        "business_hours": "VARCHAR(255)",
        "business_description": "TEXT",
        "created_at": "TIMESTAMP",
    }

    product_columns = {
        "category": "VARCHAR(100)",
        "wholesale_price": "FLOAT",
        "retail_price": "FLOAT",
        "stock_quantity": "INTEGER DEFAULT 0",
        "status": "VARCHAR(20)",
        "image_url": "TEXT",
        "price": "FLOAT",
    }

    payment_columns = {
        "merchant_id": "VARCHAR(64)",
        "lipa_namba": "VARCHAR(100)",
        "bank_account": "VARCHAR(200)",
        "phone_payment": "VARCHAR(30)",
    }

    with engine.begin() as connection:
        for name, definition in merchant_columns.items():
            add_column_if_missing(
                connection,
                "merchants",
                name,
                definition,
            )

        for name, definition in product_columns.items():
            add_column_if_missing(
                connection,
                "products",
                name,
                definition,
            )

        for name, definition in payment_columns.items():
            add_column_if_missing(
                connection,
                "merchant_payment_info",
                name,
                definition,
            )

        inspector = inspect(connection)

        if inspector.has_table("products"):
            columns = {
                column["name"]
                for column in inspector.get_columns("products")
            }

            if "price" in columns and "retail_price" in columns:
                connection.execute(
                    text(
                        "UPDATE products "
                        "SET retail_price = price "
                        "WHERE retail_price IS NULL AND price IS NOT NULL"
                    )
                )

    print("Database migration completed successfully.")


if __name__ == "__main__":
    migrate()
