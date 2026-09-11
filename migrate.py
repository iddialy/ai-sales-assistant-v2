from sqlalchemy import inspect, text

from models import engine


def add_column_if_missing(
    connection,
    table_name,
    column_name,
    column_definition
):
    inspector = inspect(connection)

    columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if column_name not in columns:
        print(
            f"Adding {table_name}.{column_name}..."
        )

        connection.execute(
            text(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} "
                f"{column_definition}"
            )
        )

        print(
            f"Added {table_name}.{column_name}"
        )

    else:
        print(
            f"{table_name}.{column_name} already exists."
        )


def migrate():
    print("Starting database migration...")

    with engine.begin() as connection:

        # =========================
        # MERCHANTS
        # =========================

        add_column_if_missing(
            connection,
            "merchants",
            "business_location",
            "VARCHAR(255)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_type",
            "VARCHAR(100)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_hours",
            "VARCHAR(255)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_description",
            "TEXT"
        )

        # =========================
        # PRODUCTS
        # =========================

        add_column_if_missing(
            connection,
            "products",
            "image_url",
            "TEXT"
        )

        add_column_if_missing(
            connection,
            "products",
            "category",
            "VARCHAR(100)"
        )

        add_column_if_missing(
            connection,
            "products",
            "wholesale_price",
            "FLOAT"
        )

        add_column_if_missing(
            connection,
            "products",
            "retail_price",
            "FLOAT"
        )

        add_column_if_missing(
            connection,
            "products",
            "stock_quantity",
            "INTEGER DEFAULT 0"
        )

        add_column_if_missing(
            connection,
            "products",
            "status",
            "VARCHAR(20) DEFAULT 'IPO'"
        )

    print("Database migration completed successfully.")


if __name__ == "__main__":
    migrate()
