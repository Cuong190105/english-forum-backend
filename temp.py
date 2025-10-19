import psycopg2

def drop_all_tables(db_name, user, password, host, port, schema='public'):
    """
    Drops all tables in a specified PostgreSQL schema.
    """
    conn = None
    cursor = None
    try:
        # Establish connection
        conn = psycopg2.connect(
            database=db_name,
            user=user,
            password=password,
            host=host,
            port=port
        )
        cursor = conn.cursor()

        # Get all table names in the specified schema
        cursor.execute(f"""
            SELECT tablename FROM pg_tables WHERE schemaname = '{schema}';
        """)
        tables = cursor.fetchall()

        # Drop each table
        for table in tables:
            table_name = table[0]
            print(f"Dropping table: {table_name}")
            cursor.execute(f"DROP TABLE IF EXISTS {schema}.{table_name} CASCADE;")

        # Commit the changes
        conn.commit()
        print("All tables dropped successfully.")

    except psycopg2.Error as e:
        print(f"Error dropping tables: {e}")
        if conn:
            conn.rollback()  # Rollback in case of error
    finally:
        # Close cursor and connection
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Example usage:
if __name__ == "__main__":
    DB_NAME = "your_database_name"
    DB_USER = "your_username"
    DB_PASSWORD = "your_password"
    DB_HOST = "localhost"
    DB_PORT = "5432"

    drop_all_tables(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
