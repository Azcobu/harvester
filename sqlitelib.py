# SQLite testbed
# iplement article storage, deletion, searching
# DB fields - ID, site, author, date, text
# folder?
# How to handle apostrophes, etc in text?

import sqlite3
import rsslib
from datetime import datetime, timezone, date, timedelta
from os import path

def connect_DB_file(db_file):
    if not db_file or not path.exists(db_file):
        print(f'DB file {db_file} could not be found.')
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
    curs = conn.cursor()

    try:
        # Create table
        curs.execute(
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
        curs.execute(
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
        curs.execute("CREATE INDEX post_dates ON posts (date);")
        curs.execute("CREATE INDEX post_feed_ids ON posts (feed_id);")
        curs.execute("CREATE INDEX post_flags ON posts (flags);")
        conn.commit()
        return curs, conn
    except Exception as err:
        print(f'Error creating DB {filename} - {err}')
        return False

def calc_limit_date(instr):
    timediffs = {'day':1, 'week':7, 'month':31, 'year':365}
    if instr in timediffs.keys():
        return timediffs[instr]
    return 99999

def text_search(srchtext, curs, conn, limit=None, datelimit=None, feed_id=None):
    # search scores?

    if datelimit:
        datelimit = calc_limit_date(datelimit)

    srchtext = f'%{srchtext}%'

    query = f'SELECT * FROM posts WHERE `content` LIKE ? '

    if feed_id:
        query += f'AND `feed_id` = "{feed_id}" '

    if datelimit:
        query += f'AND `date` >= date("now", "-{datelimit} day") '
    query += f'ORDER BY `date` DESC'
    if limit and limit > 0:
        query += f' LIMIT {limit} '
    try:
        curs.execute(query, (srchtext,))
    except Exception as err:
        print(f'Error: {err}. Full query was {query}')
        return None
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

    inpost = post.p_id, post.feed_id, post.title, post.author, post.url, post.date,\
             post.content, 'None'

    #inpost = 'idtext', 'feedidtext', 'titletext', 'authortext', 'urltext', 'datetext', 'contenttext', 'flags'

    curs.execute("INSERT OR IGNORE INTO posts ('id', 'feed_id', 'title', 'author',\
                 'url', 'date', 'content', 'flags') "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", inpost)
    conn.commit()

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

def write_feed_list(feedlist, curs=None, conn=None):
    feedsql = []

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

    feed_str = f'%{feed_str}%'
    try:
        query = ("SELECT p.feed_id, COUNT(*) FROM `posts` p WHERE p.feed_id IN (SELECT f.id "
	             f"FROM `feeds` f WHERE f.title LIKE ?) AND p.flags = 'None' GROUP BY p.feed_id;")
        curs.execute(query, (feed_str,))
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

def delete_all_but_last_n(feed_id, keepnum, curs, conn, verbose=True):
    query = '''DELETE FROM `posts` WHERE `feed_id` = ? AND `id` NOT IN
    (SELECT `id` FROM `posts` WHERE `feed_id` = ? ORDER BY `date` DESC LIMIT ?) '''
    try:
        curs.execute(query, (feed_id, feed_id, keepnum))
        conn.commit()
    except Exception as err:
        print(f'Error deleting past {keepnum} posts from {feed_id} - {err}')
    else:
        if verbose:
            print(f'Deleted all but last {keepnum} posts from {feed_id}.')

def mass_delete_all_but_last_n(keepnum, curs, conn):
    feedlist = list_feeds_over_post_count(keepnum, curs, conn)
    for f in feedlist:
        delete_all_but_last_n(f, keepnum, curs, conn)
    vacuum(conn)

def list_feeds_over_post_count(maxposts, curs, conn, report=False):
    q = ('SELECT f.id, f.title, COUNT(p.id) FROM `posts` p JOIN `feeds` f ON f.id = p.feed_id '
         'GROUP BY p.feed_id HAVING count(p.id) > ? ORDER BY COUNT(p.id) DESC;')
    curs.execute(q, (maxposts,))
    if report:
        return {x[1]:x[2] for x in curs.fetchall()}
    else:
        return [x[0] for x in curs.fetchall()]

def list_feeds_under_post_count(maxposts, curs, conn, report=False):
    q = ('SELECT f.id, f.title, COUNT(p.id) FROM `posts` p JOIN `feeds` f ON f.id = p.feed_id '
         'GROUP BY p.feed_id HAVING count(p.id) < ? ORDER BY COUNT(p.id) DESC;')
    curs.execute(q, (maxposts,))
    if report:
        return {x[1]:x[2] for x in curs.fetchall()}
    else:
        return [x[0] for x in curs.fetchall()]

def find_dead_feeds(curs, conn):
    q = ('SELECT f.id, f.title FROM `feeds` f WHERE f.id NOT IN '
         '(SELECT p.feed_id	FROM `posts` p GROUP BY p.feed_id);')
    curs.execute(q)
    return {x[0]:x[1] for x in curs.fetchall()}

def find_inactive_feeds(year, curs, conn):
    q = ('SELECT f.id, f.title, p.date FROM `posts` p JOIN `feeds` f ON '
         'f.id = p.feed_id GROUP BY p.feed_id HAVING DATE < ? ORDER BY p.date')
    curs.execute(q, (year,))
    return {x[0]:(x[1], x[2]) for x in curs.fetchall()}

def count_posts(feed_id, curs, conn):
    q = 'SELECT COUNT(*) FROM `posts` WHERE `feed_id` = ?'
    curs.execute(q, (feed_id,))
    return curs.fetchall()[0][0]

def usage_report(curs, conn, num_shown=20):
    usage = {}
    q = ('SELECT f.title, sum(length(content)) AS cl FROM `posts` p JOIN `feeds` f '
        'ON f.id = p.feed_id GROUP BY feed_id ORDER BY cl DESC LIMIT ?;')
    curs.execute(q, (num_shown,))
    for x in curs.fetchall():
        usage[x[0]] = x[1]
    return usage

def run_arbitrary_sql(query, curs, conn):
    print(f'Running command: {query}')
    curs.execute(query)

def update_feed_folder(feed_id, new_folder, curs, conn):
    if new_folder:
        new_folder = str(new_folder)
        q = 'UPDATE `feeds` SET `folder` = ? WHERE `id` = ?'
        try:
            curs.execute(q, (new_folder, feed_id))
            conn.commit()
        except Exception as err:
            print(f'Error changing folder for {feed_id} - {err}')
            return False
        else:
            print(f'Changed folder for {feed_id} to {new_folder}.')
            return True
    return False

def main():
    #dbfile = 'd:\\tmp\\posts.db'
    #dbfile = 'D:\\Python\\Code\\harvester\\tests\\test.db'
    #curs, conn = connect_DB_file(dbfile)
    #get_data(curs, conn)
    #newpost = Post(2, 'The Hypogeum', 'Father Inire', '2021-06-08', 'Certainly it is desirable to maintain in being a movement that has proved so useful in the past, and as long as the mirrors of the caller Hethor remain unbroken, she provides it with a plausible commander.')
    #write_post(dbfile, 'vfdvdf', curs, conn)
    #posttest = get_most_recent(5, curs, conn)
    #k = count_all_unread()
    #print(posttest)
    #mark_old_as_read(3, curs, conn)
    #vacuum(conn)
    #k = text_search('new world', curs, conn, None, None)
    #print(k)
    #  feed.feed_id, feed.title, feed.folder, feed.f_type, feed.rss_url, feed.html_url, str(feed.tags))
    #newfeed = rsslib.Feed('aaa Feed ID', 'aaa Feed title', 'folder', 'rss', 'http://whatever.com',
                           #'http://direct.com', '[]')
    #write_feed(newfeed, curs, conn)
    #feed_id = 'http://deltasdnd.blogspot.com/'
    #lrd = find_date_last_read(feed_id, curs, conn)
    #k = find_date_all_feeds_last_read(curs, conn)
    #print(k)
    #print(usage_report(curs, conn))
    #print(text_search('symbol', curs, conn, None, 'month'))  # kryl
    #print(find_inactive_feeds(2021, curs, conn))
    #mass_delete_all_but_last_n(100, curs, conn)
    a, b = create_DB(':memory:')

if __name__ == '__main__':
    main()
