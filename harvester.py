# - add generated newest posts page to folder list
# - start reddcrawl automatically and rewrite for JIT deletion of subredds, not mass
#   wipe of whole directory on start
# - add subprocess call of reddcrawler
# create dict for last read post date - also needs to fill in for feeds with no posts read
# DB maintenance - if > 50 unread posts, start culling?
# another report for out-of-date feeds might be handy.
# add sample feeds from https://github.com/plenaryapp/awesome-rss-feeds
# tools - report on, and delete all dead feeds. Dead culd be no posts at all, or
# no posts in last X years.
# delete folder and all feeds in it?

import sys
import threading
import urllib.request
import rsslib
import sqlitelib
import resources.breeze_resources

from PyQt5 import QtGui
from PyQt5.QtCore import (Qt, QSettings, QUrl, QFile, QTextStream, pyqtSignal,
                         pyqtSlot)
from PyQt5.QtGui import QFont, QIcon, QDesktopServices, QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QTreeView, QPushButton, QMainWindow,
                             QTreeWidgetItem, QMenu, QAction, QDialog,
                             QLineEdit, QLabel, QMessageBox, QInputDialog, QWidget,
                             QToolBar, QHBoxLayout, QShortcut, QCheckBox, QFileDialog)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from functools import partial
from os import listdir, path, getcwd
from dateutil.parser import *
from dateutil import tz
from datetime import datetime
from queue import Queue
from subprocess import Popen
from ui.harvester_main import Ui_MainWindow
from ui.harvsearch import Ui_frmSearch
from ui.harvnewsub import Ui_frmNewSub

class CustomWebEnginePage(QWebEnginePage):
    # Custom WebEnginePage to customize how we handle link navigation
    def acceptNavigationRequest(self, url,  _type, isMainFrame):
        if _type == QWebEnginePage.NavigationTypeLinkClicked:
            # Send the URL to the system default URL handler.
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url,  _type, isMainFrame)

class ReaderUI(QMainWindow):
    version_str = 'Harvester 0.1'
    console_output = True
    db_filename = None
    node_name, node_id = '', ''
    web_zoom = 1.25
    pagenav_icon_size = 20
    anchor_id = 0
    srchtext = ''
    page_size = 10 # how many posts to a page
    curr_page = 1
    max_page = 1
    results = []
    last_read = {}
    redd_dir = ''
    first_run_mode = True

    def __init__(self):
        super(ReaderUI, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.webEngine = QWebEngineView()
        self.ui.webEngine.setPage(CustomWebEnginePage(self))
        self.ui.splitter.addWidget(self.ui.webEngine)

        # hides title bar - looks nice, but annoying in practice
        #self.setWindowFlag(Qt.FramelessWindowHint)

        self.ui.buttonNextPage = QPushButton('')
        #self.ui.buttonNextPage.setIcon(QIcon(':/icons/icons/icons8-fast-forward-100.png'))
        self.ui.buttonNextPage.setStyleSheet("border-image : "
                                             "url(:/icons/icons/icons8-fast-forward-100.png);")
        self.ui.labelPage = QLabel()
        self.ui.buttonPrevPage = QPushButton('')
        #self.ui.buttonPrevPage.setIcon(QIcon(':/icons/icons/icons8-rewind-100.png'))
        self.ui.buttonPrevPage.setStyleSheet("border-image : "
                                             "url(:/icons/icons/icons8-rewind-100.png);")

        self.ui._search_panel = SearchPanel()
        self.ui.search_toolbar = QToolBar()
        self.ui.search_toolbar.addWidget(self.ui._search_panel)
        self.addToolBar(Qt.BottomToolBarArea, self.ui.search_toolbar)
        #self.ui.statusbar.addWidget(self.ui.search_toolbar)
        self.ui.search_toolbar.hide()
        self.ui._search_panel.searched.connect(self.on_searched)
        self.ui._search_panel.closed.connect(self.ui.search_toolbar.hide)

        self.initializeUI()
        self.load_previous_state()
        self.init_data()
        self.show()

    def initializeUI(self):
        self.ui.treeMain.setMouseTracking(True)
        self.ui.treeMain.itemClicked.connect(self.tree_click)
        self.ui.treeMain.itemEntered.connect(self.tree_hover)
        self.ui.treeMain.itemExpanded.connect(lambda node: self.collapse_other_folders(node))
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
        self.feedProperties = QAction('View Feed Properies', self)
        self.actionSearch_Selected_Feed = QAction('Search Current Feed', self)

        #connect actions
        self.newSubAction.triggered.connect(self.new_sub)
        self.markReadAction.triggered.connect(self.mark_read)
        self.updateFeedAction.triggered.connect(self.update_feed)
        self.unsubAction.triggered.connect(self.unsubscribe_feed)
        self.feedProperties.triggered.connect(self.view_feed_properties)
        self.actionSearch_Selected_Feed.triggered.connect(self.search_single_feed)

        # search box
        self.ui.lineSearch.textChanged.connect(self.search_feed_names)

        # menu items
        # File
        self.ui.actionSubscribe.triggered.connect(self.new_sub)
        self.ui.actionNew_Fold.triggered.connect(self.new_folder)
        #self.ui.actionDelete_Folder_2.triggered.connect(self.delete_folder)
        self.ui.actionImport_Feeds.triggered.connect(self.import_feeds_from_opml)
        self.ui.actionExport_Feeds.triggered.connect(self.export_feeds_to_opml)
        self.ui.actionCreate_Database.triggered.connect(self.create_db)
        self.ui.actionLoad_Database.triggered.connect(self.menu_load_db)
        #self.ui.actionDelete_Older_Posts.triggered.connect(self.delete_older_posts)
        self.ui.actionDatabase_Maintenance.triggered.connect(self.maintain_DB)
        self.ui.actionSelect_Reddit_Directory.triggered.connect(self.locate_reddit_dir)
        self.ui.actionExit.triggered.connect(self.exit_app)

        # Edit
        #self.ui.actionMark_All_Feeds_Read.triggered.connect(self.mark_all)
        self.ui.actionMark_Older_As_Read.triggered.connect(self.mark_older)
        self.ui.actionFind_in_Page.triggered.connect(self.find_in_page)

        # View
        self.ui.actionMost_Recent.triggered.connect(lambda: self.view_most_recent(100))
        self.ui.actionIncrease_Text_Size.triggered.connect(self.increase_text_size)
        self.ui.actionDecrease_Text_Size.triggered.connect(self.decrease_text_size)

        # Tools
        self.ui.actionUpdate_All_Feeds.triggered.connect(self.update_all_feeds)
        self.ui.actionUpdate_Current_Feed.triggered.connect(self.update_feed)
        self.ui.actionUpdate_Reddit.triggered.connect(self.update_reddit)
        self.ui.actionSearch_Feeds.triggered.connect(self.search_feeds)
        self.ui.actionSearch_Selected_Feed.triggered.connect(self.search_single_feed)
        self.ui.actionUsage_Report.triggered.connect(self.usage_report)
        self.ui.actionDead_Feeds_Report.triggered.connect(self.dead_feeds_report)
        #options
        self.ui.actionAbout_Harvester.triggered.connect(self.about_harv)

        #setup status bar
        self.ui.buttonPrevPage.setDisabled(True) #start with prev button disabled
        self.ui.statusbar.addPermanentWidget(self.ui.buttonPrevPage)
        self.ui.statusbar.addPermanentWidget(self.ui.labelPage)
        self.ui.statusbar.addPermanentWidget(self.ui.buttonNextPage)
        self.ui.buttonNextPage.clicked.connect(self.next_page)
        self.ui.buttonPrevPage.clicked.connect(self.prev_page)

        self.dl_icon = QIcon(':/icons/icons/icons8-download-100.png')
        self.folder_icon = QIcon(':/icons/icons/icons8-folder-100.png')
        self.update_icon = QIcon(':/icons/icons/icons8-right-arrow-100.png')

        self.ui.webEngine.page().linkHovered.connect(self.link_hover)
        self.ui.webEngine.page().urlChanged.connect(lambda url: self.url_change(url))
        self.ui.webEngine.loadFinished.connect(self.finalize_page)
        self.ui.webEngine.setZoomFactor(self.web_zoom)

    def init_data(self):
        self.load_db_file(self.db_filename)
        self.load_feed_data()
        self.locate_reddit_dir()
        self.setup_tree()
        self.view_most_recent()
        #self.update_all_feeds()

    def link_hover(self, url):
        if 'data:text/html;' in url:
            self.ui.statusbar.showMessage(f'Jump to next/previous post.')
        else:
            self.ui.statusbar.showMessage(f'{url}')

    def url_change(self, url):
        url_str = str(url)
        if '#anchor' in url_str:
            a, b, anchor_id = url_str.rpartition('#anchor')
            anchor_id = int(anchor_id.split("')")[0])

            anchor_target_page = anchor_id // self.page_size + 1
            if anchor_target_page < self.curr_page: # go back
                self.ui.buttonPrevPage.click()
                self.anchor_id = anchor_id
                self.finalize_page()

            elif anchor_target_page > self.curr_page: # go forwards
                self.ui.buttonNextPage.click()

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
        menu.addAction(self.newSubAction)
        self.newSubAction.setStatusTip("Subscribe to a new RSS feed.")
        menu.addAction(self.ui.actionNew_Fold)
        self.ui.actionNew_Fold.setStatusTip("Create a new folder to store feeds in.")

        if self.node_id not in ['folder', 'reddfile']: # we are on an individual feed
            menu.addSeparator()
            menu.addAction(self.updateFeedAction)
            self.updateFeedAction.setStatusTip("Update the current feed.")
            menu.addAction(self.markReadAction)
            self.actionSearch_Selected_Feed.setStatusTip("Search the current feed.")
            menu.addAction(self.actionSearch_Selected_Feed)
            self.markReadAction.setStatusTip("Mark current feed as read.")
            menu.addAction(self.unsubAction)
            self.unsubAction.setStatusTip("Unsubscribe from the current feed.")
            menu.addAction(self.feedProperties)

            curr_node = [x for x in self.feedlist if x.feed_id == self.node_id][0]

            #menu.addAction("Choice 2")
            #menu.addAction("Choice 3")
            menu.addSeparator()

            move_folder = menu.addMenu('Move to Folder')
            move_folder.hovered.connect(self.movefolder)

            folder_options = self.folderlist
            for f in folder_options:
                if f != curr_node.folder:
                    tmp_action = move_folder.addAction(f)
                    tmp_action.triggered.connect(partial(self.move_to_folder, curr_node, f))
            if curr_node.folder != None and curr_node.folder != '':
                sep = move_folder.addSeparator()
                no_folder = move_folder.addAction('None (remove from current folder)')
                no_folder.triggered.connect(partial(self.move_to_folder, curr_node, None))

        menu.exec_(self.ui.treeMain.mapToGlobal(position))

    def move_to_folder(self, feed, folder_name):
        self.output(f'Moving feed {feed.feed_id} to {folder_name} folder.')
        sqlitelib.update_feed_folder(feed.feed_id, folder_name, self.db_curs, self.db_conn)
        feed.folder = folder_name
        self.setup_tree()

    def movefolder(self, folder_name):
        self.ui.statusbar.showMessage(f'Move current feed to this folder.')

    def search_feed_names(self):
        srchtext = self.ui.lineSearch.text()
        if srchtext == '':
            self.setup_tree()
        else:
            try:
                self.generate_filtered_tree(srchtext)
            except Exception as err:
                self.output(f'{err}')

    def finalize_page(self, anchor_jump_id=None):
        """Performs final text resize and internal page navigation once the page is loaded."""
        if not (isinstance(self.web_zoom, float) or isinstance(self.web_zoom, int)):
            self.output('Error retrieving previous zoom level - value was ' +
                       f'{self.web_zoom}. Setting to default of 125%.')
            self.web_zoom = 1.25
        self.ui.webEngine.setZoomFactor(self.web_zoom)

        if self.anchor_id > 0:
            anchor_str = f'anchor{self.anchor_id}'
            prev_js = f"document.getElementById('{anchor_str}').scrollIntoView();"
        else: # new feed, so just jump to top
            prev_js = 'window.scroll(0, 0)'
        self.ui.webEngine.page().runJavaScript(prev_js)

    def increase_text_size(self):
        self.web_zoom += 0.05
        self.finalize_page()
        self.ui.statusbar.showMessage(f'Screen zoom increased to {round(self.web_zoom*100)}%')

    def decrease_text_size(self):
        self.web_zoom -= 0.05
        self.finalize_page()
        self.ui.statusbar.showMessage(f'Screen zoom decreased to {round(self.web_zoom*100)}%')

    def load_previous_state(self):
        settings = QSettings('Hypogeum', 'Harvester')
        if settings.allKeys() != []:
            self.first_run_mode = False
            self.restoreGeometry(settings.value('geometry'))
            self.restoreState(settings.value("windowState"))
            self.ui.splitter.restoreState(settings.value("splitterSizes"))
            self.db_filename = settings.value('db_location')
            self.redd_dir = settings.value('redd_dir')
            zoom = settings.value('web_zoom')
            try:
                self.web_zoom = float(zoom) if zoom else 1.25
            except:
                self.web_zoom = 1.25

    def save_state(self):
        # save program size and position on exit
        # save treeview state at some stage?
        settings = QSettings('Hypogeum', 'Harvester')
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("splitterSizes", self.ui.splitter.saveState())
        settings.setValue("db_location", self.db_filename)
        settings.setValue("redd_dir", self.redd_dir)
        settings.setValue("web_zoom", self.web_zoom)

    def locate_db(self):
        get_db_msg = QMessageBox(self)
        get_db_msg.setWindowTitle("Create or Locate Database")
        get_db_msg.setIcon(QMessageBox.Critical)

        if self.first_run_mode:
            msg = ("As this is Harvester's first run, you can either create a "
                   "database, or load a previously created database.")
        else:
            msg = 'The previous database could not be found.'
        get_db_msg.setText(msg)
        btn_create_db = get_db_msg.addButton('Create DB', QMessageBox.AcceptRole)
        btn_load_db = get_db_msg.addButton('Load DB', QMessageBox.AcceptRole)
        btn_quit = get_db_msg.addButton('Quit', QMessageBox.DestructiveRole)
        get_db_msg.exec_()
        get_db_msg.deleteLater()

        if get_db_msg.clickedButton() is btn_create_db:
            return self.create_db()
        if get_db_msg.clickedButton() is btn_load_db:
            return self.load_db_dlg()
        else:
            sys.exit(0) # still in init loop, so need more forceful exit.

    def load_db_file(self, db_filename):
        if not db_filename:
            db_filename = self.locate_db()
        self.output(f'Loading DB file {db_filename}')
        db = sqlitelib.connect_DB(db_filename)
        while not db:
            self.output(f'Attempt to load DB file {db_filename} failed.')
            self.db_filename = None
            db_filename = self.locate_db()
            db = sqlitelib.connect_DB(db_filename)

        self.db_curs, self.db_conn = db[0], db[1]
        self.db_filename = db_filename

    def load_db_dlg(self):
        dlg = QFileDialog.getOpenFileName(self, "Open Database", "", \
            "DB Files (*.db);;All files (*.*)")
        if dlg[0] != '':
            return dlg[0]
            '''
            if self.load_db_file(dlg[0]):
                self.db_filename = dlg[0]
                self.output('Setting DB file to {dlg[0]}.')
            '''
        else: #cancelled dialog
            self.output('Loading file cancelled.')
            return None

    def menu_load_db(self):
        fname = self.load_db_dlg()
        self.load_db_file(fname)
        self.load_feed_data()
        self.setup_tree()
        self.curr_page = 1
        self.view_most_recent()

    def locate_reddit_dir(self, skip_query=True):
        if not self.redd_dir:
            self.output('Locating Reddit directory.')
            rd = str(QFileDialog.getExistingDirectory(self, "Select Reddit Directory"))
            if rd:
                self.redd_dir = rd
                self.setup_tree()

    def closeEvent(self, event):
        self.save_state()
        self.close()

    def load_feed_data(self):
        self.feedlist = rsslib.import_feeds_from_db(self.db_curs, self.db_conn)
        # find all folders
        self.folderlist = set([x.folder for x in self.feedlist if x.folder not in [None, '']])
        self.folderlist = sorted(self.folderlist)

    def setup_tree(self):
        # Need to evaluate unread count - worth doing every time?
        unread_count = sqlitelib.count_all_unread(self.db_curs, self.db_conn)

        # QQQQ find the date/time of the newest post that has been read, for each feed
        # this is so worker threads can update tree with unread numbers
        self.collate_feeds_last_read()

        self.ui.treeMain.clear()

        for f in self.folderlist:
            foldernode = QTreeWidgetItem(self.ui.treeMain, [f, 'folder'])
            foldernode.setFont(0, QFont("Segoe UI", 10, weight=QFont.Bold))
            foldernode.setIcon(0, QIcon(':/icons/icons/icons8-folder-100.png'))
            for feed in [x for x in self.feedlist if x.folder == f]:
                unread_count_str = f' ({unread_count[feed.feed_id]})' if feed.feed_id in unread_count else ''
                newnode = QTreeWidgetItem(foldernode, [f'{feed.title}{unread_count_str}', feed.feed_id])
                fontweight = QFont.Bold if unread_count_str else False
                newnode.setFont(0, QFont('Segoe UI', 10, fontweight))
                if unread_count_str:
                    newnode.setIcon(0, QIcon(':/icons/icons/icons8-open-book-100-2.png'))

        # add folderless feeds?
        for feed in [x for x in self.feedlist if x.folder in [None, '']]:
            unread_count_str = f' ({unread_count[feed.feed_id]})' if feed.feed_id in unread_count else ''
            newnode = QTreeWidgetItem(self.ui.treeMain, [f'{feed.title}{unread_count_str}', feed.feed_id])
            fontweight = QFont.Bold if unread_count_str else False
            newnode.setFont(0, QFont("Segoe UI", 10, fontweight))
            if unread_count_str: # doesn't work due to style sheet
                    newnode.setIcon(0, QIcon(':/icons/icons/icons8-open-book-100-2.png'))

        # add redd folder
        if self.redd_dir:
            foldernode = QTreeWidgetItem(self.ui.treeMain, ['ReddFiles', 'folder'])
            foldernode.setFont(0, QFont("Segoe UI", 10, weight=QFont.Bold))
            foldernode.setIcon(0, QIcon(':/icons/icons/icons8-reddit-100-2.png'))
            reddfiles = sorted(listdir(self.redd_dir), key = lambda x:x.lower())
            for rf in reddfiles:
                newnode = QTreeWidgetItem(foldernode, [f'{rf}', 'reddfile'])
                newnode.setFont(0, QFont("Segoe UI", 10))

    def generate_filtered_tree(self, srchtext):
        self.output(f'Searching for feeds with {srchtext} in name...')
        unread_count_dict = sqlitelib.count_filtered_unread(srchtext, self.db_curs, self.db_conn)
        self.ui.treeMain.clear()
        srchtext = srchtext.lower()

        for feed in self.feedlist:
            if srchtext in feed.title.lower():
                if feed.feed_id in unread_count_dict:
                    unread_count_str = f'({unread_count_dict[feed.feed_id]})'
                else:
                    unread_count_str = ''
                newnode = QTreeWidgetItem(self.ui.treeMain, [f'{feed.title} {unread_count_str}', feed.feed_id])
                fontweight = QFont.Bold if unread_count_str else False
                newnode.setFont(0, QFont('Segoe UI', 10, fontweight))
                self.ui.treeMain.addTopLevelItem(newnode)

        # add redd folder
        if self.redd_dir:
            reddfiles = listdir(self.redd_dir)
            for rf in reddfiles:
                if srchtext in rf:
                    newnode = QTreeWidgetItem(self.ui.treeMain, [f'{rf}', 'reddfile'])
                    newnode.setFont(0, QFont('Segoe UI', 10))

    def collate_feeds_last_read(self):
        # QQQQ for each feed, gets the date of the last read post
        last_read = sqlitelib.find_date_all_feeds_last_read(self.db_curs, self.db_conn)
        for f in self.feedlist:
            if f.feed_id in last_read:
                f.last_read = last_read[f.feed_id]

    def exit_app(self):
        self.output('Exiting app...')
        self.close()

    def create_db(self):
        # QQQQ offer to add sample feeds to new DB
        try:
            dlg = QFileDialog.getSaveFileName(self, "Create New Database")
            if dlg:
                new_db = dlg[0]
        except Exception as err:
            self.output(f'{err}')
        if new_db:
            if sqlitelib.create_DB(new_db):
                self.output(f'New database {new_db} created.')
                loadnew = QMessageBox.question(self, "Load new DB?",
                          "Would you like to load the new database?",
                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if loadnew == QMessageBox.Yes:
                    '''
                    load_sample = QMessageBox.question(self, "Import Sample Feeds?",
                                  "Would you like to add some sample feeds to the "
                                  "new database? If not, the new database will be empty.",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if load_sample == QMessageBox.Yes:
                        #new, dupes = rsslib.import_opml_to_db(dlg[0], self.feedlist, self.db_curs, self.db_conn)
                        pass
                    '''
                    self.db_filename = new_db
                    self.db_curs, self.db_conn = sqlitelib.connect_DB(new_db)
                    self.init_data()
                return self.db_filename

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
            self.ui.webEngine.setZoomFactor(self.web_zoom)
            self.ui.webEngine.load(QUrl.fromLocalFile(reddurl))
            self.curr_page, self.max_page = 1, 1
            self.ui.labelPage.setText(f'Page 1 of 1')
            self.handle_nextprev_buttons()
        elif node_id == 'folder':
            # two options - either expand whole folder as if expand widget was clicked
            # or generate new sorted page for all feeds in that folder. Or both?
            self.setWindowTitle(f'{self.version_str}')
            curr_node = self.ui.treeMain.findItems(node_title, Qt.MatchContains, 0)[0]
            curr_state = curr_node.isExpanded()
            curr_node.setExpanded(not curr_state)
        else:
            #print(f'Tree clicked - {node_title} selected with ID {node_id}.')
            self.anchor_id = 0
            self.setWindowTitle(f'{self.version_str} - {node_title}')
            try:
                results = sqlitelib.get_feed_posts(node_id, self.db_curs, self.db_conn)
                self.results = results
            except Exception as err:
                self.output(err)
            posthtml = self.generate_posts_page(results)
            self.ui.webEngine.setHtml(posthtml)
            # mark as read - change font, remove icon and unread conunt, and update DB
            if '(' in node_title:
                node_title = node_title.rpartition('(')[0].strip()
                self.ui.treeMain.currentItem().setText(0, node_title)
                self.ui.treeMain.currentItem().setFont(0, QFont('Segoe UI', 10))
                self.ui.treeMain.currentItem().setIcon(0, QIcon())
                #QQQQ - should ideally add to a thread manager
                try:
                    sqlitelib.mark_feed_read(node_id, self.db_curs, self.db_conn)
                except Exception as err:
                    self.output(f'Error - failed to update read status of {node_title}: {err}')

    def collapse_other_folders(self, curr_node):
        root = self.ui.treeMain.invisibleRootItem()
        for x in range(root.childCount()):
            node = root.child(x)
            if node.text(1) == 'folder' and node != curr_node:
                node.setExpanded(False)
        self.ui.treeMain.scrollToItem(curr_node)

    def tree_hover(self, item):
        if item.text(1) != 'folder':
            self.ui.statusbar.showMessage(f'{item.text(0)} - {item.text(1)}')

    def view_most_recent(self, num=100):
        self.output(f'Showing {num} most recent posts.')
        startposts = sqlitelib.get_most_recent(num, self.db_curs, self.db_conn)
        if not startposts:
            self.results = []
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

        DB_thread = threading.Thread(target=rsslib.DB_writer,
                                     args=[DB_queue, numworkers, self.db_filename, mainwin])
        DB_thread.start()

    def new_sub(self):
        # QQQQ should probably use threading for instances where other DB activity is happening
        newsubform = NewSubDialog(self)
        if newsubform.exec():
            newsub = newsubform.get_inputs()
            self.ui.statusbar.showMessage(f'Adding new subscription: {newsub.title} - '
                                          f'{newsub.rss_url} to folder {newsub.folder}')
            sqlitelib.write_feed(newsub, self.db_curs, self.db_conn)
            self.update_feed(newsub)
            self.load_feed_data()
            self.setup_tree()
            #QQQQ need to add to tree, refresh

    def mark_read(self):
        self.output(f'Mark feed {self.node_name} - {self.node_id} read.')

    def import_feeds_from_opml(self):
        dlg = QFileDialog.getOpenFileName(self, "Open OPML File", "", \
            "OPML Files (*.opml);;All files (*.*)")
        if dlg[0] != '':
            new, dupes = rsslib.import_opml_to_db(dlg[0], self.feedlist, self.db_curs, self.db_conn)
            if new:
                self.load_feed_data()
                self.setup_tree()
                self.update_all_feeds()
                self.setup_tree()
                msg = f'Imported {new} new feeds'
                add = '.' if not dupes else f' and skipped {dupes} duplicates.'
                self.ui.statusbar.showMessage(msg + add)
            else:
                self.ui.statusbar.showMessage(f'Feed import failed.')

    def export_feeds_to_opml(self):
        opml = []

        dlg = QFileDialog.getSaveFileName(self, "Save OPML File", "", \
            "OPML Files (*.opml);;All files (*.*)")
        if dlg[0] != '':
            fname = dlg[0]
        else:
            return

        timestr = datetime.now().strftime('%a, %d %b %Y %I:%M:%S %p %Z')
        opml.append('<opml version="1.1">\n\t<head>\n\t\t<title>Harvester Subscriptions</title>\n\t\t'
                    f'<dateModified>{timestr}</dateModified>\n\t</head>\n\t<body>\n')
        for folder in self.folderlist:
            opml.append(f'\t\t<outline text="{folder}">\n')
            for feed in [x for x in self.feedlist if x.folder == folder]:
                feed = feed.sanitize()
                opml.append(f'\t\t\t<outline text="{feed.title}" title="{feed.title}" '
                            f'type="{feed.f_type}" xmlUrl="{feed.rss_url}" '
                            f'htmlUrl="{feed.html_url}"/>\n')
            opml.append('\t\t</outline>\n')

        # folderless feeds
        for feed in [x for x in self.feedlist if x.folder in [None, '']]:
            feed = feed.sanitize()
            opml.append(f'\t\t<outline text="{feed.title}" title="{feed.title}" '
                        f'type="{feed.f_type}" xmlUrl="{feed.rss_url}" '
                        f'htmlUrl="{feed.html_url}"/>\n')

        opml.append('\t</body>\n</opml>')

        opml = ''.join(opml)
        with open(fname, 'w') as outfile:
            outfile.write(opml)

        self.ui.statusbar.showMessage(f'Feeds exported to file {fname}.')

    def update_feed(self, feed=None):
        if not feed:
            node_id = self.ui.treeMain.currentItem().text(1)
            feed = [x for x in self.feedlist if x.feed_id == node_id][0]
        self.output(f'Updating {feed.title}')
        self.ui.statusbar.showMessage(f'Updating {feed.title}')
        rsslib.retrieve_feed(feed, self.db_curs, self.db_conn)
        sqlitelib.get_feed_posts(feed.feed_id, self.db_curs, self.db_conn)

    def search_feeds(self):
        srchdialog = SrchDialog(self)
        srchdialog.exec()
        if self.srchtext:
            self.output(f'Searching feeds DB for "{self.srchtext}" in {self.srchtime.lower()}.')
            results = sqlitelib.text_search(self.srchtext, self.db_curs, self.db_conn, 100, self.srchtime)
            if results:
                self.ui.statusbar.showMessage(f'{len(results)} results found.')
                posthtml = self.generate_posts_page(results)
                self.ui.webEngine.setHtml(posthtml)
            else:
                self.ui.statusbar.showMessage(f'No results found for search "{self.srchtext}"')

    def search_single_feed(self):
        if self.ui.treeMain.currentItem():
            node_title = self.ui.treeMain.currentItem().text(0)
            node_id = self.ui.treeMain.currentItem().text(1)

            srchdialog = SrchDialog(self)
            srchdialog.exec()
            if self.srchtext:
                self.output(f'Searching {node_title} for "{self.srchtext}" in {self.srchtime.lower()}.')
                results = sqlitelib.text_search(self.srchtext, self.db_curs, self.db_conn, 100, self.srchtime, node_id)
                if results:
                    self.ui.statusbar.showMessage(f'{len(results)} results found.')
                    posthtml = self.generate_posts_page(results)
                    self.ui.webEngine.setHtml(posthtml)
                else:
                    self.ui.statusbar.showMessage(f'No results found for search "{self.srchtext}"')
        else:
            self.ui.statusbar.showMessage(f'No feed currently selected.')

    def update_reddit(self):
        # QQQQ should locate correct file
        Popen(['python', r'D:\Python\Code\redditcrawl4.py'], shell=True)

    def unsubscribe_feed(self):
        if self.node_id not in ['folder', 'reddfile']:
            confirm = QMessageBox.question(self, "Unsubscribe from feed?",
                     "This will unsubscribe you from the feed and delete all saved posts. Are you sure?",
                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if confirm == QMessageBox.Yes:
                delfeed = [x for x in self.feedlist if x.feed_id == self.node_id][0]
                self.feedlist.remove(delfeed)
                res = sqlitelib.delete_feed(delfeed, self.db_curs, self.db_conn)
                if res:
                    self.output(f'Unsubscribed from {delfeed.feed_id}.')
                    self.ui.statusbar.showMessage(f'Unsubscribed from {delfeed.feed_id}.')
                    self.load_feed_data()
                    self.setup_tree()

    def generate_jump_buttons(self, anchor_id):
        anchor = ''
        if anchor_id < len(self.results) - 1:
            anchor = (f'<a href="#anchor{anchor_id+1}"><img alt="Next" '
                       'style="float:right" title="Next post" '
                       'src="qrc:/icons/icons/icons8-download-100-3.png" '
                      f'width="{self.pagenav_icon_size}" height="{self.pagenav_icon_size}"></a>')
        if anchor_id != 0:
            anchor += (f'<a href="#anchor{anchor_id-1}"><img alt="Prev" '
                        'style="float:right" title="Previous post" '
                        'src="qrc:/icons/icons/icons8-upload-100-2.png" '
                       f'width="{self.pagenav_icon_size}" height="{self.pagenav_icon_size}"></a>')
        return anchor

    def generate_posts_page(self, results=None):
        if results: # cache results
            self.results = results
        else:
            results = self.results

        page = ['<!DOCTYPE html><html><head>']
        if style := load_css_file():
            page.append('<style>' + style + '</style>')
        page.append('</head><body>')

        startpost = (self.curr_page - 1) * self.page_size
        endpost = self.curr_page * self.page_size
        self.max_page = int(len(results) / self.page_size) + (len(results) % self.page_size > 0)
        self.max_page = max(self.max_page, 1)
        self.handle_nextprev_buttons()
        results = results[startpost:endpost]
        anchor_id = startpost

        self.ui.labelPage.setFont(QFont("Segoe UI", 10, weight=QFont.Bold))
        self.ui.labelPage.setText(f'Page {self.curr_page} of {self.max_page}')

        if results:
            for post in results:
                convdate = convert_isodate_to_fulldate(post.date)
                anchortext = self.generate_jump_buttons(anchor_id)
                isread = 'unread' if post.flags == 'None' else 'read'
                page.append('<div class="post">'
                            f'<a id="anchor{anchor_id}" class="{isread}" href="{post.url}">{post.title}</a> '
                            f' {anchortext} '
                            f'<h5>{post.author} on {convdate}</h5>'
                            f'<p>{post.content}'
                            f'</div><hr class="new">')
                anchor_id += 1
        else:
            page.append('<h4>No results found.</h4>')
            self.handle_nextprev_buttons()
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
        self.ui.buttonNextPage.setDisabled(self.curr_page == self.max_page)
        self.ui.buttonPrevPage.setDisabled(self.curr_page == 1)

        if self.curr_page == self.max_page:
            self.ui.buttonNextPage.setStyleSheet("")
        else:
            self.ui.buttonNextPage.setStyleSheet("border-image : url(:/icons/icons/icons8-fast-forward-100.png);")

        if self.curr_page == 1:
            self.ui.buttonPrevPage.setStyleSheet("")
        else:
            self.ui.buttonPrevPage.setStyleSheet("border-image : url(:/icons/icons/icons8-rewind-100.png);")

    def new_folder(self):
        newfolder, ok = QInputDialog.getText(self, 'New Folder Name', 'Enter folder name:')
        if ok:
            #print(str(newfolder))
            newfoldernode = QTreeWidgetItem(self.ui.treeMain, [newfolder, 'folder'])
            newfoldernode.setFont(0, QFont("Segoe UI", 10, weight=QFont.Bold))
            newfoldernode.setIcon(0, QIcon(':/icons/icons/icons8-folder-100.png'))
            self.folderlist.append(newfolder)
            self.folderlist = sorted(self.folderlist)

    @pyqtSlot(str, QWebEnginePage.FindFlag)
    def on_searched(self, text, flag):
        def callback(found):
            if text and not found:
                self.ui.statusbar.showMessage(f'String "{text}" not found')
            else:
                self.ui.statusbar.showMessage(f'')
        self.ui.webEngine.findText(text, flag, callback)

    def format_filesize_str(self, fsize):
        if fsize > 10 ** 6:
            return f'{round(fsize / 1024 ** 2, 2):,} MB'
        else:
            return f'{round(fsize / 1024):,} KB'

    def usage_report(self):
        # make feed names clickable?
        report = sqlitelib.usage_report(self.db_curs, self.db_conn)
        page = ['<!DOCTYPE html><html><head>']
        if style := load_css_file():
            page.append('<style>' + style + '</style>')

        db_size = path.getsize(self.db_filename)

        page.append(f'<b>Total database size:</b> {self.format_filesize_str(db_size)}.<p>')
        page.append(f'<b>Total feeds:</b> {len(self.feedlist)}.<p>')
        mean_str = self.format_filesize_str(db_size / len(self.feedlist))
        page.append(f'<b>Mean feed size:</b> {mean_str}.<p><hr>')

        page.append('</head><body><h3>Feed Size Report</h3>'
                    '<table><tr><td>#</td><td><b><u>Feed Name</u></b></td>'
                    '<td><b><u>Space Used</u></b></td></tr>')
        for num, k in enumerate(report.items()):
            size = self.format_filesize_str(k[1])
            page.append(f'<tr><td>{num+1}.</td><td>{k[0]}</td><td>{size}</td></tr>')
        page.append('</table><p><hr>')

        postsrep = sqlitelib.list_feeds_over_post_count(100, self.db_curs, self.db_conn, True)
        page.append('<h3>Feeds With >100 Posts</h3>'
                     '<table><tr><td>#</td><td><b><u>Feed Name</u></b></td>'
                     '<td><b><u>Post Count</u></b></td></tr>')
        for num, k in enumerate(postsrep.items()):
            page.append(f'<tr><td>{num+1}.</td><td>{k[0]}</td><td>{k[1]}</td></tr>')
        page.append('</table>')

        page = ''.join(page)
        self.ui.webEngine.setHtml(page)
        self.curr_page, self.max_page = 1, 1
        self.ui.labelPage.setText(f'Page 1 of 1')
        self.handle_nextprev_buttons()

    def dead_feeds_report(self):
        dead = sqlitelib.find_dead_feeds(self.db_curs, self.db_conn)
        if dead:
            page = ['<!DOCTYPE html><html><head>']
            if style := load_css_file():
                page.append('<style>' + style + '</style>')

            page.append('<b>Dead Feeds</b><p><ol>')

            for k, v in dead.items():
                page.append(f'<li>{v}</li>')
            page.append('<//ol>')

            page = ''.join(page)
            self.ui.webEngine.setHtml(page)
            self.curr_page, self.max_page = 1, 1
            self.ui.labelPage.setText(f'Page 1 of 1')
            self.handle_nextprev_buttons()

    def view_feed_properties(self):
        pass

    def about_harv(self):
        #Information page for the program
        about = QMessageBox(self)
        about.setWindowTitle("About Harvester")
        about.setTextFormat(Qt.RichText)
        about.setIconPixmap(QPixmap(':/icons/icons/icons8-combine-harvester-100-2.png'))
        about.setText('<h4>Harvester 0.1</h4>A cross-platform RSS reader.<p style="margin-bottom: -20px;">Credits:'
                      '<ul style="margin-left: -30px; margin-top: -20px;">'
                      '<li>Icons from <a href="https://icons8.com">Icons8</a>'
                      '<li>Dark theme is <a href="https://github.com/ColinDuquesnoy/'
                      'QDarkStyleSheet">QDarkStylesheet</a></ul>')
        about.setStandardButtons(QMessageBox.Ok)
        about.setDefaultButton(QMessageBox.Ok)
        about.exec_()
        about.deleteLater()

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
            if feed_url not in [x.rss_url for x in self.parent.feedlist]:
                self.ui.lblFeedValid.setText('Checking feed...')
                self.ui.lblFeedValid.repaint()
                results = rsslib.validate_feed(feed_url)
                if type(results) == rsslib.Feed:
                    #if results.title not in [x.title for x in self.parent.feedlist]:
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
        lay.addStretch(1)
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
        print(f'Timezone conversion error - {err}')
        return isodate

def load_css_file():
    cssfilename = path.join(getcwd(), 'resources', 'pagestyle.css')
    try:
        with open(cssfilename, 'r') as cssfile:
            return cssfile.read()
    except Exception as err:
        print(f'Loading CSS file failed - {err}')

def load_data(infile):
    try:
        with open(infile, 'r') as infile:
            indata = infile.read()
        self.output('Data loaded.')
        return indata
    except Exception as err:
        print(f'{err}')

def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
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
