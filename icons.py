import favicon
import requests
import dbhandler
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QObject, QRunnable)
import logging
import time

class IconSignals(QObject):
    started = pyqtSignal(tuple)
    icondata = pyqtSignal(tuple)

class IconHandler(QObject):
    def __init__(self, feeds, db_q):
        super(IconHandler, self).__init__()
        self.feeds = feeds
        self.db_q = db_q
        self.signals = IconSignals()
        self.running = True

        logging.getLogger("urllib3").setLevel(logging.WARNING)

    def run(self):
        self.exec()

    def exec(self):
        #time.sleep(20)
        logging.info('Starting icon updates.')
        for k, v in self.feeds.items():
            if not self.running:
                break
            if not self.feeds[k].favicon:
                self.save_icon(v.id, v.html_url)
            time.sleep(3)

    def stop(self):
        logging.debug('Shutting down icon updater thread.')
        self.running = False

    def save_icon(self, feed_id, html_url):
        try:
            logging.debug(f'Getting icon for {feed_id}')
            icons = favicon.get(html_url)
            # get icon > 0 and about 64
            poss = [x for x in icons if x.height <= 64]
            if poss:
                icon = sorted(poss, key=lambda x:x.height, reverse=True)[0]
            else:
                icon = sorted(icons, key=lambda x:x.height)[0]
            response = requests.get(icon.url, stream=True)
        except Exception as err:
            logging.debug(f'Icon get failed for {feed_id} - {err}')
        else:
            if 'text/html' not in response.headers['content-type']:
                data = b''
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        data += chunk
                self.db_q.put(dbhandler.DBJob("update_favicon", [feed_id, data]))
                self.signals.icondata.emit((feed_id, data))
            else:
                logging.error(f'{feed_id} - Response was text rather than binary.')

def main():
    # still need to sanitize name as it does not handle added url elements well
    # i.e. http://www.theregister.co.uk/
    pass

if __name__ == '__main__':
    main()
