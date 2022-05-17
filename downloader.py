import requests
import logging
from datetime import datetime
import feedparser
import favicon
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QRunnable
import rsslib
import dbhandler

class WorkerSignals(QObject):
    started = pyqtSignal(tuple)
    finished = pyqtSignal(tuple)
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)
    icondata = pyqtSignal(tuple)

class Worker(QRunnable):
    def __init__(self, max_q_size, workernum, feed_queue, db_queue, feeds,
                 dl_feeds = True, dl_icons=False):
        super(Worker, self).__init__()
        self.max_q_size = max_q_size
        self.workernum = workernum
        self.feed_queue = feed_queue
        self.db_queue = db_queue
        self.feeds = feeds
        self.dl_feeds = dl_feeds
        self.dl_icons = dl_icons
        self.signals = WorkerSignals()
        self.feednum = 0
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    @pyqtSlot()
    def run(self):
        while not self.feed_queue.empty():
            feed = self.feed_queue.get()
            self.feednum = self.max_q_size - self.feed_queue.qsize()

            self.generate_status_msg(feed)

            if self.dl_feeds:
                self.dl_feed(feed)

            if self.dl_icons:
                self.dl_icon(feed)

            self.feed_queue.task_done()

    def generate_status_msg(self, feed):
        msg = (f"{self.feednum}/{self.max_q_size}: Worker {self.workernum+1} "
               f"retrieving {feed.title}")
        #logging.info(msg)
        self.signals.started.emit((msg, feed.id))

    def dl_feed(self, feed):
        unread_count = 0
        postlist = []
        logging.info(f'DL starting for {feed.title}')

        try:
            parsedfeed = feedparser.parse(feed.rss_url,
                                          etag=feed.etag,
                                          modified=feed.last_modified)
        except Exception as err:
            logging.error(f"Failed to read feed {feed.title} - {err}")
        else:
            if self.check_return_status_ok(parsedfeed, feed):
                # update last modified time and etag, both locally and in DB
                self.update_lastmod_etag(parsedfeed, feed)

                if parsedfeed.entries:
                    for p in parsedfeed.entries:
                        newpost = rsslib.parse_post(feed, p)
                        if newpost:
                            newpost.strip_image_tags()
                            postlist.append(newpost)
                if postlist:
                    unread_count = sum([1 for p in postlist
                                        if p.date > self.feeds[feed.id].last_read])
                    self.db_queue.put(dbhandler.DBJob("write_post_list", postlist))
        finally:
            self.signals.finished.emit((unread_count, feed.id))

    def check_return_status_ok(self, parsedfeed, feed):
        if hasattr(parsedfeed, "status"):
            if parsedfeed.status == 304:
                logging.info(f"{self.feednum}/{self.max_q_size}: Skipping {feed.id} "
                             f"as it is unchanged.")
            elif str(parsedfeed.status)[0] in ["4", "5"]:
                logging.error(f"Error retrieving feed {feed.title} - "
                                  f"error code was {parsedfeed.status}")
            else: # this accepts any other 2-- and 3-- values, needed because
                  # some feeds return 3-- codes along with a valid feed. Be nice to
                  # handle 301 permanent redirects properly in future.
                return True

    def update_lastmod_etag(self, parsedfeed, feed):
        lastmod = (parsedfeed.modified if hasattr(parsedfeed, "modified")
                                       else "Thu, 1 Jan 1970 00:00:00 GMT")
        etag = parsedfeed.etag if hasattr(parsedfeed, "etag") else "0"

        if (self.feeds[feed.id].last_modified != lastmod
            or self.feeds[feed.id].etag != etag):
            self.feeds[feed.id].last_modified = lastmod
            self.feeds[feed.id].etag = etag

            self.db_queue.put(dbhandler.DBJob("update_lastmod_etag",
                              [feed.id, lastmod, etag]))

    def dl_icon(self, feed):
        if not feed.favicon:
            try:
                logging.debug(f'Getting icon for {feed.title}')
                icons = favicon.get(feed.html_url)
                # get icon > 0 and about 64
                poss = [x for x in icons if x.height <= 64]
                if poss:
                    icon = sorted(poss, key=lambda x:x.height, reverse=True)[0]
                else:
                    icon = sorted(icons, key=lambda x:x.height)[0]
                response = requests.get(icon.url, stream=True,
                                        headers={"User-Agent": "Harvester"})
            except Exception as err:
                logging.debug(f'Icon get failed for feed {feed.title} - {err}')
            else:
                if 'text/html' not in response.headers['content-type']:
                    data = b''
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            data += chunk
                    self.db_queue.put(dbhandler.DBJob("update_favicon", [feed.id, data]))
                    self.signals.icondata.emit((feed.id, data))
                else:
                    #logging.error(f'{feed.title} - Response was text rather than binary.')
                    pass

def main():
    pass

if __name__ == "__main__":
    main()
