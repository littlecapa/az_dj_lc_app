import os
import pyodbc
import sys

def test_connection():
    try:
        conn_str = r"""
            DRIVER={ODBC Driver 18 for SQL Server};
            SERVER=lcsqlserver.database.windows.net;
            DATABASE=lc_db;
            UID=lc_db_admin@lcsqlserver;
            PWD=xxx;
            Encrypt=yes;
            TrustServerCertificate=yes;
            Connection Timeout=30;
            """
        conn = pyodbc.connect(conn_str)
        
        print("Testing database connection...")
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        print("✅ Database connection successful!")
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}")
        print(f"Details: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)