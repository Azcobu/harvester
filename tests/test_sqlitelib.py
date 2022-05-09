from datetime import date, timedelta
from dataclasses import dataclass
import sys
import sqlite3
import pytest

sys.path.append("..")
import sqlitelib
import rsslib

@dataclass
class DB_Data:
    curs: sqlite3.Cursor
    conn: sqlite3.Connection

@pytest.fixture()
def db():
    test_db = DB_Data(*sqlitelib.create_DB(":memory:"))
    newfeed = rsslib.Feed("http://new-sun.gov", "New Sun", "Main Folder",
                          "rss", "http://new-sun.gov/rss", "http://new-sun.gov",
                          None, "1970-01-01T00:00:00+00:00", None)
    sqlitelib.write_feed(newfeed, test_db.curs, test_db.conn)
    postdate = f"{date.today().year}-01-01"
    newpost = rsslib.Post(1, "http://new-sun.gov", "Chapter 1 - Resurrection and Death",
        "Gene Wolfe", "http://order-of-seekers.gov", postdate,
        "It is possible I already had some presentiment of my future. The locked "
        "and rusted gate that stood before us, with wisps of river fog threading "
        "its spikes like the mountain paths, remains in my mind now as the symbol of "
        "my exile.", "None")
    sqlitelib.write_post(newpost, test_db.curs, test_db.conn)
    postdate = (date.today() - timedelta(days=14)).isoformat()  # 14 days ago from current day
    newpost = rsslib.Post(2, "http://new-sun.gov", "Chapter 1 - On Symbols",
        "Gene Wolfe", "http://order-of-seekers.gov", postdate,
        "We believe that we invent symbols. The truth is that they invent us; we "
        "are their creatures, shaped by their hard, defining edges.", "None")
    sqlitelib.write_post(newpost, test_db.curs, test_db.conn)
    yield test_db
    test_db.conn.close()

def test_db_create(db):
    assert isinstance(db.curs, sqlite3.Cursor)
    assert isinstance(db.conn, sqlite3.Connection)

def test_repeated_feed_write_ignored(db):
    newfeed = rsslib.Feed("http://new-sun.gov", "New Sun", "Main Folder",
                          "rss", "http://new-sun.gov/rss", "http://new-sun.gov",
                          None, 0, None)
    sqlitelib.write_feed(newfeed, db.curs, db.conn)
    assert len(list(db.curs.execute("SELECT * FROM `feeds`"))) == 1

def test_repeated_post_write_ignored(db):
    postdate = (date.today() - timedelta(days=14)).isoformat()
    newpost = rsslib.Post(2, "http://new-sun.gov", "Chapter 1 - On Symbols",
                          "Gene Wolfe", "http://order-of-seekers.gov",
                          postdate, "We", None)
    sqlitelib.write_post(newpost, db.curs, db.conn)
    assert len(list(db.curs.execute("SELECT * FROM `posts`"))) == 2

def test_get_feed_posts(db):
    assert len(sqlitelib.get_feed_posts("random_text", db.curs, db.conn)) == 0
    assert len(sqlitelib.get_feed_posts("http://new-sun.gov", db.curs, db.conn)) == 2

def test_count_unread_posts(db):
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {"http://new-sun.gov": 2}
    sqlitelib.mark_feed_read("http://new-sun.gov", db.curs, db.conn)
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {}

def test_mark_old_posts_read(db):
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {"http://new-sun.gov": 2}
    sqlitelib.mark_old_as_read(30, db.curs, db.conn)
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {"http://new-sun.gov": 1}
    sqlitelib.mark_old_as_read(3, db.curs, db.conn)
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {}

def test_find_date_last_read(db):
    assert sqlitelib.find_date_last_read("http://new-sun.gov", db.curs, db.conn) == None

def test_find_date_all_feeds_last_read(db):
    assert sqlitelib.find_date_all_feeds_last_read(db.curs, db.conn) == \
        {'http://new-sun.gov': "1970-01-01T00:00:00+00:00"}

def test_count_unread_posts(db):
    assert sqlitelib.count_filtered_unread("New", db.curs, db.conn) == \
        {"http://new-sun.gov": 2}
    sqlitelib.mark_feed_read("http://new-sun.gov", db.curs, db.conn)
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {}

def test_get_most_recent(db):
    assert len(sqlitelib.get_most_recent(1, db.curs, db.conn)) == 1
    assert len(sqlitelib.get_most_recent(2, db.curs, db.conn)) == 2

def test_count_filtered_unread(db):
    assert len(sqlitelib.count_filtered_unread("Random", db.curs, db.conn)) == 0
    assert len(sqlitelib.count_filtered_unread("New Sun", db.curs, db.conn)) == 1

@pytest.mark.parametrize("instr, expected", [("day", 1), ("week", 7), ("month", 31),
                        ("year", 365), (None, 99999), ("random_text", 99999)])
def test_initial_numbers(instr, expected):
    assert sqlitelib.calc_limit_date(instr) == expected

@pytest.mark.parametrize("instr, expected", [("random_text", 0), ("exile", 1),
                        ("symbol", 2)])
def test_text_search(db, instr, expected):
    assert len(sqlitelib.text_search(instr, db.curs, db.conn)) == expected

def test_text_search_limit(db):
    assert len(sqlitelib.text_search("symbol", db.curs, db.conn, 1)) == 1
    assert len(sqlitelib.text_search("symbol", db.curs, db.conn, 2)) == 2

def test_text_search_by_feed_id(db):
    assert len(sqlitelib.text_search("symbol", db.curs, db.conn, None, None,
                                     "random")) == 0
    assert len(sqlitelib.text_search("symbol", db.curs, db.conn, None, None,
                                     "http://new-sun.gov")) == 2

@pytest.mark.parametrize("date, expected", [("week", 0), ("month", 1), ("year", 2)])
def test_text_search_date(db, date, expected):
    assert len(sqlitelib.text_search("symbol", db.curs, db.conn, None, date)) == expected

def test_retrieve_feed_list(db):
    assert len(sqlitelib.retrieve_feedlist(db.curs, db.conn)) == 1

def test_delete_feed(db):
    assert len(sqlitelib.retrieve_feedlist(db.curs, db.conn)) == 1
    delfeed = rsslib.Feed("http://new-sun.gov", "New Sun", "Main Folder",
                          "rss", "http://new-sun.gov/rss", "http://new-sun.gov",
                          None, 0, None)
    sqlitelib.delete_feed(delfeed, db.curs, db.conn)
    assert len(sqlitelib.retrieve_feedlist(db.curs, db.conn)) == 0
    assert sqlitelib.count_all_unread(db.curs, db.conn) == {}

def test_delete_all_but_last_n(db):
    assert sqlitelib.count_posts("http://new-sun.gov", db.curs, db.conn) == 2
    sqlitelib.delete_all_but_last_n("http://new-sun.gov", 1, db.curs, db.conn)
    assert sqlitelib.count_posts("http://new-sun.gov", db.curs, db.conn) == 1
    sqlitelib.delete_all_but_last_n("http://new-sun.gov", 0, db.curs, db.conn)
    assert sqlitelib.count_posts("http://new-sun.gov", db.curs, db.conn) == 0

def test_mass_delete_all_but_last_n(db):
    assert sqlitelib.list_feeds_under_post_count(5, db.curs, db.conn) ==\
        ["http://new-sun.gov"]
    assert sqlitelib.list_feeds_under_post_count(5, db.curs, db.conn, True) ==\
        {"New Sun": 2}
    assert sqlitelib.list_feeds_under_post_count(2, db.curs, db.conn) == []
    assert sqlitelib.list_feeds_under_post_count(2, db.curs, db.conn, True) == {}

def test_find_dead_feeds(db):
    sqlitelib.delete_all_but_last_n("http://new-sun.gov", 0, db.curs, db.conn)
    assert sqlitelib.find_dead_feeds(db.curs, db.conn) ==\
        {"http://new-sun.gov": "New Sun"}

def test_find_inactive_feeds(db):
    curr_year = date.today().year
    assert sqlitelib.find_inactive_feeds(curr_year, db.curs, db.conn) == {}
    inactive_feed = rsslib.Feed("http://inactive.com", "Inactive", "Main Folder",
                                "rss", "http://inactive.com/rss", "http://inactive.com",
                                None, 0, None)
    sqlitelib.write_feed(inactive_feed, db.curs, db.conn)
    oldpost = rsslib.Post(3, "http://inactive.com", "Very Old Post", "Author",
                          "http://inactive.com", "2020-08-05T12:54:00.006000-07:00",
                          "Old post", "None")
    sqlitelib.write_post(oldpost, db.curs, db.conn)
    assert len(list(db.curs.execute("SELECT * FROM `posts`"))) == 3
    assert sqlitelib.find_inactive_feeds(2021, db.curs, db.conn) == {
        "http://inactive.com": ("Inactive", "2020-08-05T12:54:00.006000-07:00")
    }
    assert sqlitelib.find_inactive_feeds(2020, db.curs, db.conn) == {}

def test_update_feed_folder(db):
    new_folder = "New Folder Name"
    assert sqlitelib.update_feed_folder("http://new-sun.gov", "", db.curs,
                                        db.conn) == False
    assert sqlitelib.update_feed_folder("http://new-sun.gov", new_folder, db.curs,
                                        db.conn) == True
    fl = sqlitelib.retrieve_feedlist(db.curs, db.conn)
    assert fl[0].folder == new_folder
    new_folder = 127
    assert sqlitelib.update_feed_folder("http://new-sun.gov", new_folder, db.curs,
                                        db.conn) == True
    fl = sqlitelib.retrieve_feedlist(db.curs, db.conn)
    assert fl[0].folder == str(new_folder)

def test_usage_report(db):
    strlen = sum(len(x.content) for x in sqlitelib.get_feed_posts("http://new-sun.gov",
                 db.curs, db.conn))
    assert sqlitelib.usage_report(db.curs, db.conn) == {'New Sun': strlen}
