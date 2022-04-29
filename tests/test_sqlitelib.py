import sys
import pytest
import os.path
from os import getcwd
from datetime import date, timedelta

sys.path.append('..')
import sqlitelib
import rsslib

@pytest.fixture()
def test_db():
    curs, conn = sqlitelib.create_DB(':memory:')
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
        'my exile.', 'None')
    sqlitelib.write_post(newpost, curs, conn)
    postdate = (date.today() - timedelta(days=14)).isoformat() # 14 days ago from current day
    newpost = rsslib.Post(2, 'http://new-sun.gov', 'Chapter 1 - On Symbols',
        'Gene Wolfe', 'http://order-of-seekers.gov', postdate,
        'We believe that we invent symbols. The truth is that they invent us; we '
        'are their creatures, shaped by their hard, defining edges. ', 'None')
    sqlitelib.write_post(newpost, curs, conn)
    yield curs, conn
    conn.close()

def test_db_create(test_db):
    curs, conn = test_db
    assert str(type(curs)) == "<class 'sqlite3.Cursor'>"
    assert str(type(conn)) == "<class 'sqlite3.Connection'>"

def test_repeated_feed_write_ignored(test_db):
    curs, conn = test_db
    newfeed = rsslib.Feed('http://new-sun.gov', 'New Sun', 'Main Folder', 'rss',
                          'http://new-sun.gov/rss', 'http://new-sun.gov', None,
                          0, None)
    sqlitelib.write_feed(newfeed, curs, conn)
    assert len(list(curs.execute('SELECT * FROM `feeds`'))) == 1

def test_repeated_post_write_ignored(test_db):
    curs, conn = test_db
    postdate = (date.today() - timedelta(days=14)).isoformat() # 14 days ago from current day
    newpost = rsslib.Post(2, 'http://new-sun.gov', 'Chapter 1 - On Symbols',
        'Gene Wolfe', 'http://order-of-seekers.gov', postdate,
        'We believe that we invent symbols. The truth is that they invent us; we '
        'are their creatures, shaped by their hard, defining edges. ', None)
    sqlitelib.write_post(newpost, curs, conn)
    assert len(list(curs.execute('SELECT * FROM `posts`'))) == 2

def test_get_feed_posts(test_db):
    curs, conn = test_db
    assert len(sqlitelib.get_feed_posts('random_text', curs, conn)) == 0
    assert len(sqlitelib.get_feed_posts('http://new-sun.gov', curs, conn)) == 2

def test_count_unread_posts(test_db):
    curs, conn = test_db
    assert sqlitelib.count_all_unread(curs, conn) == {'http://new-sun.gov': 2}
    sqlitelib.mark_feed_read('http://new-sun.gov', curs, conn)
    assert sqlitelib.count_all_unread(curs, conn) == {}

def test_mark_old_posts_read(test_db):
    curs, conn = test_db
    assert sqlitelib.count_all_unread(curs, conn) == {'http://new-sun.gov': 2}
    sqlitelib.mark_old_as_read(30, curs, conn)
    assert sqlitelib.count_all_unread(curs, conn) == {'http://new-sun.gov': 1}
    sqlitelib.mark_old_as_read(3, curs, conn)
    assert sqlitelib.count_all_unread(curs, conn) == {}

def test_find_date_last_read(test_db):
    curs, conn = test_db
    assert sqlitelib.find_date_last_read('http://new-sun.gov', curs, conn) == None

def test_find_date_all_feeds_last_read(test_db):
    curs, conn = test_db
    assert sqlitelib.find_date_all_feeds_last_read(curs, conn) == {}

def test_count_unread_posts(test_db):
    curs, conn = test_db
    assert sqlitelib.count_filtered_unread('New', curs, conn) == {'http://new-sun.gov': 2}
    sqlitelib.mark_feed_read('http://new-sun.gov', curs, conn)
    assert sqlitelib.count_all_unread(curs, conn) == {}

def test_get_most_recent(test_db):
    curs, conn = test_db
    assert len(sqlitelib.get_most_recent(1, curs, conn)) == 1
    assert len(sqlitelib.get_most_recent(2, curs, conn)) == 2

def test_count_filtered_unread(test_db):
    curs, conn = test_db
    assert len(sqlitelib.count_filtered_unread('Random', curs, conn)) == 0
    assert len(sqlitelib.count_filtered_unread('New Sun', curs, conn)) == 1

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

def test_text_search_by_feed_id(test_db):
    curs, conn = test_db
    assert len(sqlitelib.text_search('symbol', curs, conn, None, None, 'random')) == 0
    assert len(sqlitelib.text_search('symbol', curs, conn, None, None,
                                     'http://new-sun.gov')) == 2

@pytest.mark.parametrize('date, expected', [('week', 0), ('month', 1),
                                             ('year', 2)])
def test_text_search_date(test_db, date, expected):
    curs, conn = test_db
    assert len(sqlitelib.text_search('symbol', curs, conn, None, date)) == expected

def test_retrieve_feed_list(test_db):
    curs, conn = test_db
    assert len(sqlitelib.retrieve_feedlist(curs, conn)) == 1

def test_delete_feed(test_db):
    curs, conn = test_db
    assert len(sqlitelib.retrieve_feedlist(curs, conn)) == 1
    delfeed = rsslib.Feed('http://new-sun.gov', 'New Sun', 'Main Folder', 'rss',
                          'http://new-sun.gov/rss', 'http://new-sun.gov', None,
                          0, None)
    sqlitelib.delete_feed(delfeed, curs, conn)
    assert len(sqlitelib.retrieve_feedlist(curs, conn)) == 0
    assert sqlitelib.count_all_unread(curs, conn) == {}

def test_delete_all_but_last_n(test_db):
    curs, conn = test_db
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 2
    sqlitelib.delete_all_but_last_n('http://new-sun.gov', 1, curs, conn)
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 1
    sqlitelib.delete_all_but_last_n('http://new-sun.gov', 0, curs, conn)
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 0

def test_mass_delete_all_but_last_n(test_db):
    curs, conn = test_db
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 2
    sqlitelib.mass_delete_all_but_last_n(1, curs, conn)
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 1
    sqlitelib.mass_delete_all_but_last_n(0, curs, conn)
    assert sqlitelib.count_posts('http://new-sun.gov', curs, conn) == 0

def test_list_feeds_over_post_count(test_db):
    curs, conn = test_db
    assert sqlitelib.list_feeds_over_post_count(1, curs, conn) == ['http://new-sun.gov']
    assert sqlitelib.list_feeds_over_post_count(2, curs, conn) == []

def test_list_feeds_under_post_count(test_db):
    curs, conn = test_db
    assert sqlitelib.list_feeds_under_post_count(5, curs, conn) == ['http://new-sun.gov']
    assert sqlitelib.list_feeds_under_post_count(5, curs, conn, True) == {'New Sun': 2}
    assert sqlitelib.list_feeds_under_post_count(2, curs, conn) == []
    assert sqlitelib.list_feeds_under_post_count(2, curs, conn, True) == {}

def test_find_dead_feeds(test_db):
    curs, conn = test_db
    sqlitelib.delete_all_but_last_n('http://new-sun.gov', 0, curs, conn)
    assert sqlitelib.find_dead_feeds(curs, conn) == {'http://new-sun.gov':'New Sun'}

def test_find_inactive_feeds(test_db):
    curs, conn = test_db
    curr_year = date.today().year
    assert sqlitelib.find_inactive_feeds(curr_year, curs, conn) == {}
    inactive_feed = rsslib.Feed('http://inactive.com', 'Inactive', 'Main Folder', 'rss',
                          'http://inactive.com/rss', 'http://inactive.com', None,
                          0, None)
    sqlitelib.write_feed(inactive_feed, curs, conn)
    oldpost = rsslib.Post(3, 'http://inactive.com', 'Very Old Post',
        'Author', 'http://inactive.com', '2020-08-05T12:54:00.006000-07:00',
        'Old post', 'None')
    sqlitelib.write_post(oldpost, curs, conn)

    assert len(list(curs.execute('SELECT * FROM `posts`'))) == 3
    assert sqlitelib.find_inactive_feeds(2021, curs, conn) ==\
        {'http://inactive.com': ('Inactive', '2020-08-05T12:54:00.006000-07:00')}
    assert sqlitelib.find_inactive_feeds(2020, curs, conn) == {}

def test_usage_report(test_db):
    curs, conn = test_db
    calc_str = ('It is possible I already had some presentiment of my future. The locked '
        'and rusted gate that stood before us, with wisps of river fog threading '
        'its spikes like the mountain paths, remains in my mind now as the symbol of '
        'my exile.' + 'We believe that we invent symbols. The truth is that they '
        'invent us; we are their creatures, shaped by their hard, defining edges. ')
    cont_len = len(calc_str)
    usage = sqlitelib.usage_report(curs, conn)
    assert usage == {'New Sun': cont_len}

def test_update_feed_folder(test_db):
    curs, conn = test_db
    new_folder = 'New Folder Name'
    assert sqlitelib.update_feed_folder('http://new-sun.gov', '', curs, conn) == False
    assert sqlitelib.update_feed_folder('http://new-sun.gov', new_folder, curs, conn) == True
    fl = sqlitelib.retrieve_feedlist(curs, conn)
    assert fl[0].folder == new_folder

    new_folder = 127
    assert sqlitelib.update_feed_folder('http://new-sun.gov', new_folder, curs, conn) == True
    fl = sqlitelib.retrieve_feedlist(curs, conn)
    assert fl[0].folder == str(new_folder)
