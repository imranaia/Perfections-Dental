# =========================================
# Perfections Dental Services
# SQLite connection helper — replaces the old pymysql/MySQL data layer.
# =========================================

import os
import sqlite3
import datetime as _dt

from config import Config

_SCHEMA_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'database', 'schema.sql')


def _dict_row_factory(cursor, row):
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row))


# The old pymysql/MySQL code was written expecting DATE/DATETIME columns to
# come back as native datetime.date/datetime.datetime objects (it calls
# .strftime(), .year, .month on them directly). SQLite's Python driver
# doesn't do this unless converters are registered for the declared column
# type — schema.sql declares those columns DATE/DATETIME precisely so this
# kicks in for direct column references. (Aggregates/subquery expressions
# lose the decltype and still come back as plain strings — a known,
# narrower limitation left for the query-by-query reconciliation pass.)
def _convert_date(raw):
    return _dt.date.fromisoformat(raw.decode())


def _convert_datetime(raw):
    s = raw.decode().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return s


sqlite3.register_converter('DATE', _convert_date)
sqlite3.register_converter('DATETIME', _convert_datetime)
sqlite3.register_converter('TIMESTAMP', _convert_datetime)


class _Cursor(sqlite3.Cursor):
    """sqlite3.Cursor doesn't support `with db.cursor() as cursor:` — the
    whole codebase is written that way (matching pymysql's DictCursor
    context-manager usage), so make our cursor a context manager too."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class _Connection(sqlite3.Connection):
    def cursor(self, factory=_Cursor):
        return super().cursor(factory)


def get_db():
    """Return a new SQLite connection whose rows behave like the DictCursor
    rows the codebase was written against (plain dicts, support .get())."""
    conn = sqlite3.connect(Config.DB_PATH, factory=_Connection,
                           detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = _dict_row_factory
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def init_db():
    """Create the schema if the database file doesn't exist yet."""
    is_new = not os.path.exists(Config.DB_PATH)
    conn = get_db()
    with open(_SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    return is_new
