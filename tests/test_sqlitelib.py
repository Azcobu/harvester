import sys
import pytest
import os.path
from os import getcwd
from datetime import date, timedelta

sys.path.append('..')
import sqlitelib
import rsslib

@pytest.fixture(scope='session')
def test_db():
    test_db = os.path.join(getcwd(), 'test.db')
    curs, conn = sqlitelib.connect_DB(test_db)
    newfeed = rsslib.Feed('http://new-sun.gov', 'New Sun', 'Main Folder', 'rss',
                          'http://new-sun.gov/rss', 'http://new-sun.gov', None,
                          0, None)
    sqlitelib.write_feed(newfeed, curs, conn)
    postdate = f'{date.today().year}-01-01'
    newpost = rsslib.Post(1, 'http://new-sun.gov', 'Chapter 1 - Resurrection and Death',
        'Gene Wolfe', 'http://order-of-seekers.gov', postdate,
        'It is possible I already had some presentiment of my future. The locked '
        'and rusted gate that stood before us, with wisps of river fog threading '
        'its spikes like the mountain paths, remains in my mind now as the symbol of '
        'my exile.', None)
    sqlitelib.write_post(newpost, curs, conn)
    postdate = (date.today() - timedelta(days=14)).isoformat() # 14 days ago from current day
    newpost = rsslib.Post(2, 'http://new-sun.gov', 'Chapter 1 - On Symbols',
        'Gene Wolfe', 'http://order-of-seekers.gov', postdate,
        'We believe that we invent symbols. The truth is that they invent us; we '
        'are their creatures, shaped by their hard, defining edges. ', None)
    sqlitelib.write_post(newpost, curs, conn)
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

# def test_write_post_list
# def test_write_feed_list

def test_get_feed_posts(test_db):
    curs, conn = test_db
    assert len(sqlitelib.get_feed_posts('random_text', curs, conn)) == 0
    assert len(sqlitelib.get_feed_posts('http://new-sun.gov', curs, conn)) == 2

def test_count_all_unread(test_db):
    curs, conn = test_db
    assert len(sqlitelib.count_all_unread(curs, conn)) == 1

'''
def test_count_filtered_unread(test_db):
    curs, conn = test_db
    assert len(sqlitelib.count_filtered_unread('Random', curs, conn)) == 0
    assert len(sqlitelib.count_filtered_unread('New Sun', curs, conn)) == 1
'''

@pytest.mark.parametrize("instr, expected", [('day', 1), ('week', 7), ('month', 31),
                          ('year', 365), (None, 99999), ('random_text', 99999)])
def test_initial_numbers(instr, expected):
    assert sqlitelib.calc_limit_date(instr) == expected


@pytest.mark.parametrize('instr, expected', [('random_text', 0), ('exile', 1),
                                             ('symbol', 2)])
def test_text_search(test_db, instr, expected):
    curs, conn = test_db
    assert len(sqlitelib.text_search(instr, curs, conn)) == expected

def test_text_search_limit(test_db):
    curs, conn = test_db
    assert len(sqlitelib.text_search('symbol', curs, conn, 1)) == 1
    assert len(sqlitelib.text_search('symbol', curs, conn, 2)) == 2

@pytest.mark.parametrize('date, expected', [('week', 0), ('month', 1),
                                             ('year', 2)])
def test_text_search_date(test_db, date, expected):
    curs, conn = test_db
    assert len(sqlitelib.text_search('symbol', curs, conn, None, date)) == expected
