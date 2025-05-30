import boto3
import pymysql
import os
import json
from pymysql.cursors import DictCursor

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

ACCOUNT_TABLE= "Accounts"
TRANSACTIONS_TABLE = "Transactions"
CUSTOMERS_TABLE = "Customers"

def lambda_handler(event, context):

    
    headers = {
        "Access-Control-Allow-Origin": "http://my-ui-bucket-anushka-1610.s3-website.ap-south-1.amazonaws.com",
        "Access-Control-Allow-Headers": "*"
    }

    customer_id = event['pathParameters'].get('customerId')
    if customer_id is not None:
        customer_id = int(customer_id)
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'status': 'error', 'message': 'customerId path parameter missing'})
        }
    secret_name = os.environ['SECRET_NAME']
    db_name = os.environ['DB_NAME']
    region_name = os.environ.get('AWS_REGION', 'ap-south-1')

    client = boto3.client('secretsmanager', region_name=region_name)
    secret = json.loads(client.get_secret_value(SecretId=secret_name)['SecretString'])

    
    print(secret, os.environ['DB_HOST'], db_name)
    try:
        mysqlhelper = MySQLHelper(
            host=os.environ['DB_HOST'],
            user=secret['username'],
            password=secret['password'],
            db=db_name,
            port = 3306
        )
        accounts = mysqlhelper.select_items(ACCOUNT_TABLE, where=f"customer_id = {customer_id}")
        print(f"Accounts for customer_id {customer_id}:", accounts)
        account_ids = [str(acc['account_id']) for acc in accounts]
        print(f"Account IDs found: {account_ids}")


        
        print(f"Querying accounts for customer_id {customer_id}")

        query = """
            SELECT 
                COUNT(*) AS transaction_count,
                IFNULL(SUM(t.amount), 0) AS total_amount
            FROM Transactions t
            INNER JOIN Accounts a ON t.account_id = a.account_id
            WHERE a.customer_id = %s
        """
        with mysqlhelper.connection.cursor() as cursor:
            cursor.execute(query, (customer_id,))
            result = cursor.fetchall()

        print("Query Result:", result)

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'status': "ok", 'data': result}, default=str)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'status': "error", 'message': "Something went wrong"}, default=str)
        }





