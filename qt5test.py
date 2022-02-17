# - add generated newest posts page to folder list
# - start reddcrawl automatically and rewrite for JIT deletion of subredds, not mass
#   wipe of whole directory on start
# - add subprocess call of reddcrawler
# create dict for last read post date - also needs to fill in for feeds with no posts read

import sys
from subprocess import Popen #, CREATE_NEW_CONSOLE
from os import listdir, path
from PyQt5 import QtGui
from PyQt5.QtCore import (Qt, QSettings, QUrl, QFile, QTextStream, QThread, pyqtSignal,
                         pyqtSlot)
from PyQt5.QtGui import QFont, QIcon, QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (QApplication, QTreeView, QPushButton, QMainWindow,
                             QTreeWidgetItem, QMenu, QAction, QDialog, QProgressBar,
                             QLineEdit, QLabel, QMessageBox, QInputDialog, QWidget,
                             QToolBar, QHBoxLayout, QShortcut, QCheckBox, QFileDialog)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from harvester import Ui_MainWindow
from harvsearch import Ui_frmSearch
from harvnewsub import Ui_frmNewSub
import rsslib
import sqlitelib
import breeze_resources
from dateutil.parser import *
from dateutil import tz
from datetime import datetime
import threading
from queue import Queue
import urllib.request

class CustomWebEnginePage(QWebEnginePage):
    # Custom WebEnginePage to customize how we handle link navigation
    def acceptNavigationRequest(self, url,  _type, isMainFrame):
        if (_type == QWebEnginePage.NavigationTypeLinkClicked):
            # Send the URL to the system default URL handler.
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url,  _type, isMainFrame)

class ReaderUI(QMainWindow):
    version_str = 'Harvester 0.1'
    console_output = True
    dbfile = ''
    node_name, node_id = '', ''
    web_zoom = 1.25
    srchtext = ''
    page_size = 10 # how many posts to a page
    curr_page = 1
    max_page = 1
    results = []
    last_read = {}
    redd_dir = ''

    def __init__(self):
        super(ReaderUI, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.webEngine = QWebEngineView()
        self.ui.webEngine.setPage(CustomWebEnginePage(self))
        self.ui.splitter.addWidget(self.ui.webEngine)

        self.ui.buttonNextPage = QPushButton('>>')
        self.ui.labelPage = QLabel()
        self.ui.buttonPrevPage = QPushButton('<<')

        self.ui._search_panel = SearchPanel()
        self.ui.search_toolbar = QToolBar()
        self.ui.search_toolbar.addWidget(self.ui._search_panel)
        self.addToolBar(Qt.BottomToolBarArea, self.ui.search_toolbar)
        #self.ui.statusbar.addWidget(self.ui.search_toolbar)
        self.ui.search_toolbar.hide()
        self.ui._search_panel.searched.connect(self.on_searched)
        self.ui._search_panel.closed.connect(self.ui.search_toolbar.hide)

        self.initializeUI()
        self.show()

    def initializeUI(self):
        self.load_previous_state()
        self.locate_db()
        self.locate_reddit_dir()
        self.db_curs, self.db_conn = sqlitelib.connect_DB(self.dbfile)
        self.load_feed_data()
        self.setup_tree()

        self.ui.treeMain.setMouseTracking(True)
        self.ui.treeMain.itemClicked.connect(self.tree_click)
        self.ui.treeMain.itemEntered.connect(self.tree_hover)
        self.ui.treeMain.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeMain.customContextMenuRequested.connect(self.tree_context_menu)

        #self.ui.progressBar = QProgressBar()
        #self.ui.statusbar.addPermanentWidget(self.ui.progressBar)
        #self.ui.progressBar.setGeometry(30, 40, 200, 25)
        #self.ui.progressBar.setValue(50)

        #create actions
        self.newSubAction = QAction("&New Subscription", self)
        self.markReadAction = QAction("Mark Read", self)
        self.updateFeedAction = QAction("&Update Feed", self)
        self.unsubAction = QAction("Unsubscribe", self)

        #connect actions
        self.newSubAction.triggered.connect(self.new_sub)
        self.markReadAction.triggered.connect(self.mark_read)
        self.updateFeedAction.triggered.connect(self.update_feed)
        self.unsubAction.triggered.connect(self.unsubscribe_feed)

        # search box
        self.ui.lineSearch.textChanged.connect(self.search_feed_names)

        # menu items
        # File
        self.ui.actionSubscribe.triggered.connect(self.new_sub)
        self.ui.actionLoad_Database.triggered.connect(self.load_db)
        self.ui.actionDatabase_Maintenance.triggered.connect(self.maintain_DB)
        self.ui.actionSelect_Reddit_Directory.triggered.connect(self.locate_reddit_dir)
        self.ui.actionExit.triggered.connect(self.exit_app)

        # Edit
        self.ui.actionFind_in_Page.triggered.connect(self.find_in_page)

        # View
        self.ui.actionMost_Recent.triggered.connect(lambda: self.view_most_recent(100))
        self.ui.actionIncrease_Text_Size.triggered.connect(self.increase_text_size)
        self.ui.actionDecrease_Text_Size.triggered.connect(self.decrease_text_size)

        # Tools
        self.ui.actionUpdate_All_Feeds.triggered.connect(self.update_all_feeds)
        self.ui.actionSearch_Feeds.triggered.connect(self.search_feeds)
        self.ui.actionMark_Older_As_Read.triggered.connect(self.mark_older)
        self.ui.actionUpdate_Reddit.triggered.connect(self.update_reddit)

        #setup status bar
        self.ui.buttonPrevPage.setDisabled(True) #start with prev button disabled
        self.ui.statusbar.addPermanentWidget(self.ui.buttonPrevPage)
        self.ui.statusbar.addPermanentWidget(self.ui.labelPage)
        self.ui.statusbar.addPermanentWidget(self.ui.buttonNextPage)
        self.ui.buttonNextPage.clicked.connect(self.next_page)
        self.ui.buttonPrevPage.clicked.connect(self.prev_page)

        self.ui.webEngine.page().linkHovered.connect(self.link_hover)

        self.dl_icon = QIcon(r'k:\Dropbox\Python\icons-rss\icons8-download-100.png')
        self.folder_icon = QIcon(r'k:\Dropbox\Python\icons-rss\icons8-folder-100.png')
        self.update_icon = QIcon(r'k:\Dropbox\Python\icons-rss\icons8-right-arrow-100.png')

        self.view_most_recent()
        self.ui.webEngine.loadFinished.connect(self.set_web_zoom)
        self.ui.webEngine.setZoomFactor(self.web_zoom)

        #begin initial feed update
        #self.update_all_feeds()

    def link_hover(self, url):
        self.ui.statusbar.showMessage(f'{url}')

    def output(self, instr):
        # centralises all output so it can be disabled or logged as needed
        if self.console_output:
            print(instr)

    def tree_context_menu(self, position):
        # should differentiate between feeds and folders and show options accordingly
        index = self.ui.treeMain.indexAt(position)
        if not index.isValid():
            return

        item = self.ui.treeMain.itemAt(position)
        self.node_name = item.text(0)  # The text of the node.
        self.node_id = item.text(1)
        self.output(f'Clicked on {self.node_name}')

        menu = QMenu()
        action1 = menu.addAction(self.newSubAction)
        menu.addSeparator()
        action2 = menu.addAction(self.markReadAction)
        menu.addSeparator()
        #action = menu.addAction(f'{self.node_name} - {self.node_id}')
        action3 = menu.addAction(self.updateFeedAction)

        if self.node_id not in ['folder', 'reddfile']:
            menu.addSeparator()
            action_1 = menu.addAction(self.unsubAction)
            action_2 = menu.addAction("Choice 2")
            action_3 = menu.addAction("Choice 3")
        menu.exec_(self.ui.treeMain.mapToGlobal(position))

    def search_feed_names(self):
        srchtext = self.ui.lineSearch.text()
        self.output(f'Searching for {srchtext}')
        if srchtext == '':
            self.setup_tree()
        else:
            if len(srchtext) < 3: #ignore 1, 2 letters
                pass
            else:
                try:
                    self.generate_filtered_tree(srchtext)
                except Exception as err:
                    self.output(f'{err}')

    def set_web_zoom(self):
        if not (isinstance(self.web_zoom, float) or isinstance(self.web_zoom, int)):
            self.output('Error retrieving previous zoom level - value was ' +
                       f'{self.web_zoom}. Setting to default of 125%.')
            self.web_zoom = 1.25
        self.ui.webEngine.setZoomFactor(self.web_zoom)

    def increase_text_size(self):
        self.web_zoom += 0.05
        self.set_web_zoom()
        self.ui.statusbar.showMessage(f'Screen zoom increased to {round(self.web_zoom*100)}%')

    def decrease_text_size(self):
        self.web_zoom -= 0.05
        self.set_web_zoom()
        self.ui.statusbar.showMessage(f'Screen zoom decreased to {round(self.web_zoom*100)}%')

    def load_previous_state(self):
        settings = QSettings('Hypogeum', 'Harvester')
        if settings.allKeys() != []:
            self.restoreGeometry(settings.value('geometry'))
            self.restoreState(settings.value("windowState"))
            self.ui.splitter.restoreState(settings.value("splitterSizes"))
            self.dbfile = settings.value('db_location')
            self.redd_dir = settings.value('redd_dir')
            zoom = settings.value('web_zoom')
            try:
                if zoom:
                    self.web_zoom = float(zoom)
                else:
                    self.web_zoom = 1.25
            except:
                self.web_zoom = 1.25

    def save_state(self):
        # here's where we save program size and position on exit
        # save treeview state at some stage?
        settings = QSettings('Hypogeum', 'Harvester')
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("splitterSizes", self.ui.splitter.saveState())
        settings.setValue("db_location", self.dbfile)
        settings.setValue("redd_dir", self.redd_dir)
        settings.setValue("web_zoom", self.web_zoom)

    def locate_db(self):
        if not self.dbfile:
            self.output('No local DB found, requesting location.')
            self.load_db()
        else:
            self.output(f'Using DB file {self.dbfile}.')

    def load_db(self):
        try:
            dlg = QFileDialog.getOpenFileName(self, "Open Database", "", \
            "DB Files (*.db);;All files (*.*)")
            if dlg:
                # QQQQ validate DB here
                self.dbfile = dlg[0]
        except Exception as err:
            self.output(f'{err}')

    def locate_reddit_dir(self, skip_query=True): # QQQQ this is a mess
        if (not self.redd_dir and self.redd_dir != 'Negative'):
            self.output('Locating Reddit directory.')
            if not skip_query:
                confirm = QMessageBox.question(self, "Locate Reddit directory?",
                          "Do you want to locate the Reddit files directory?",
                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if skip_query or confirm == QMessageBox.Yes:
                try:
                    rd = str(QFileDialog.getExistingDirectory(self, "Select Reddit Directory"))
                    if rd:
                        self.redd_dir = rd
                except Exception as err:
                    self.output(f'{err}')
            else:
                self.redd_dir = 'Negative' # set this so it doesn't ask again

    def closeEvent(self, event):
        self.save_state()
        self.close()

    def load_feed_data(self):
        self.feedlist = rsslib.import_feeds_from_db(self.db_curs, self.db_conn)
        # find all folders
        self.folderlist = set([x.folder for x in self.feedlist])
        self.folderlist = sorted(self.folderlist)

    def setup_tree(self):
        # Need to evaluate unread count - worth doing every time?
        unread_count_dict = sqlitelib.count_all_unread(self.db_curs, self.db_conn)

        # QQQQ find the date/time of the newest post that has been read, for each feed
        # this is so worker threads can update tree with unread numbers
        self.collate_feeds_last_read()

        self.ui.treeMain.clear()

        for f in self.folderlist:
            foldernode = QTreeWidgetItem(self.ui.treeMain, [f, 'folder'])
            foldernode.setFont(0, QFont("Segoe UI", 10, weight=QFont.Bold))
            foldernode.setIcon(0, QIcon(r'k:\Dropbox\Python\icons-rss\icons8-folder-100.png'))
            self.ui.treeMain.addTopLevelItem(foldernode)
            for feed in self.feedlist:
                if feed.folder == f:
                    if feed.feed_id in unread_count_dict:
                        unread_count_str = f' ({unread_count_dict[feed.feed_id]})'
                    else:
                        unread_count_str = ''
                    newnode = QTreeWidgetItem(foldernode, [f'{feed.title}{unread_count_str}', feed.feed_id])
                    fontweight = QFont.Bold if unread_count_str else False
                    newnode.setFont(0, QFont('Segoe UI', 10, fontweight))
                    if unread_count_str: # doesn't wrk due to style sheet
                    #    newnode.setForeground(0, QtGui.QBrush(Qt.yellow))  # QtGui.QColor("blue")))
                        newnode.setIcon(0, QIcon(r'k:\Dropbox\Python\icons-rss\icons8-newspaper-100.png'))

        # add redd folder
        if self.redd_dir and self.redd_dir != 'Negative':
            foldernode = QTreeWidgetItem(self.ui.treeMain, ['ReddFiles', 'folder'])
            foldernode.setFont(0, QFont("Segoe UI", 10, weight=QFont.Bold))
            reddfiles = listdir(self.redd_dir)
            for rf in reddfiles:
                newnode = QTreeWidgetItem(foldernode, [f'{rf}', 'reddfile'])
                newnode.setFont(0, QFont("Segoe UI", 10))

    def generate_filtered_tree(self, srchtext):
        unread_count_dict = sqlitelib.count_all_unread()

        self.ui.treeMain.clear()
        srchtext = srchtext.lower()
        self.output(f'Searching for feeds with {srchtext} in name...')

        for feed in self.feedlist:
            if srchtext in feed.title.lower():
                if feed.feed_id in unread_count_dict:
                    unread_count = unread_count_dict[feed.feed_id]
                else:
                    unread_count = 0
                newnode = QTreeWidgetItem(self.ui.treeMain, [f'{feed.title} ({unread_count})', feed.feed_id])
                newnode.setFont(0, QFont("Georgia", 10))
                #self.ui.treeMain.addTopLevelItem(newnode)

        # add redd folder
        if self.redd_dir and self.redd_dir != 'Negative':
            reddfiles = listdir(self.redd_dir)
            for rf in reddfiles:
                if srchtext in rf:
                    newnode = QTreeWidgetItem(self.ui.treeMain, [f'{rf}', 'reddfile'])
                    newnode.setFont(0, QFont("Georgia", 10))

    def collate_feeds_last_read(self):
        # QQQQ for each feed, gets the date of the last read post
        last_read = sqlitelib.find_date_all_feeds_last_read(self.db_curs, self.db_conn)
        for f in self.feedlist:
            if f.feed_id in last_read:
                f.last_read = last_read[f.feed_id]

    def exit_app(self):
        self.output('Exiting app...')
        self.close()

    def tree_click(self):
        #QQQQ also needs to update page controls, as max_page doesn't seem to update
        # if a new page is added
        node_title = self.ui.treeMain.currentItem().text(0)
        node_id = self.ui.treeMain.currentItem().text(1)

        self.curr_page = 1
        self.handle_nextprev_buttons()

        if node_id == 'reddfile':
            reddurl = path.join(self.redd_dir, node_title)
            self.setWindowTitle(f'{self.version_str} - {reddurl}')
            self.ui.webEngine.load(QUrl.fromLocalFile(reddurl))
        elif node_id == 'folder':
            # two options - either expand whole folder as if expand widget was clicked
            # or generate new sorted page for all feeds in that folder. Or both?
            self.setWindowTitle(f'{self.version_str}')
            curr_node = self.ui.treeMain.findItems(node_title, Qt.MatchContains, 0)[0]
            curr_state = curr_node.isExpanded()
            curr_node.setExpanded(not curr_state)
        else:
            #print(f'Tree clicked - {node_title} selected with ID {node_id}.')
            self.setWindowTitle(f'{self.version_str} - {node_title}')
            try:
                results = sqlitelib.get_feed_posts(node_id, self.db_curs, self.db_conn)
            except Exception as err:
                self.output(err)
            posthtml = self.generate_posts_page(results)
            self.ui.webEngine.setHtml(posthtml)
            # mark as read - change font, remove unread conunt, and update DB
            if '(' in node_title:
                node_title = node_title.rpartition('(')[0].strip()
                self.ui.treeMain.currentItem().setText(0, node_title)
                self.ui.treeMain.currentItem().setFont(0, QFont('Segoe UI', 10))
                #QQQQ - should ideally add to a thread manager
                try:
                    sqlitelib.mark_feed_read(node_id, self.db_curs, self.db_conn)
                except Exception as err:
                    self.output(f'Error - failed to update read status of {node_title}: {err}')

    def tree_hover(self, item):
        if item.text(1) != 'folder':
            self.ui.statusbar.showMessage(f'{item.text(0)} - {item.text(1)}')

    def view_most_recent(self, num=100):
        self.output(f'Showing {num} most recent posts.')
        startposts = sqlitelib.get_most_recent(num, self.db_curs, self.db_conn)[1:] #trim first, Wertzone promo post
        posthtml = self.generate_posts_page(startposts)
        self.ui.webEngine.setHtml(posthtml)

    def maintain_DB(self):
        self.ui.statusbar.showMessage('Running DB maintenance.')
        sqlitelib.vacuum(self.db_conn)

    def mark_older(self):
        sqlitelib.mark_old_as_read(3, self.db_curs, self.db_conn)
        self.setup_tree()

    def find_in_page(self, srchtext=None):
        #file_menu.addAction('&Find...', self.search_toolbar.show, shortcut=QKeySequence.Find)
        #self.ui.find_in_page = QLineEdit()
        #self.ui.statusbar.addWidget(self.ui.find_in_page)
        #self.ui.find_in_page.setFocus()
        #flags = QWebEnginePage.FindFlags(0)
        #self.ui.webEngine.findText("new", flags)
        self.ui.search_toolbar.show()

    def update_all_feeds(self):
        flags = Qt.MatchContains | Qt.MatchRecursive
        #tree = self.ui.treeMain
        mainwin = self.ui
        #rsslib.retrieve_feeds(self.feedlist[:5], self.ui.treeMain, flags)

        if not is_internet_on():
            self.ui.statusbar.showMessage(f'Not connected to the Internet.')
            return

        q = Queue()
        DB_queue = Queue()
        numworkers = 10
        listsize = len(self.feedlist)
        #self.ui.progressBar.setMinimum(0)
        #self.ui.progressBar.setMaximum(listsize)

        for feed in self.feedlist:
            q.put(feed)

        for x in range(numworkers):
            t = threading.Thread(target=rsslib.worker, args=(listsize, x, q, DB_queue,\
                                 mainwin, flags, self.update_icon))
            t.start()

        DB_thread = threading.Thread(target=rsslib.DB_writer, args=[DB_queue, numworkers, self.dbfile, mainwin])
        DB_thread.start()

    def new_sub(self):
        # should verify url if possible, then add the feed to the DB,
        # load posts from the feed and refresh the tree. How to decide folders?
        # will probably need a custom dialog after all.
        newsubform = NewSubDialog(self)
        if newsubform.exec():
            newsub = newsubform.get_inputs()
            self.ui.statusbar.showMessage(f'Adding new subscription: {newsub.title} - {newsub.rss_url}')

    def mark_read(self):
        self.output(f'Mark feed {self.node_name} - {self.node_id} read.')

    def update_feed(self):
        self.output(f'Updating {self.node_name} id {self.node_id}')

    def search_feeds(self):
        srchdialog = SrchDialog(self)
        srchdialog.exec()
        if self.srchtext:
            self.output(f'Searching feeds DB for "{self.srchtext}" in {self.srchtime.lower()}.')
            results = sqlitelib.text_search(self.srchtext, 50, self.db_curs, self.db_conn, self.srchtime)
            if results:
                self.ui.statusbar.showMessage(f'{len(results)} results found.')
                posthtml = self.generate_posts_page(results)
                self.ui.webEngine.setHtml(posthtml)
            else:
                self.ui.statusbar.showMessage(f'No results found for search "{self.srchtext}"')

    def update_reddit(self):
        Popen(['python', r'D:\Python\Code\redditcrawl4.py'], creationflags=CREATE_NEW_CONSOLE)

    def unsubscribe_feed(self):
        #should pop up a dialog box to confirm
        if self.node_id not in ['folder', 'reddfile']:
            confirm = QMessageBox.question(self, "Unsubscribe from feed?",
                     "This will unsubscribe you from the feed and delete all saved posts. Are you sure?",
                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if confirm == QMessageBox.Yes:
                self.output(f'unsub from {self.node_id}')

    def generate_posts_page(self, results=None):
        # also needs some indicator of if feed has been read
        if results:
            self.results = results
        else:
            results = self.results

        page = ['<!DOCTYPE html><html><head><style>']
        style = load_css_file()
        page.append(style + '</style></head><body>')

        startpost = (self.curr_page - 1) * self.page_size
        endpost = self.curr_page * self.page_size
        self.max_page = int(len(results) / self.page_size) + (len(results) % self.page_size > 0)
        self.handle_nextprev_buttons()
        results = results[startpost:endpost]

        self.ui.labelPage.setFont(QFont("Segoe UI", 10, weight=QFont.Bold))
        self.ui.labelPage.setText(f'Page {self.curr_page} of {self.max_page}')

        if results:
            for post in results:
                convdate = convert_isodate_to_fulldate(post.date)
                page.append('<div class="post">'
                            f'<h4><a href="{post.url}">{post.title}</a></h4>'
                            f'<h5>{post.author} on {convdate}</h5>'
                            f'<p>{post.content}'
                            f'</div><hr class="new">')
        else:
            page.append('<h4>No results found.</h4>')
        page.append('</body></html>')

        page = ''.join(page)
        return page

    def next_page(self):
        if self.curr_page < self.max_page:
            self.curr_page += 1
            self.ui.buttonPrevPage.setDisabled(False)
            posthtml = self.generate_posts_page()
            self.ui.webEngine.setHtml(posthtml)
        if self.curr_page == self.max_page:
            self.ui.buttonNextPage.setDisabled(True)

    def prev_page(self):
        if self.curr_page > 1:
            self.curr_page -= 1
            self.ui.buttonNextPage.setDisabled(False)
            posthtml = self.generate_posts_page()
            self.ui.webEngine.setHtml(posthtml)
        if self.curr_page == 1:
            self.ui.buttonPrevPage.setDisabled(True)

    def handle_nextprev_buttons(self):
        if self.curr_page < self.max_page:
            self.ui.buttonPrevPage.setDisabled(False)
        if self.curr_page == self.max_page:
            self.ui.buttonNextPage.setDisabled(True)
        if self.curr_page > 1:
            self.ui.buttonNextPage.setDisabled(False)
        if self.curr_page == 1:
            self.ui.buttonPrevPage.setDisabled(True)

    @pyqtSlot(str, QWebEnginePage.FindFlag)
    def on_searched(self, text, flag):
        def callback(found):
            if text and not found:
                self.ui.statusbar.showMessage(f'String "{text}" not found')
            else:
                self.ui.statusbar.showMessage(f'')
        self.ui.webEngine.findText(text, flag, callback)

#=========================================================================

class SrchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.srchtext = ''
        self.srchtime = ''
        self.ui = Ui_frmSearch()
        self.ui.setupUi(self)
        self.ui.lineSubSearch.setFocus()

        # Connect up the buttons
        self.ui.btnSearchOK.clicked.connect(self.ok_button)
        self.ui.btnSearchCancel.clicked.connect(self.cancel_button)

    def ok_button(self):
        srchstr = self.ui.lineSubSearch.text().strip()
        if srchstr:
            self.parent.srchtext = srchstr
            self.parent.srchtime = self.ui.cmbSearchTime.currentText()
        else:
            self.parent.srchtext = None
            self.parent.srchtime = None

        self.close()

    def cancel_button(self):
        self.parent.srchtext = None
        self.parent.srchtime = None
        self.close()

# ============================================================================

class NewSubDialog(QDialog):
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
            self.ui.lblFeedValid.setText('Checking feed...')
            self.ui.lblFeedValid.repaint()
            results = rsslib.validate_feed(feed_url)
            if type(results) == rsslib.Feed:
                if results.title not in [x.title for x in self.parent.feedlist]:
                    self.feed = results
                    self.ui.lineNewSubFeedUrl.setText(results.rss_url)
                    self.ui.lblFeedValid.setText('Feed is valid.')
                    self.ui.lineNewSubTitle.setText(results.title)
                    self.ui.btnNewSubOK.setDisabled(False)
                else:
                    self.ui.lblFeedValid.setText('Subscription already exists.')
            else:
                self.ui.lblFeedValid.setText('Feed URL is invalid.')

    def ok_button(self):
        #self.parent.srchtext = self.ui.lineSubSearch.text()
        #self.close()
        self.accept()

    def cancel_button(self):
        self.reject()

    def get_inputs(self):
        return self.feed

    def edit_feed_url(self):
        self.ui.lblFeedValid.setText('')

# ============================================================================

class SearchPanel(QWidget):
    searched = pyqtSignal(str, QWebEnginePage.FindFlag)
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super(SearchPanel, self).__init__(parent)
        lay = QHBoxLayout(self)
        #self.case_button = QPushButton('Match &Case', checkable=True)
        self.case_button = QCheckBox('Match &Case')
        next_button = QPushButton('&Next')
        prev_button = QPushButton('&Previous')
        done_button = QPushButton('&Done')
        self.search_le = QLineEdit()
        self.search_le.setFixedWidth(256)
        self.setFocusProxy(self.search_le)
        done_button.clicked.connect(self.closed)
        next_button.clicked.connect(self.update_searching)
        prev_button.clicked.connect(self.on_preview_find)
        self.case_button.clicked.connect(self.update_searching)
        for btn in (self.search_le, self.case_button, next_button, prev_button, done_button):
            lay.addWidget(btn)
            if isinstance(btn, QPushButton): btn.clicked.connect(self.setFocus)
        lay.addStretch(0.1)
        self.search_le.textChanged.connect(self.update_searching)
        self.search_le.returnPressed.connect(self.update_searching)
        self.closed.connect(self.search_le.clear)

        QShortcut(QKeySequence.FindNext, self, activated=next_button.animateClick)
        QShortcut(QKeySequence.FindPrevious, self, activated=prev_button.animateClick)
        QShortcut(QKeySequence(Qt.Key_Escape), self.search_le, activated=self.closed)

    @pyqtSlot()
    def on_preview_find(self):
        self.update_searching(QWebEnginePage.FindBackward)

    @pyqtSlot()
    def update_searching(self, direction=QWebEnginePage.FindFlag()):
        flag = direction
        if self.case_button.isChecked():
            flag |= QWebEnginePage.FindCaseSensitively
        self.searched.emit(self.search_le.text(), flag)

    def showEvent(self, event):
        super(SearchPanel, self).showEvent(event)
        self.setFocus(True)

# ============================================================================

def is_internet_on():
    try:
        response = urllib.request.urlopen('http://www.google.com', timeout=5)
        return True
    except urllib.error.URLError as err: pass
    return False

def convert_isodate_to_fulldate(isodate):
    formatstr = '%A, %d %B %Y %I:%M:%S %p'
    try:
        utctime = parse(isodate)
        localtz = tz.tzlocal()
        localtime = utctime.astimezone(localtz)
        return localtime.strftime(formatstr)
    except Exception as err:
        self.output(f'Timezone conversion error - {err}')
        return isodate

def load_css_file():
    try:
        with open(r'pagestyle.css', 'r') as cssfile:
            return cssfile.read()
    except Exception as err:
        self.output(f'Loading CSS file failed - {err}')

def load_data(infile):
    try:
        with open(infile, 'r') as infile:
            indata = infile.read()
        self.output('Data loaded.')
        return indata
    except Exception as err:
        self.output(f'{err}')

def exception_hook(exctype, value, traceback):
    self.output(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)

def main():
    app = QApplication(sys.argv)

    # set stylesheet
    file = QFile(":/dark/stylesheet.qss")
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    app.setStyleSheet(stream.readAll())

    sys._excepthook = sys.excepthook
    sys.excepthook = exception_hook

    Reader = ReaderUI()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
