# modules/dbFunctions.py

import mysql.connector
import yaml
import logging


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