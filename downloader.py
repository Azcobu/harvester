import feedparser
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
            postlist = []
            currfeed = self.url_queue.get()
            feednum = self.listsize - self.url_queue.qsize()
            msg = (f'{feednum}/{self.listsize}: Worker {self.workernum+1} '
                   f'retrieving {currfeed.title}')
            logging.info(msg)
            self.signals.started.emit((msg, currfeed.id))
            try:
                parsedfeed = feedparser.parse(currfeed.rss_url)
            except Exception as err:
                logging.error(f'Failed to read feed {currfeed.title} - {err}')
            else:
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
                self.url_queue.task_done()
            finally:
                self.signals.finished.emit((unread_count, currfeed.id)) # Done
        #self.db_queue.put('stopsignal')

if __name__ == '__main__':
    main()
