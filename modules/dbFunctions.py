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
    import re, logging, mysql.connector
    search_term_raw = str(search_term or "").strip()
    search_term = search_term_raw.lower()

    # Recognize:
    #  • email/name/discord handle (LIKE search)
    #  • Discord mention <@123> / <@!123>
    #  • plain numeric Discord ID
    #  • explicit DB id via "id:123"
    mention_id = None
    user_id_exact = None

    m = re.match(r"\s*<@!?(\d{5,25})>\s*$", search_term_raw)
    if m:
        mention_id = m.group(1)
    if not mention_id and re.fullmatch(r"\d{5,25}", search_term_raw):
        mention_id = search_term_raw
    m2 = re.match(r"\s*id\s*:\s*(\d+)\s*$", search_term_raw, flags=re.IGNORECASE)
    if m2:
        user_id_exact = int(m2.group(1))

    # Fast path: DB user id
    try:
        if user_id_exact is not None:
            connection = create_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id_exact,))
                row = cursor.fetchone()
                cursor.close(); connection.close()
                if row:
                    return [row]
    except Exception as e:
        logging.error(f"Error searching by explicit user id {user_id_exact}: {e}")

    # Fast path: Discord ID (primary/secondary)
    try:
        if mention_id:
            connection = create_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                cursor.execute(
                    "SELECT * FROM users WHERE primaryDiscordId = %s OR secondaryDiscordId = %s",
                    (mention_id, mention_id)
                )
                row = cursor.fetchone()
                cursor.close(); connection.close()
                if row:
                    return [row]
    except Exception as e:
        logging.error(f"Error searching by discord id {mention_id}: {e}")

    # Fallback: LIKE across common identity columns (case-insensitive)
    columns = ['primaryEmail', 'secondaryEmail', 'primaryDiscord', 'secondaryDiscord', 'paymentPerson']
    matching_rows_list = []

    for column in columns:
        try:
            connection = create_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                query = f"SELECT * FROM users WHERE LOWER({column}) LIKE %s"
                cursor.execute(query, ('%' + search_term + '%',))
                for row in cursor.fetchall():
                    if row not in matching_rows_list:
                        matching_rows_list.append(row)
        except mysql.connector.Error as e:
            logging.error(f"Error searching for users: {e}")
        finally:
            try:
                if connection and connection.is_connected():
                    cursor.close()
                    connection.close()
            except Exception:
                pass

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

def log_transaction(information: dict):
    """
    Insert a transaction row.
    Expects the following keys (some optional):
      - what: "newuser" | "renew" | "move" | custom (defaults to "newuser")
      - primaryEmail (entity_id)
      - paidAmount (amount)
      - paymentMethod
      - server, 4k, termLength/term_length (for notes)
      - oldStartDate, oldEndDate (optional, for notes)
    """
    import mysql.connector, logging
    from datetime import datetime

    description = str(information.get('what') or 'newuser')
    try:
        amount = float(information.get('paidAmount') or 0.0)
    except Exception:
        amount = 0.0
    entity_id = (
        information.get('primaryEmail')
        or information.get('entity_id')
        or information.get('email')
        or ''
    )
    payment_method = information.get('paymentMethod') or ''

    # build notes
    term_len = information.get('termLength', information.get('term_length'))
    try:
        term_len = int(term_len) if term_len is not None else None
    except Exception:
        term_len = None

    notes_parts = []
    if information.get('server'):
        notes_parts.append(f"Server: {information.get('server')}")
    if information.get('4k'):
        notes_parts.append(f"4k: {information.get('4k')}")
    if term_len:
        notes_parts.append(f"Length: {term_len}")
    if information.get('oldStartDate'):
        notes_parts.append(f"OldStart: {information.get('oldStartDate')}")
    if information.get('oldEndDate'):
        notes_parts.append(f"OldEnd: {information.get('oldEndDate')}")
    notes = " | ".join(notes_parts)

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        insert_sql = (
            "INSERT INTO transactions (timestamp, description, entity_id, amount, payment_method, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        cursor.execute(
            insert_sql,
            (datetime.now(), description, entity_id, amount, payment_method, notes),
        )
        connection.commit()
        logging.info(
            f"Transaction inserted: desc={description}, entity={entity_id}, amount={amount}, pm={payment_method}, notes={notes}"
        )
    except mysql.connector.Error as e:
        logging.error(f"DB error inserting transaction: {e}")
        if connection:
            connection.rollback()
        raise
    except Exception as e:
        logging.error(f"log_transaction unexpected error: {e}")
        raise
    finally:
        try:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
        except Exception:
            pass

def get_user_by_id(user_id: int):
    """Return a single user row (dict) by primary id, or None."""
    connection = None
    cursor = None
    try:
        connection = create_connection()
        if not connection:
            logging.error("Database connection is not available.")
            return None
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        return row
    except mysql.connector.Error as e:
        logging.error(f"Error fetching user by id {user_id}: {e}")
        return None
    finally:
        try:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
        except Exception:
            pass
