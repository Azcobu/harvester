import feedparser
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable)
import rsslib

class WorkerSignals(QObject):
    started = pyqtSignal(tuple)
    finished = pyqtSignal(tuple)
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)

class Worker(QRunnable):
    def __init__(self, listsize, workernum, url_queue, db_queue):
        super(Worker, self).__init__()
        self.listsize = listsize
        self.workernum = workernum
        self.url_queue = url_queue
        self.db_queue = db_queue
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        while not self.url_queue.empty():
            currfeed = self.url_queue.get()
            feednum = self.listsize - self.url_queue.qsize()
            msg = (f'{feednum}/{self.listsize}: Worker {self.workernum+1} '
                   f'retrieving {currfeed.title}')
            print(msg)
            self.signals.started.emit((msg, currfeed.title))
            try:
                parsedfeed = feedparser.parse(currfeed.rss_url)
            except Exception as err:
                print(f'Failed to read feed {currfeed.title} - {err}')
            else:
                if parsedfeed.entries:
                    # QQQQ should check for post date - if < last read, discard
                    # this allows only new entries to be written, and helps with
                    # updating the feed list tree
                    for p in parsedfeed.entries:
                        newpost = rsslib.parse_post(currfeed, p)
                        if newpost:
                            newpost.strip_image_tags()
                            self.db_queue.put(newpost)
                self.url_queue.task_done()
            #self.signals.result.emit(result) # Return the result of the process
            finally:
                num_new = 0
                self.signals.finished.emit((num_new, currfeed.title)) # Done
        self.db_queue.put('stopsignal')

if __name__ == '__main__':
    main()
