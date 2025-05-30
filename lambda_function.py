import boto3
import pymysql
import os
import json
import socket


import pymysql
from pymysql.cursors import DictCursor
 
ACCOUNT_TABLE= "Accounts"
TRANSACTIONS_TABLE = "Transactions"
CUSTOMERS_TABLE = "Customers"

CUSTOMERS = [
    {"customer_id": 1, "name": "Alice Smith", "email": "alice@example.com", "phone": "123-456-7890"},
    {"customer_id": 2, "name": "Bob Johnson", "email": "bob@example.com", "phone": "234-567-8901"},
    {"customer_id": 3, "name": "Charlie Lee", "email": "charlie@example.com", "phone": "345-678-9012"}
]
 
ACCOUNTS = [
    {"account_id": 101, "customer_id": 1, "account_type": "savings", "balance": 1200.50},
    {"account_id": 102, "customer_id": 1, "account_type": "checking", "balance": 500.00},
    {"account_id": 103, "customer_id": 2, "account_type": "savings", "balance": 750.75},
    {"account_id": 104, "customer_id": 3, "account_type": "checking", "balance": 300.25}
]
 
TRANSACTIONS = [
    {"transaction_id": 1001, "account_id": 101, "amount": -100.00, "description": "ATM Withdrawal"},
    {"transaction_id": 1002, "account_id": 101, "amount": 250.00, "description": "Salary Deposit"},
    {"transaction_id": 1003, "account_id": 102, "amount": -50.00, "description": "Grocery Store"},
    {"transaction_id": 1004, "account_id": 103, "amount": -200.00, "description": "Online Purchase"},
    {"transaction_id": 1005, "account_id": 104, "amount": 150.00, "description": "Check Deposit"}
]


class MySQLHelper:
    def __init__(self, host, port, user, password, db):
        try:
            self.connection = pymysql.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                database=db,
                cursorclass=DictCursor,
                autocommit=True
            )
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            self.connection = None
   
    def create_table(self, table_name, columns):
        if not self.connection:
            print("No database connection.")
            return
        try:
            with self.connection.cursor() as cursor:
                column_def = ", ".join([f"{col} {dtype}" for col, dtype in columns.items()])
                query = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_def})"
                cursor.execute(query)
                print(f"Table `{table_name}` checked/created.")
        except Exception as e:
            print(f"Failed to create table '{table_name}': {e}")
    
    def delete_table(self, table_name):
        if not self.connection:
            print("No database connection.")
            return
        try:
            with self.connection.cursor() as cursor:
                query = f"DROP TABLE IF EXISTS {table_name}"
                cursor.execute(query)
                print(f"Table `{table_name}` deleted if it existed.")
        except Exception as e:
            print(f"Failed to delete table '{table_name}': {e}")

    def insert_item(self, table_name, data):
        if not self.connection:
            print("No database connection.")
            return
        try:
            with self.connection.cursor() as cursor:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["%s"] * len(data))
                values = list(data.values())
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                cursor.execute(query, values)
                print("Data inserted successfully.")
        except Exception as e:
            print(f"Insert failed for table '{table_name}': {e}")
 
    def get_tables(self):
        if not self.connection:
            print("No database connection.")
            return []
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                result = cursor.fetchall()
                tables = [list(row.values())[0] for row in result]
                return tables
        except Exception as e:
            print(f"Failed to get tables: {e}")
            return []
 
    def select_items(self, table_name, columns="*", where=None):
        if not self.connection:
            print("No database connection.")
            return []
        try:
            if isinstance(columns, list):
                columns = ", ".join(columns)
 
            query = f"SELECT {columns} FROM {table_name}"
            if where:
                query += f" WHERE {where}"
 
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                return result
        except Exception as e:
            print(f"Failed to select items from '{table_name}': {e}")
            return []
 
    def close(self):
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                print(f"Failed to close connection: {e}")
        else:
            print("No database connection to close.")

def test_rds_connection(host, port=3306, timeout=5):
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except Exception as e:
        return str(e)
    
def get_credentials_from_secrets(secret_name, region_name="ap-south-1"):
 
    try:
        client = boto3.client('secretsmanager', region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
 
        if 'SecretString' in response:
            secret = json.loads(response['SecretString'])
            return {
                "host": secret.get("host"),
                "port": int(secret.get("port", 3306)),
                "user": secret.get("username"),
                "password": secret.get("password"),
                "db": secret.get("dbname")
            }
        else:
            raise ValueError("SecretBinary not supported in this function")
 
    except Exception as e:
        print(f"Error retrieving secret - ': {str(e)}")

def lambda_handler(event, context):
    secret_name = os.environ['SECRET_NAME']
    region_name = os.environ.get('AWS_REGION', 'ap-south-1')

    # Get DB credentials from Secrets Manager
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)
    secret = json.loads(client.get_secret_value(SecretId=secret_name)['SecretString'])

    host = os.environ['DB_HOST']
    user = secret['username']
    password = secret['password']
    database = os.environ['DB_NAME']

    # Test if RDS is reachable
    connectivity_check = test_rds_connection(host)
    if connectivity_check is not True:
        return {"status": "Error", "message": f"Cannot reach RDS: {connectivity_check}"}

    # Connect to MySQL
    try:

        mysql_helper = MySQLHelper(
            host=host,
            user=user,
            password=password,
            db=database,
            port=3306
        )

        mysql_helper.create_table(CUSTOMERS_TABLE, {
            "customer_id": "INT PRIMARY KEY",
            "name": "VARCHAR(100)",
            "email": "VARCHAR(100)",
            "phone": "VARCHAR(20)"
        })
 
        mysql_helper.create_table(ACCOUNT_TABLE, {
            "account_id": "INT PRIMARY KEY",
            "customer_id": "INT",
            "account_type": "VARCHAR(50)",
            "balance": "DECIMAL(15, 2)"
        })
 
        mysql_helper.create_table(TRANSACTIONS_TABLE, {
            "transaction_id": "INT PRIMARY KEY",
            "account_id": "INT",
            "amount": "DECIMAL(15, 2)",
            "description": "VARCHAR(255)"
        })
 
        # Insert data
        for customer in CUSTOMERS:
            mysql_helper.insert_item(CUSTOMERS_TABLE, customer)
 
        for account in ACCOUNTS:
            mysql_helper.insert_item(ACCOUNT_TABLE, account)
 
        for transaction in TRANSACTIONS:
            mysql_helper.insert_item(TRANSACTIONS_TABLE, transaction)


        return {
            "status": "Success",
            "message": "Tables created successfully",
        }

    except Exception as e:
        return {"status": "Error", "message": str(e)}
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()





