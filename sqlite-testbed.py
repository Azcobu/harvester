# SQLite testbed
# iplement article storage, deletion, searching
# DB fields - ID, site, author, date, text
# folder?
# How to handle apostrophes, etc in text?
import feedparse, opml

dbfile = 'd:\\tmp\\posts.db'

import sqlite3

sevtext = 'What struck me on the beach—and it struck me indeed, so that I staggered as at a blow—was that if the Eternal Principle had rested in that curved thorn I had carried about my neck across so many leagues, and if it now rested in the new thorn (perhaps the same thorn) I had only now put there, then it might rest in anything, and in fact probably did rest in everything, in every thorn on every bush, in every drop of water in the sea. The thorn was a sacred Claw because all thorns were sacred Claws; the sand in my boots was sacred sand because it came from a beach of sacred sand. The cenobites treasured up the relics of the sannyasins because the sannyasins had approached the Pancreator. But everything had approached and even touched the Pancreator, because everything had dropped from his hand. Everything was a relic. All the world was a relic. I drew off my boots, that had traveled with me so far, and threw them into the waves that I might not walk shod on holy ground.'

class Post:
    def __init__(self, post_id, site, author, date, text):
        self.post_id = post_id
        self.site = site
        self.author = author
        self.date = date
        self.text = text

    def __repr__(self):
        return (f'ID: {self.post_id}, Site: {self.site}, Author: {self.author}, '
                f'Date: {self.date}, Text: {self.text}')

def connect_DB(db_file):
    try:
        conn = sqlite3.connect(dbfile)
    except Exception as err:
        print(err)
    curs = conn.cursor()
    return curs, conn

def create_DB(filename):
    conn = sqlite3.connect(filename)
    c = conn.cursor()

    # Create table
    c.execute(
    '''CREATE TABLE feeds (
        id       integer primary key autoincrement,
        title    text,
        folder   text,
        type     text,
        rss_url  text,
        html_url text,
        tags     text
        )
    ''')

    c.execute(
    '''CREATE TABLE posts (
        id      integer primary key autoincrement,
        title   text,
        author  text,
        url     text,
        date    datetime,
        content text
        )
    ''')

    # Insert a row of data
    #c.execute(f"INSERT INTO posts VALUES (1, 'Book of Gold', 'Ultan', '2022-06-08', '{sevtext}')")
    conn.commit()
    conn.close()

def text_search(curs, conn, tablename, target):
    # search scores?
    # search for multiple terms?

    try:
        curs.execute(f'SELECT id FROM posts WHERE {tablename} LIKE "%{target}%"'
                      'ORDER BY date')
    except Exception as err:
        print(f'Error: {err}')
    else:
        found = curs.fetchall()
        for f in found:
            print(f)

def get_data(curs, conn):
    curs.execute('SELECT * FROM posts')
    msgs = curs.fetchall()

    for m in msgs:
        newmsg = Post(*m)
        print(newmsg)

def write_post(post, filename, curs=None, conn=None):
    if not conn:
        # get connection
        curs, conn = connect_DB(filename)

    posttuple = post.p_id, post.title, post.author, post.url, post.date, post.content
    curs.execute("INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?);", posttuple)
    conn.commit()

def main():
    #curs, conn = connect_DB(dbfile)
    #create_DB('d:\\tmp\\rsstest.db')
    #get_data(curs, conn)
    #newpost = Post(2, 'The Hypogeum', 'Fathr Inire', '2021-06-08', 'Certainly it is desirable to maintain in being a movement that has proved so useful in the past, and as long as the mirrors of the caller Hethor remain unbroken, she provides it with a plausible commander.')
    #add_post(curs, conn, newpost)
    #text_search(curs, conn, 'text', 'of')

if __name__ == '__main__':
    main()
