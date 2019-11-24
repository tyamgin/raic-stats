import credentials

import pymysql

db_connection = None


def db():
    global db_connection
    if not db_connection:
        db_connection = pymysql.connect(credentials.DB_HOST, credentials.DB_USER, credentials.DB_PASSWORD, credentials.DB_NAME,
                                        cursorclass=pymysql.cursors.DictCursor)
    return db_connection
