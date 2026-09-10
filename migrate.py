from sqlalchemy import inspect, text

from models import engine


def add_column_if_missing(
    connection,
    table_name: str,
    column_name: str,
    column_definition: str,
):
    inspector = inspect(connection)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if column_name not in existing_columns:
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
            f"{table_name}.{column_name} already exists"
        )


def migrate():
    print("Starting database migration...")

    with engine.begin() as connection:

        # -------------------------
        # Merchant Business Profile
        # -------------------------

        add_column_if_missing(
            connection,
            "merchants",
            "business_location",
            "VARCHAR(300)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_type",
            "VARCHAR(150)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_hours",
            "VARCHAR(300)"
        )

        add_column_if_missing(
            connection,
            "merchants",
            "business_description",
            "TEXT"
        )

        # -------------------------
        # Product Image
        # -------------------------

        add_column_if_missing(
            connection,
            "products",
            "image_url",
            "TEXT"
        )

    print("Database migration completed successfully.")


if __name__ == "__main__":
    migrate()
