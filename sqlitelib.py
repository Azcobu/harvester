# SQLite testbed
# iplement article storage, deletion, searching
# DB fields - ID, site, author, date, text
# folder?
# How to handle apostrophes, etc in text?

import sqlite3
import rsslib
from datetime import datetime, timezone, date, timedelta
from os import path

'''
class Post:
    def __init__(self, post_id, site, author, date, text, flags):
        self.post_id = post_id
        self.site = site
        self.author = author
        self.date = date
        self.text = text
        self.flags = flags

    def __repr__(self):
        return (f'ID: {self.post_id}, Site: {self.site}, Author: {self.author}, '
                f'Date: {self.date}, Text: {self.text}, Flags:{self.flags}')
'''

def connect_DB(db_file):
    if not db_file or not path.exists(db_file):
        return None

    try:
        conn = sqlite3.connect(db_file)
    except Exception as err:
        print(f'Error connecting to DB file {db_file}: {err}')
        return None
    curs = conn.cursor()
    return curs, conn

def create_DB(filename):
    conn = sqlite3.connect(filename)
    c = conn.cursor()

    try:
        # Create table
        c.execute(
        '''CREATE TABLE feeds (
            id        text primary key,
            title     text,
            folder    text,
            type      text,
            rss_url   text,
            html_url  text,
            tags      text,
            last_read text,
            favicon   blob
            )
        ''')
        # most fields are self explanatory, but flags = None/0 for unread posts, and 1 for read
        c.execute(
        '''CREATE TABLE posts (
            id      text primary key,
            feed_id text,
            title   text,
            author  text,
            url     text,
            date    text,
            content text,
            flags   text
            )
        ''')
        c.execute("CREATE INDEX post_dates ON posts (date);")
        c.execute("CREATE INDEX post_feed_ids ON posts (feed_id);")
        c.execute("CREATE INDEX post_flags ON posts (flags);")
        conn.commit()
        conn.close()
        return True
    except Exception as err:
        print(f'Error creating DB {filename} - {err}')
        return False

def calc_limit_date(instr):
    timediffs = {'day':1, 'week':7, 'month':31, 'year':365}
    for k, v in timediffs.items():
        if k in instr:
            #return (date.today() - timedelta(days=v)).isoformat()
            return v
    else:
        return 999999

def text_search(srchtext, limit=None, curs=None, conn=None, datelimit=None):
    # search scores?
    # search for multiple terms?

    datelimit = calc_limit_date(datelimit)
    #  `date` < date("now", "-{numdays} day")'

    try:
        curs.execute(f'SELECT * FROM posts WHERE `content` LIKE "%{srchtext}%" '
                     f'AND `date` >= date("now", "-{datelimit} day") '
                     f'ORDER BY `date` DESC LIMIT {limit}')
    except Exception as err:
        print(f'Error: {err}')
    else:
        results = curs.fetchall()

    return convert_results_to_postlist(results)

def get_data(curs, conn):
    curs.execute('SELECT * FROM posts')
    msgs = curs.fetchall()

    for m in msgs:
        newmsg = Post(*m)
        print(newmsg)

def write_post(post, curs=None, conn=None):
    # id, feed_id, title, author, url, date, content, flags

    if not curs:
        curs, conn = connect_DB(filename)

    inpost = post.p_id, post.feed_id, post.title, post.author, post.url, post.date, post.content, 'None'

    #inpost = 'idtext', 'feedidtext', 'titletext', 'authortext', 'urltext', 'datetext', 'contenttext', 'flags'

    curs.execute("INSERT OR IGNORE INTO posts ('id', 'feed_id', 'title', 'author',\
                 'url', 'date', 'content', 'flags') "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", inpost)
    conn.commit()
    conn.close()

def write_post_list(postlist, curs=None, conn=None):
    postssql = []

    if not curs:
        curs, conn = connect_DB(db_file)

    for post in postlist:
        inpost = post.p_id, post.feed_id, post.title, post.author, post.url, post.date, post.content, 'None'
        postssql.append(inpost)

    curs.executemany("INSERT OR IGNORE INTO posts ('id', 'feed_id', 'title', 'author',\
                     'url', 'date', 'content', 'flags') "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", postssql)
    conn.commit()

def write_feed(feed, curs=None, conn=None):
    if not curs:
        curs, conn = connect_DB(filename)

    infeed = feed.feed_id, feed.title, feed.folder, feed.f_type, feed.rss_url,\
                 feed.html_url, str(feed.tags), feed.last_read #, feed.favicon

    curs.execute("INSERT OR IGNORE INTO feeds "\
                 "('id', 'title', 'folder','type', 'rss_url', 'html_url', 'tags', 'last_read') "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ",\
                 (feed.feed_id, feed.title, feed.folder, feed.f_type, feed.rss_url,\
                 feed.html_url, str(feed.tags), feed.last_read))
    conn.commit()

def write_feed_list(db_file, feedlist, curs=None, conn=None):
    feedsql = []

    if not curs:
        curs, conn = connect_DB(db_file)

    for feed in feedlist:
        print(f'{feed}')
        infeed = feed.feed_id, feed.title, feed.folder, feed.f_type, feed.rss_url,\
                 feed.html_url, str(feed.tags), feed.last_read #, feed.favicon
        feedsql.append(infeed)

    print([x for x in feedsql if 'Register' in x[1]])

    curs.executemany("INSERT OR IGNORE INTO feeds ('id', 'title', 'folder',\
                     'type', 'rss_url', 'html_url', 'tags', 'last_read') "
                     #, 'favicon') "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", feedsql)
    conn.commit()

def get_feed_posts(feed_id, curs=None, conn=None):
    try:
        query = f'SELECT * FROM `posts` WHERE `feed_id` = "{feed_id}" ORDER BY `date` DESC;'
        curs.execute(query)
        results = curs.fetchall()
        return convert_results_to_postlist(results)
    except Exception as err:
        print(f'Error retrieving posts for {feed_id} - {err}')

def get_folder_posts(folder, curs=None, conn=None):
    try:
        query = f'SELECT * FROM `posts` WHERE `folder` = "{folder}" ORDER BY `date` DESC;'
        curs.execute(query)
        results = curs.fetchall()
        return convert_results_to_postlist(results)
    except Exception as err:
        print(f'Error retrieving posts for {feed_id} - {err}')

def count_all_unread(curs=None, conn=None):
    try:
        query = ("SELECT p.feed_id, COUNT(*) FROM `posts` p WHERE p.flags = 'None' GROUP BY p.feed_id;")
        curs.execute(query)
        k =  {x[0]:x[1] for x in curs.fetchall()}
        return k
    except Exception as err:
        print(f'Error counting unread posts for feeds - {err}')

def count_filtered_unread(feed_str, curs=None, conn=None):
    # returns unread count for feeds with title matching search string
    # note matching feeds with 0 unread are not returned
    try:
        query = ("SELECT p.feed_id, COUNT(*) FROM `posts` p WHERE p.feed_id IN (SELECT f.id "
	             f"FROM `feeds` f WHERE f.title LIKE '%{feed_str}%') AND p.flags = 'None' GROUP BY p.feed_id;")
        curs.execute(query)
        k =  {x[0]:x[1] for x in curs.fetchall()}
        return k
    except Exception as err:
        print(f'Error counting unread posts for feeds - {err}')

def get_most_recent(numposts, curs=None, conn=None):
    try:
        query = (f"SELECT * FROM `posts` p ORDER BY p.date DESC LIMIT {numposts};")
        curs.execute(query)
        results = curs.fetchall()
        return convert_results_to_postlist(results)
    except Exception as err:
        print(f'Error getting most recent posts - {err}')

def vacuum(conn):
    conn.execute('VACUUM')
    conn.close()
    print('DB maintenance complete.')

def mark_old_as_read(numdays, curs=None, conn=None):
    query = f'UPDATE `posts` SET `flags` = 1 WHERE `date` < date("now", "-{numdays} day")'
    #query = "SELECT * FROM `posts` WHERE `date` < date('now', '-365 day');"
    curs.execute(query)
    conn.commit()
    print(f'{curs.rowcount} posts marked as read.')

def mark_feed_read(feed_id, curs, conn):
    query = f'UPDATE `posts` SET `flags` = 1 WHERE `feed_id` = "{feed_id}" '
    curs.execute(query)
    conn.commit()
    print(f'Feed {feed_id} marked as read.')

def find_date_last_read(feed_id, curs, conn):
    query = f'SELECT `date` FROM `posts` WHERE `feed_id` = "{feed_id}" AND `flags` = 1 '\
             'ORDER BY `date` DESC LIMIT 1;'
    curs.execute(query)
    lastdate = curs.fetchone()
    if lastdate:
        print(f'Date for last read post for {feed_id} is {lastdate[0]}.')
        return lastdate[0]
    return None

def find_date_all_feeds_last_read(curs, conn):
    #generate a dict of last read post for all feeds
    query = f'SELECT feed_id, MAX(`date`) FROM `posts` WHERE `flags` = 1 GROUP BY `feed_id`;'
    curs.execute(query)
    results = {x[0]:x[1] for x in curs.fetchall()}
    return results

def convert_results_to_postlist(results):
    # converts returned SQL list into a list of Post objects
    postlist = []
    for p in results:
        try:
            newpost = rsslib.Post(*p)
        except Exception as err:
            print(f'Error converting DB result to post object - {err}')
        postlist.append(newpost)
    return postlist

def retrieve_feedlist(curs=None, conn=None):
    feedlist = []

    curs.execute('SELECT * FROM "feeds"')
    for f in curs.fetchall():
        try:
            newfeed = rsslib.Feed(*f)
        except Exception as err:
            print('Error loading feeds from DB - {err}')
        feedlist.append(newfeed)
    return feedlist

def delete_feed(feed, curs=None, conn=None):
    if not curs:
        curs, conn = connect_DB(filename)

    try:
        delquery = f'DELETE FROM `posts` WHERE `feed_id` = "{feed.feed_id}";'
        curs.execute(delquery)
        delquery = f'DELETE FROM `feeds` WHERE `id` = "{feed.feed_id}";'
        curs.execute(delquery)
        conn.commit()
    except Exception as err:
        print(f'Error deleting feed {feed} - {err}')
        return False
    else:
        print(f'Deleted feed {feed}.')
        return True

def usage_report(curs, conn, num_shown=10):
    q = 'SELECT feed_id, sum(length(content)) AS cl FROM `posts` GROUP BY feed_id ORDER BY cl DESC;'
    curs.execute(q)
    results = curs.fetchall()
    print('DB Usage Report:')
    for x in range(num_shown):
        print(f'{results[x][0]} - {results[x][1]}')

def run_arbitrary_sql(query, curs, conn):
    curs.execute(query)

def main():
    dbfile = 'd:\\tmp\\posts.db'
    curs, conn = connect_DB(dbfile)
    #create_DB()
    #get_data(curs, conn)
    #newpost = Post(2, 'The Hypogeum', 'Fathr Inire', '2021-06-08', 'Certainly it is desirable to maintain in being a movement that has proved so useful in the past, and as long as the mirrors of the caller Hethor remain unbroken, she provides it with a plausible commander.')
    #write_post(dbfile, 'vfdvdf', curs, conn)
    #text_search(curs, conn, 'text', 'of')
    #posttest = get_most_recent(5, curs, conn)
    #k = count_all_unread()
    #print(posttest)
    #mark_old_as_read(3, curs, conn)
    #vacuum(conn)
    #k = text_search('new world', 20, curs, conn)
    #  feed.feed_id, feed.title, feed.folder, feed.f_type, feed.rss_url, feed.html_url, str(feed.tags))
    #newfeed = rsslib.Feed('aaa Feed ID', 'aaa Feed title', 'folder', 'rss', 'http://whatever.com',
                           #'http://direct.com', '[]')
    #write_feed(newfeed, curs, conn)
    #feed_id = 'http://deltasdnd.blogspot.com/'
    #lrd = find_date_last_read(feed_id, curs, conn)
    #k = find_date_all_feeds_last_read(curs, conn)
    #print(k)
    #usage_report(curs, conn)
    print(count_filtered_unread('eco', curs, conn))

if __name__ == '__main__':
    main()
