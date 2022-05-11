# Handles subscriptions ot new feeds.

import rsslib
from PyQt5.QtWidgets import QDialog
from ui.harvnewsub import Ui_frmNewSub

class NewSubDialog(QDialog):
    """UI elements for subscribing to a new feed."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.feed = ''
        self.srchtext = ''
        self.ui = Ui_frmNewSub()
        self.ui.setupUi(self)
        self.ui.lineNewSubFeedUrl.setFocus()

        #populate listbox
        self.ui.listNewSubFolders.addItems(parent.folderlist)
        if self.ui.listNewSubFolders.count() > 0:
            self.ui.listNewSubFolders.item(0).setSelected(True)

        # Connect up the buttons
        self.ui.btnNewSubCheck.clicked.connect(self.check_button)
        self.ui.btnNewSubOK.clicked.connect(self.ok_button)
        self.ui.btnNewSubCancel.clicked.connect(self.cancel_button)

        self.ui.btnNewSubOK.setDisabled(True)
        self.ui.lineNewSubFeedUrl.textEdited.connect(self.edit_feed_url)

    def check_button(self):
        feed_url = self.ui.lineNewSubFeedUrl.text()
        if feed_url:
            if feed_url not in [x.rss_url for x in self.parent.feeds.values()]:
                self.ui.lblFeedValid.setText('Checking feed...')
                self.ui.lblFeedValid.repaint()
                results = rsslib.validate_feed(feed_url)
                if type(results) == rsslib.Feed:
                    self.feed = results
                    self.ui.lineNewSubFeedUrl.setText(results.rss_url)
                    self.ui.lblFeedValid.setText('Feed is valid.')
                    self.ui.lineNewSubTitle.setText(results.title)
                    self.ui.btnNewSubOK.setDisabled(False)
                    #else:
                    #    self.ui.lblFeedValid.setText('Duplicate feed title.')
                else:
                    self.ui.lblFeedValid.setText('Feed URL is invalid.')
            else:
                self.ui.lblFeedValid.setText('Subscription already exists.')

    def ok_button(self):
        self.accept()

    def cancel_button(self):
        self.reject()

    def get_inputs(self):
        if self.ui.listNewSubFolders.count() > 0:
            if not self.ui.listNewSubFolders.currentItem():
                self.ui.listNewSubFolders.setCurrentRow(0)
            self.feed.folder = self.ui.listNewSubFolders.currentItem().text()
        else:
            self.feed.folder = None

        self.feed.title = self.ui.lineNewSubTitle.text()

        return self.feed

    def edit_feed_url(self):
        self.ui.lblFeedValid.setText('')
