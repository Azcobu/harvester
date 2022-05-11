import feedparser
from datetime import datetime
import logging
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable)
import rsslib
import dbhandler

class WorkerSignals(QObject):
    started = pyqtSignal(tuple)
    finished = pyqtSignal(tuple)
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)

class Worker(QRunnable):
    def __init__(self, listsize, workernum, url_queue, db_queue, feeds):
        super(Worker, self).__init__()
        self.listsize = listsize
        self.workernum = workernum
        self.url_queue = url_queue
        self.db_queue = db_queue
        self.signals = WorkerSignals()
        self.feeds = feeds

    @pyqtSlot()
    def run(self):
        while not self.url_queue.empty():
            unread_count = 0
            postlist = []
            currfeed = self.url_queue.get()
            feednum = self.listsize - self.url_queue.qsize()
            msg = (f'{feednum}/{self.listsize}: Worker {self.workernum+1} '
                   f'retrieving {currfeed.title}')
            logging.info(msg)
            self.signals.started.emit((msg, currfeed.id))
            try:
                parsedfeed = feedparser.parse(currfeed.rss_url,
                                              etag = currfeed.etag,
                                              modified = currfeed.last_modified)
            except Exception as err:
                logging.error(f'Failed to read feed {currfeed.title} - {err}')
            else:
                if parsedfeed.status == 304:
                    logging.info(f'{feednum}/{self.listsize}: Skipping {currfeed.id} '
                                 f'as it is unchanged.')
                elif parsedfeed.status == 200:
                    # update last modified time and etag, both locally and in DB
                    self.update_lastmod_etag(parsedfeed, currfeed)

                    if parsedfeed.entries:
                        for p in parsedfeed.entries:
                            newpost = rsslib.parse_post(currfeed, p)
                            if newpost:
                                newpost.strip_image_tags()
                                postlist.append(newpost)
                    if postlist:
                        unread_count = sum([1 for p in postlist if p.date >
                                           self.feeds[currfeed.id].last_read])
                        self.db_queue.put(dbhandler.DBJob('write_post_list', postlist))
            finally:
                self.signals.finished.emit((unread_count, currfeed.id))
            self.url_queue.task_done()
        #self.db_queue.put('stopsignal')

    def update_lastmod_etag(self, parsedfeed, currfeed):
        lastmod = parsedfeed.modified if hasattr(parsedfeed, 'modified') else "Thu, 1 Jan 1970 00:00:00 GMT"
        etag = parsedfeed.etag if hasattr(parsedfeed, 'etag') else '0'

        self.feeds[currfeed.id].last_modified = lastmod
        self.feeds[currfeed.id].etag = etag

        if lastmod != "Thu, 1 Jan 1970 00:00:00 GMT" and etag != '0':
            self.db_queue.put(dbhandler.DBJob('update_lastmod_etag',
                                              [currfeed.id, lastmod, etag]))

def main():
    pass

if __name__ == '__main__':
    main()

