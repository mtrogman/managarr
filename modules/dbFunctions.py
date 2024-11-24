# modules/dbFunctions.py

import mysql.connector, logging, re
from datetime import datetime
from modules import configFunctions


config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)

db_config = {
    'host': config['database']['host'],
    'database': config['database']['database'],
    'user': config['database']['user'],
    'password': config['database']['password'],
    'port': config['database']['port']
}

def create_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            return connection
    except mysql.connector.Error as e:
        logging.error(f"Error connecting to the database: {e}")
        return None

def create_user(information):
    try:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()

        # Extract information from the input dictionary
        primary_email = information.get('primaryEmail', '')
        primary_discord = information.get('primaryDiscord', '')
        primary_discord_id = information.get('primaryDiscordId', '')
        payment_method = information.get('paymentMethod', '')
        payment_person = information.get('paymentPerson', '')
        paid_amount = information.get('paidAmount', '')
        server = information.get('server', '')
        is_4k = information.get('4k', '')
        status = "Active"
        start_date = information.get('startDate', '')
        join_date = start_date
        end_date = information.get('endDate', '')

        # SQL query to insert a new user into the database
        insert_query = """
        INSERT INTO users (primaryEmail, primaryDiscord, primaryDiscordId, paymentMethod, paymentPerson, paidAmount, server, 4k, status, joinDate, startDate, endDate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (primary_email, primary_discord, primary_discord_id, payment_method, payment_person, paid_amount, server, is_4k, status, join_date, start_date, end_date))

        # Commit the changes
        connection.commit()
        logging.info(f"Created new user with primary email: {primary_email}")
    except mysql.connector.Error as e:
        logging.error(f"Error creating user: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def find_user(search_term):
    search_term = search_term.lower()
    columns = ['primaryEmail', 'secondaryEmail', 'primaryDiscord', 'secondaryDiscord', 'paymentPerson']
    matching_rows_list = []
    email_regex = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'

    for column in columns:
        try:
            connection = create_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                is_email_field = re.search(email_regex, column.lower())
                if is_email_field:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s AND {column} REGEXP %s"
                    cursor.execute(query, ('%' + search_term + '%', email_regex))
                else:
                    query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s"
                    cursor.execute(query, ('%' + search_term + '%',))
                matching_rows = cursor.fetchall()
                for row in matching_rows:
                    if row not in matching_rows_list:
                        matching_rows_list.append(row)
        except mysql.connector.Error as e:
            logging.error(f"Error searching for users: {e}")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

    return matching_rows_list


def update_database(user_id, field, value):
    try:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()

            # SQL query to update the specified field for the given user ID
            update_query = f"UPDATE users SET {field} = %s WHERE id = %s"
            cursor.execute(update_query, (value, user_id))

            # Commit the changes
            connection.commit()
            logging.info(f"Updated {field} for user ID {user_id} to {value}")
    except mysql.connector.Error as e:
        logging.error(f"Error updating database: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def log_transaction(information):
    try:
        connection = create_connection()
        if connection:
            cursor = connection.cursor()

            # Loop through each user in the information's "users" list
            for user in information.get('users', []):
                # Extract data for each user
                description = information.get('what', 'Transaction')  # General description
                entity_id = user.get('primaryEmail', 'general_cost')  # Email or 'general_cost'
                amount = user.get('newPaidAmount', 0.00)  # Payment amount
                payment_method = user.get('paymentMethod', 'Unknown')  # Payment method
                if description == "payment":
                    term_length = str(user.get('term_length', "")) + " Months"
                    notes = f"Server: {user.get('server')} | Length: {term_length}"

                # SQL query to insert a new transaction
                insert_query = """
                INSERT INTO transactions (description, entity_id, amount, payment_method, notes)
                VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (description, entity_id, amount, payment_method, notes))

                # Log success for each user
                logging.info(f"Logged transaction for {entity_id} with amount: {amount}")

            # Commit all changes after the loop
            connection.commit()
    except mysql.connector.Error as e:
        logging.error(f"Error logging transactions: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

