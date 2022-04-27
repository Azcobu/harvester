import sys
import pytest
import os.path
from os import getcwd

sys.path.append('..')
import sqlitelib
import rsslib

@pytest.fixture()
def test_db():
    test_db = os.path.join(getcwd(), 'test.db')
    curs, conn = sqlitelib.connect_DB(test_db)
    yield curs, conn
    conn.close()

def test_db_create(test_db):
    curs, conn = test_db
    assert str(type(curs)) == "<class 'sqlite3.Cursor'>"
    assert str(type(conn)) == "<class 'sqlite3.Connection'>"


def test_write_feed(test_db):
    curs, conn = test_db
    newfeed = rsslib.Feed('http://new-sun.gov', 'New Sun', 'Main Folder', 'rss',
                          'http://new-sun.gov/rss', 'http://new-sun.gov', None,
                          0, None)
    sqlitelib.write_feed(newfeed, curs, conn)
    assert len(list(curs.execute('SELECT * FROM `feeds`'))) == 1

def test_write_post(test_db):
    curs, conn = test_db
    newpost = rsslib.Post(1, 'New Sun', 'Chapter 1 - Resurrection and Death',
        'Gene Wolfe', 'http://order-of-seekers.gov', '2022-06-08',
        'It is possible I already had some presentiment of my future. The locked '
        'and rusted gate that stood before us, with wisps of river fog threading '
        'its spikes like the mountain paths, remains in my mind now as the symbol of '
        'my exile.', None)

    sqlitelib.write_post(newpost, curs, conn)
    assert len(list(curs.execute('SELECT * FROM `posts`'))) == 1

@pytest.mark.parametrize("instr, expected", [('day', 1), ('week', 7), ('month', 31),
                          ('year', 365), (None, 99999), ('random_text', 99999)])
def test_initial_numbers(instr, expected):
    assert sqlitelib.calc_limit_date(instr) == expected
