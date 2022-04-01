# RSS-lib
#handles backend RSS stuff like retrieving and parsing feeds and posts

import threading
from queue import Queue
import feedparser
from dateutil.parser import *
import re
import string
import opml
import sqlitelib
import time
from PyQt5 import QtGui
from urllib.parse import urljoin

errorlog = []

class Feed:
    def __init__(self, feed_id, title, folder, f_type, rss_url, html_url, tags=[],\
                 last_read=0, favicon=None):
        self.feed_id = feed_id
        self.title = title
        self.folder = folder
        self.f_type = f_type
        self.rss_url = rss_url
        self.html_url = html_url
        self.tags = tags
        self.last_read = last_read
        self.favicon = favicon

    def __repr__(self):
        return f'Feed: {self.title} ({self.html_url})'

    def san(self, instr):
        # &apos; (') is also listed as excluded, but doesn't seem to cause any problems?
        if instr and type(instr) == str:
            rep = {'&':'&amp;', '"':'&quot;', '<':'&lt;', '>':'&gt;'}
            for k, v in rep.items():
                instr = instr.replace(k, v)
            return instr

    def sanitize(self):
        return Feed(self.feed_id, self.san(self.title), self.folder, self.f_type,
                    self.san(self.rss_url), self.san(self.html_url), self.san(self.tags),
                    self.last_read, self.favicon)

class Post:
    def __init__(self, p_id, feed_id, title, author, url, date, content, flags):
        self.p_id = p_id
        self.feed_id = feed_id
        self.title = title
        self.author = author
        self.url = url
        self.date = date
        self.content = content
        self.flags = flags

    def __repr__(self):
        return (f'Post: {self.title}')

    def strip_image_tags(self):
        p = re.compile(r'<img.*?/>')
        self.content = p.sub('', self.content)

def open_opml_file(infile):
    try:
        with open(infile, 'r') as inf:
            outdata = inf.read()
    except Exception as err:
        print(err)
    return outdata

def parse_opml(infile):
    #p_id, feed_id, title, folder, f_type, rss_url, html_url, tags=[], last_read, favicon)
    # needs to distinguish between folders and top-level folderless feeds

    currfolder = ''
    #feedlist =
    try:
        feedlist = opml.parse(infile)
    except Exception as err:
        print(f'Parsing of {infile} failed - {err}')
    else:
        folder_feeds, folderless_feeds = [], []

        for x in range(len(feedlist)):
            if not hasattr(feedlist[x], 'xmlUrl'): # this is a folder
                currfolder = feedlist[x].text
                for y in range(len(feedlist[x])):
                    data = feedlist[x][y]
                    try:
                        if hasattr(data, 'htmlUrl'):
                            newfeed = Feed(data.htmlUrl, data.title, currfolder, data.type,
                                           data.xmlUrl, data.htmlUrl)
                        else: # html link not in feed data, so fall back to xml url
                            newfeed = Feed(data.xmlUrl, data.title, currfolder, data.type,
                                           data.xmlUrl, data.xmlUrl)
                    except Exception as err:
                        print(f'Error parsing {data} - {err}')
                    else:
                        folder_feeds.append(newfeed)
            else: #folderless feed
                data = feedlist[x]
                try:
                    newfeed = Feed(data.htmlUrl, data.title, None, data.type,
                                   data.xmlUrl, data.htmlUrl)
                except Exception as err:
                    print(f'Error parsing {data} - {err}')
                else:
                    folderless_feeds.append(newfeed)

        folder_feeds.sort(key = lambda x: (x.folder, x.title))
        folderless_feeds.sort(key = lambda x: x.title)
        return folder_feeds + folderless_feeds

def parse_date(indate):
    try:
        outdate = parse(indate).isoformat()
    except Exception as err:
        print(f'Error parsing date {indate} - {err}')
        return indate
    return outdate

def parse_post(feed, postdata):
    try:
        if hasattr(postdata, 'id'):
            p_id = postdata['id']
        else:
            if hasattr(postdata, 'link'):
                p_id = postdata['link']

        if hasattr(postdata, 'title'):
            title = postdata['title']
        else:
            title = "Untitled Feed"

        if hasattr(postdata, 'author'):
            author = postdata['author']
        else:
            author = 'Unknown author'

        url = postdata['link']

        if hasattr(postdata, 'published'):
            date = postdata['published']
        else:
            if hasattr(postdata, 'updated'):
                date = postdata['updated']
        if date:
            date = parse_date(date) #QQQQ and if neither is found?

        if hasattr(postdata, 'content'):
            content = postdata['content'][0]['value']
        else:
            if hasattr(postdata, 'summary'):
                content = postdata['summary']
            else:
                content = 'No content found.'

        return Post(p_id, feed.feed_id, title, author, url, date, content, 'None')

    except Exception as err:
        print(f'Post parsing failed for feed {feed} - {err}.')
        errorlog.append(f'{err} - ' + str(postdata) + '\n\n')

def retrieve_feed(feed, db_curs, db_conn):
    postlist = []

    parsedfeed = feedparser.parse(feed.rss_url)

    if parsedfeed.entries:
        for p in parsedfeed.entries:
            try:
                newpost = parse_post(feed, p)
            except Exception as err:
                print(f'Parsing of post {p} failed - {err}.')
            else:
                if newpost:
                    newpost.strip_image_tags()
                    #print(newpost.title)
                    postlist.append(newpost)
        sqlitelib.write_post_list(postlist, db_curs, db_conn)
    else:
        print(f'No posts found for {feed.title}')

'''
def retrieve_all_feeds(feedlist):
    for feed in feedlist:
        print(f'Retrieving {feed.title}')
        retrieve_feed(feed)
'''
def save_error_log(errlog):
    errlog = ''.join(errlog)
    with open('d:\\tmp\\rss-errors.txt', 'w') as outfile:
        outfile.write(errlog)

def find_node(tree, flags, target):
    # should be feed ID column 1, but can't get that to work
    return tree.findItems(target, flags, 0)[0]

def import_opml_to_db(opmlfile, curr_feeds, db_curs, db_conn):
    trimfeeds = []
    dupes = 0
    already_subbed = set([x.feed_id for x in curr_feeds])
    feeds = parse_opml(opmlfile)
    if feeds:
        for x in feeds:
            if x.feed_id in already_subbed:
                print(f'Already subscribed to feed {x}, skipping import.')
                dupes += 1
            else:
                trimfeeds.append(x)
        sqlitelib.write_feed_list(trimfeeds, db_curs, db_conn)
        return len(trimfeeds), dupes
    else:
        return None, None

def import_feeds_from_db(db_curs, db_file):
    feedlist = sqlitelib.retrieve_feedlist(db_curs, db_file)
    return sorted(feedlist, key=lambda x:x.title.capitalize())

def export_feeds_to_opml(feedlist):
    pass

def worker(listsize, workernum, q, DB_queue, mainwin=None, flags=None, upicon=None):
    # QQQQ should update the tree items with new font and number of new posts too
    # approaches - either compare dates of parsed posts with latest read date from
    # DB of self.feedlist, or count after all downloaded, which means another DB access
    node = None

    while not q.empty():
        currfeed = q.get()
        feednum = listsize - q.qsize()

        #unread_count = 0

        if mainwin.treeMain:
            #node = find_node(treeMain, flags, currfeed.title)
            try:
                node = mainwin.treeMain.findItems(currfeed.title, flags, 0)[0]
                if node:
                    curricon = node.icon(0)
                    node.setIcon(0, upicon)
            except Exception as err:
                pass

        mainwin.statusbar.showMessage(f'{feednum}/{listsize}: Worker {workernum+1} retrieving {currfeed.title}')
        try:
            parsedfeed = feedparser.parse(currfeed.rss_url)
        except Exception as err:
            print(f'Failed to read feed {currfeed.title} - {err}')

        if parsedfeed.entries:
            for p in parsedfeed.entries:
                newpost = parse_post(currfeed, p)
                if newpost:
                    newpost.strip_image_tags()
                    # QQQQ - run a DB query here to find unread post count?
                    # with all threads running, seems likely to fail
                    #if newpost.date > last_read_post_date:
                    #    unread_count += 1

                    DB_queue.put(newpost)
        else:
            print(f'No posts found for {currfeed.title}')

        if mainwin.treeMain and node:
            try:
                node.setIcon(0, curricon)
            except Exception as err:
                pass
            #if unread_count:
            #    node.setText(0, f'{currfeed.title} ({unread_count})')
            #    node.setFont(0, QFont('Segoe UI', 10, QFont.Bold))
        '''
        try:
            mainwin.progressBar.setValue(feednum)
        except Exception as err:
            print(err)
        '''

        q.task_done()
    DB_queue.put('stopsignal')

def DB_writer(DB_queue, numworkers, db_filename, mainwin):
    stopsfound = 0
    postlist = []

    db_curs, db_conn = sqlitelib.connect_DB(db_filename)

    while stopsfound < numworkers:
        while not DB_queue.empty():
            currpost = DB_queue.get()
            if currpost == "stopsignal":
                stopsfound += 1
                print(f'Stop signal {stopsfound} found.')
                if stopsfound == 10:
                    print('Scan completed.')
                    if mainwin.statusbar.isVisible() == True:
                        mainwin.statusbar.showMessage('Feed scan completed.')
            else:
                postlist.append(currpost)

        if postlist:
            print(f'Writing batch of {len(postlist)} posts to DB.')
            try:
                sqlitelib.write_post_list(postlist, db_curs, db_conn)
            except Exception as err:
                print(f"DB write error - {err}")
            postlist = []
            time.sleep(1)
    DB_queue.task_done()

'''
def retrieve_feeds(feedlist, treeMain=None, flags=None):
    q = Queue()
    DB_queue = Queue()

    numworkers = 10

    listsize = len(feedlist)
    for feed in feedlist:
        q.put(feed)

    for x in range(numworkers):
        t = threading.Thread(target=worker, args=(listsize, x, q, DB_queue, treeMain, flags))
        t.start()

    DB_thread = threading.Thread(target=DB_writer, args=[DB_queue, numworkers])
    DB_thread.start()
    q.join()
    DB_thread.join()
    print('Feed retrieval finished.')
'''

def test_feed(feed_url):
    # returns either a Feed object or False
    # feed_id, title=title, folder=None, f_type, rss_url, html_url=link, tags, favicon
    try:
        parsedfeed = feedparser.parse(feed_url)
        title = parsedfeed.feed.title
        newfeed = Feed(feed_url, parsedfeed.feed.title, None, 'rss', feed_url,
                       parsedfeed.feed.link, '[]', None)
        return newfeed
    except Exception as err:
        print(f'Failed to parse feed at {feed_url} - {err}')
        return False

def validate_feed(feed_url):
    # variants: try /feed/ or /rss/ or /feeds/posts/default/
    #check if feed url is correct, and if possible return feed title
    results = test_feed(feed_url) or\
              test_feed(urljoin(feed_url, '/feed/')) or\
              test_feed(urljoin(feed_url, '/rss/')) or\
              test_feed(urljoin(feed_url, '/feeds/posts/default/'))
    return results

def main():
    db_file = 'd:\\tmp\\posts.db'
    #retrieve_feed('http://www.reddit.com/r/python/.rss')
    #invfull = 'http://bhagpuss.blogspot.com/feeds/posts/default'
    #futclo = 'http://feeds.feedburner.com/FutilityCloset'
    #post = retrieve_feed(futclo)
    feedlist = parse_opml('d:\\tmp\\aus-feeds.opml')
    print(f'{len(feedlist)} feeds imported.')
    #retrieve_feeds(feedlist)
    #save_error_log(errorlog)
    #export_opml_to_db('d:\\tmp\\blw10.opml', db_file)
    #sd = 'https://erikhoel.substack.com'
    #k = validate_feed(sd)
    #print(k)

if __name__ == '__main__':
    main()
