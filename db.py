import credentials

import pymysql


db_connection = None


def db():
    global db_connection
    assert db_connection is not None
    return db_connection


def db_init():
    global db_connection
    db_connection = pymysql.connect(credentials.DB_HOST, credentials.DB_USER, credentials.DB_PASSWORD, credentials.DB_NAME,
                    cursorclass=pymysql.cursors.DictCursor)
