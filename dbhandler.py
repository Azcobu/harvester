import logging
from dataclasses import dataclass
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable)
import sqlitelib

@dataclass
class DBJob:
    name: str
    params: list

class DBSignals(QObject):
    started = pyqtSignal(tuple)
    finished = pyqtSignal(tuple)
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)
    feedposts = pyqtSignal(list)

class DBHandler(QObject):
    def __init__(self, db_q, db_filename):
        super(DBHandler, self).__init__()
        self.db_q = db_q
        self.db_filename = db_filename
        self.signals = DBSignals()

    def run(self):
        self.exec()

    def exec(self):
        stopsfound = 0
        postlist = []
        comm_count = 0

        db_curs, db_conn = sqlitelib.connect_DB_file(self.db_filename)
        sqlitelib.set_sqlite_pragmas(db_curs, db_conn)

        while True:
            op = self.db_q.get()
            if op.name == 'write_post_list':
                postlist = op.params
                sqlitelib.write_post_list(postlist, db_curs, db_conn)
            elif op.name == 'mark_feed_read':
                sqlitelib.mark_feed_read(op.params[0], db_curs, db_conn)
                #logging.debug(f'DB handler marked feed {op.params[0]} as read.')
            elif op.name == 'get_feed_posts':
                feed_id = op.params[0]
                results = sqlitelib.get_feed_posts(feed_id, db_curs, db_conn)
                self.signals.feedposts.emit(results)
            elif op.name == 'update_lastmod_etag':
                feed_id, last_mod, etag = op.params
                sqlitelib.update_lastmod_etag(feed_id, last_mod, etag, db_curs, db_conn)
                #logging.debug(f'DB handler updated etag/lastmod for feed {feed_id}')
            elif op.name == 'update_favicon':
                feed_id, data = op.params
                sqlitelib.update_favicon(feed_id, data, db_curs, db_conn)
            elif op.name == 'SHUTDOWN':
                db_conn.close()
            logging.debug(f'Running DB command {op.name} - queue is {self.db_q.qsize()}')

            comm_count += 1
            if comm_count % 50 == 0 or self.db_q.qsize() == 0:
                try:
                    db_conn.commit()
                except:
                    pass
            self.db_q.task_done()

        db_conn.commit()
        logging.debug(f'DB handler thread halting.')

        '''
        while stopsfound < numworkers:
            while not self.q.empty():
                currpost = DB_queue.get()
                if currpost == "stopsignal":
                    stopsfound += 1
                    logging.debug(f'Stop signal {stopsfound} found.')
                    if stopsfound == numworkers:
                        logging.debug('Scan completed.')
                        if mainwin.statusbar.isVisible() == True:
                            mainwin.statusbar.showMessage('Feed scan completed.')
                else:
                    postlist.append(currpost)

            if postlist:
                logging.debug(f'Writing batch of {len(postlist)} posts to DB.')
                try:
                    sqlitelib.write_post_list(postlist, db_curs, db_conn)
                except Exception as err:
                    logging.error(f"DB write error - {err}")
                postlist = []
                time.sleep(1)
    DB_queue.task_done()
        '''

def main():
    pass

if __name__ == '__main__':
    main()
