# - add generated newest posts page to folder list
# - start reddcrawl automatically and rewrite for JIT deletion of subredds, not mass
#   wipe of whole directory on start
# - add subprocess call of reddcrawler
# create dict for last read post date - also needs to fill in for feeds with no posts read
# DB maintenance - if > 50 unread posts, start culling?
# another report for out-of-date feeds might be handy.
# add sample feeds from https://github.com/plenaryapp/awesome-rss-feeds
# tools - report on, and delete all dead feeds. Dead could be no posts at all, or
# no posts in last X years.
# delete folder and all feeds in it?
# reload Reddit folder when opening the directory in the tree?
# match whole word only?

from os import listdir, path, getcwd, environ

if environ.get("XDG_SESSION_TYPE") == "wayland":
    environ["QT_QPA_PLATFORM"] = "xcb"

import sys
import logging
import socket
import urllib.request
from functools import partial
from datetime import datetime, timezone, timedelta
from queue import Queue
from subprocess import Popen
from dateutil import tz
from dateutil.parser import parse as dateutil_parse
import re

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6 import QtGui
from PyQt6.QtCore import (Qt, QSettings, QUrl, QFile, QTextStream, pyqtSignal,
                          pyqtSlot, QThread, QThreadPool, QTimer)
from PyQt6.QtGui import QFont, QIcon, QDesktopServices, QKeySequence, QPixmap, QMovie, QAction, QShortcut
from PyQt6.QtWidgets import (QApplication, QTreeView, QPushButton, QMainWindow,
    QTreeWidgetItem, QMenu, QDialog, QLineEdit, QLabel, QMessageBox,
    QInputDialog, QWidget, QToolBar, QHBoxLayout, QCheckBox, QFileDialog)
from ui.harvester_main import Ui_MainWindow
from ui.harvsearch import Ui_frmSearch

import rsslib
import sqlitelib
from newsub import NewSubDialog
import downloader

def _ui_font(weight=QFont.Weight.Normal, size=11):
    font = QApplication.font()
    font.setPointSize(size)
    font.setWeight(weight.value)
    return font


class CustomWebEnginePage(QWebEnginePage):
    # Custom WebEnginePage to customize how we handle link navigation
    def acceptNavigationRequest(self, url,  _type, isMainFrame):
        if _type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            # Send the URL to the system default URL handler.
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url,  _type, isMainFrame)

class ReaderUI(QMainWindow):
    version_str = 'Harvester 0.2'
    console_output = True
    db_filename = None
    feeds = {}
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
    folderlist = []
    auto_update_interval = 1800 # in seconds

    def __init__(self):
        super(ReaderUI, self).__init__()
        #environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-logging --log-level=3"
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.webEngine = QWebEngineView()
        self.ui.webEngine.setPage(CustomWebEnginePage(self))
        self.ui.splitter.addWidget(self.ui.webEngine)

        # hides title bar - looks nice, but annoying in practice
        #self.setWindowFlag(Qt.WindowType.FramelessWindowHint)

        self.ui.buttonNextPage = QPushButton('')
        #self.ui.buttonNextPage.setIcon(QIcon(':/icons/icons/icons8-fast-forward-100.png'))
        self.ui.buttonNextPage.setStyleSheet(
            "border-image : url(:/icons/icons/icons8-fast-forward-100.png);")
        self.ui.buttonNextPost = QPushButton('>')
        self.ui.labelPage = QLabel()
        self.ui.buttonPrevPost = QPushButton('<')
        self.ui.buttonPrevPage = QPushButton('')
        #self.ui.buttonPrevPage.setIcon(QIcon(':/icons/icons/icons8-rewind-100.png'))
        self.ui.buttonPrevPage.setStyleSheet(
            "border-image : url(:/icons/icons/icons8-rewind-100.png);")

        self.ui._search_panel = SearchPanel()
        self.ui.search_toolbar = QToolBar()
        self.ui.search_toolbar.addWidget(self.ui._search_panel)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.ui.search_toolbar)
        #self.ui.statusbar.addWidget(self.ui.search_toolbar)
        self.ui.search_toolbar.hide()
        self.ui._search_panel.searched.connect(self.on_searched)
        self.ui._search_panel.closed.connect(self.ui.search_toolbar.hide)

        self.initializeUI()
        self.load_previous_state()
        self.init_data()
        self.init_threads()
        self.show()
        self._restore_geometry()

    def initializeUI(self):
        self.ui.treeMain.verticalScrollBar().setStyleSheet("""
            QScrollBar { width: 8px; background: transparent; }
            QScrollBar::handle { background: #3daee9; border-radius: 4px; min-height: 20px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)
        palette = self.ui.treeMain.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(61, 174, 233))
        palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(0, 0, 0))
        self.ui.treeMain.setPalette(palette)
        
        self.ui.treeMain.setMouseTracking(True)
        self.ui.treeMain.itemClicked.connect(self.tree_click)
        self.ui.treeMain.itemEntered.connect(self.tree_hover)
        self.ui.treeMain.itemExpanded.connect(lambda node: self.collapse_other_folders(node))
        self.ui.treeMain.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeMain.customContextMenuRequested.connect(self.tree_context_menu)

        logging.basicConfig(level=logging.DEBUG)

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
        self.markFolderReadAction = QAction("Mark All in Folder Read", self)

        #connect actions
        self.newSubAction.triggered.connect(self.new_sub)
        self.markReadAction.triggered.connect(self.mark_read)
        self.updateFeedAction.triggered.connect(self.update_single_feed)
        self.unsubAction.triggered.connect(self.unsubscribe_feed)
        self.feedProperties.triggered.connect(self.view_feed_properties)
        self.actionSearch_Selected_Feed.triggered.connect(self.search_single_feed)
        self.markFolderReadAction.triggered.connect(self.mark_folder_read)

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
        self.ui.actionDelete_Older_Posts.triggered.connect(self.delete_older_posts)
        self.ui.actionDatabase_Maintenance.triggered.connect(self.maintain_DB)
        self.ui.actionSelect_Reddit_Directory.triggered.connect(self.locate_reddit_dir)
        self.ui.actionExit.triggered.connect(self.exit_app)

        # Edit
        self.ui.actionMark_All_Feeds_Read.triggered.connect(self.mark_all)
        self.ui.actionMark_Older_As_Read.triggered.connect(self.mark_older)
        self.ui.actionFind_in_Page.triggered.connect(self.find_in_page)

        # View
        self.ui.actionMost_Recent.triggered.connect(lambda: self.view_most_recent(100))
        self.ui.actionIncrease_Text_Size.triggered.connect(self.increase_text_size)
        self.ui.actionDecrease_Text_Size.triggered.connect(self.decrease_text_size)

        # Tools
        self.ui.actionUpdate_All_Feeds.triggered.connect(
            lambda: self.update_queued_feeds(None, True, False))
        self.ui.actionUpdate_Current_Feed.triggered.connect(self.update_single_feed)
        self.ui.actionUpdate_Current_Feed.setEnabled(False)
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
        self.ui.statusbar.addPermanentWidget(self.ui.buttonPrevPost)
        self.ui.statusbar.addPermanentWidget(self.ui.labelPage)
        self.ui.statusbar.addPermanentWidget(self.ui.buttonNextPost)
        self.ui.statusbar.addPermanentWidget(self.ui.buttonNextPage)
        self.ui.buttonNextPage.clicked.connect(self.next_page)
        self.ui.buttonPrevPage.clicked.connect(self.prev_page)
        self.ui.buttonNextPost.clicked.connect(self.next_post)
        self.ui.buttonPrevPost.clicked.connect(self.prev_post)
        self.shortcut_next_post = QShortcut(QKeySequence('N'), self)
        self.shortcut_next_post.activated.connect(self.next_post)
        self.shortcut_prev_post = QShortcut(QKeySequence('B'), self)
        self.shortcut_prev_post.activated.connect(self.prev_post)

        self.dl_icon = QIcon(':/icons/icons/icons8-download-100.png')
        self.folder_icon = QIcon(':/icons/icons/icons8-folder-100.png')
        self.update_icon = QIcon(':/icons/icons/icons8-right-arrow-100.png')

        self.ui.webEngine.page().linkHovered.connect(self.link_hover)
        self.ui.webEngine.page().urlChanged.connect(lambda url: self.url_change(url))
        self.ui.webEngine.loadFinished.connect(self.finalize_page)
        self.ui.webEngine.setZoomFactor(self.web_zoom)

        #timer setup
        if self.auto_update_interval:
            self.timer = QTimer()
            self.timer.setInterval(self.auto_update_interval * 1000)
            self.timer.timeout.connect(lambda: self.update_queued_feeds(None, True, False))
            self.timer.start()

    def init_data(self):
        self._feed_errors = {}
        self._downloading_feeds = set()
        self._spinner = QMovie(":/resources/loading.gif")
        self._spinner.frameChanged.connect(self._update_spinner_icons)
        self._spinner.start()
        self.load_db_file(self.db_filename)
        self.load_feed_data()
        self.locate_reddit_dir()
        self.setup_tree()
        self.view_most_recent()
        #self.update_queued_feeds()

    def init_threads(self):
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(10)
        self.threadpool.setExpiryTimeout(10000)

    def link_hover(self, url):
        if '#anchor' in url:
            self.ui.statusbar.showMessage(f'Jump to next/previous post.')
        else:
            self.ui.statusbar.showMessage(f'{url}')

    def url_change(self, url):
        url_str = str(url)
        if '#anchor' in url_str:
            a, b, anchor_id = url_str.rpartition('#anchor')
            anchor_id = int(anchor_id.split("')")[0])
            self.anchor_id = anchor_id
            logging.debug(f'Url change -> Anchor is {self.anchor_id}')

            anchor_target_page = anchor_id // self.page_size + 1
            if anchor_target_page < self.curr_page: # go back
                self.ui.buttonPrevPage.click()
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
        logging.debug(f'Clicked on {self.node_name}')

        menu = QMenu()
        menu.addAction(self.newSubAction)
        self.newSubAction.setStatusTip("Subscribe to a new RSS feed.")
        menu.addAction(self.ui.actionNew_Fold)
        self.ui.actionNew_Fold.setStatusTip("Create a new folder to store feeds in.")

        if self.node_id == 'folder':
            menu.addSeparator()
            menu.addAction(self.markFolderReadAction)
            self.markFolderReadAction.setData(item.data(0, Qt.ItemDataRole.UserRole))

        elif self.node_id not in ['folder', 'reddfile']: # we are on an individual feed
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

            curr_feed = self.feeds[self.node_id]

            #menu.addAction("Choice 2")
            #menu.addAction("Choice 3")
            menu.addSeparator()

            move_folder = menu.addMenu('Move to Folder')
            move_folder.hovered.connect(self.movefolder)

            folder_options = self.folderlist
            for f in folder_options:
                if f != curr_feed.folder:
                    tmp_action = move_folder.addAction(f)
                    tmp_action.triggered.connect(partial(self.move_to_folder, curr_feed, f))
            if curr_feed.folder != None and curr_feed.folder != '':
                sep = move_folder.addSeparator()
                no_folder = move_folder.addAction('None (remove from current folder)')
                no_folder.triggered.connect(partial(self.move_to_folder, curr_feed, None))

        menu.exec(self.ui.treeMain.mapToGlobal(position))

    def move_to_folder(self, feed, folder_name):
        logging.debug(f'Moving feed {feed.id} to {folder_name} folder.')
        moved = sqlitelib.update_feed_folder(feed.id, str(folder_name),
                                             self.db_curs, self.db_conn)
        if moved:
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
                logging.error(f'{err}')

    def finalize_page(self, anchor_jump_id=None):
        """Performs final text resize and internal page navigation once the page is loaded."""
        if not (isinstance(self.web_zoom, float) or isinstance(self.web_zoom, int)):
            logging.error('Error retrieving previous zoom level - value was ' +
                          f'{self.web_zoom}. Setting to default of 125%.')
            self.web_zoom = 1.25
        self.ui.webEngine.setZoomFactor(self.web_zoom)
        # QQQQ need to differentiate between ordinary internal nav, which
        # needs anchor changes, and opening external pages, which also calls this.
        self.jump_to_current_anchor()

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
            self.db_filename = settings.value('db_location')
            self.redd_dir = settings.value('redd_dir')
            zoom = settings.value('web_zoom')
            try:
                self.web_zoom = float(zoom) if zoom else 1.25
            except (ValueError, TypeError):
                self.web_zoom = 1.25
            self._saved_expanded_folders = set(settings.value("expanded_folders") or [])

    def _restore_geometry(self):
        settings = QSettings('Hypogeum', 'Harvester')
        geometry = settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
            if not QApplication.screenAt(self.frameGeometry().center()):
                self.setGeometry(100, 100, 1280, 800)
        window_state = settings.value('windowState')
        if window_state:
            self.restoreState(window_state)
        splitter_state = settings.value('splitterSizes')
        if splitter_state:
            self.ui.splitter.restoreState(splitter_state)

    def save_state(self):
        settings = QSettings('Hypogeum', 'Harvester')
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("splitterSizes", self.ui.splitter.saveState())
        settings.setValue("db_location", self.db_filename)
        settings.setValue("redd_dir", self.redd_dir)
        settings.setValue("expanded_folders", list(self._get_expanded_folders()))
        settings.setValue("web_zoom", self.web_zoom)

    def locate_db(self):
        get_db_msg = QMessageBox(self)
        get_db_msg.setWindowTitle("Create or Locate Database")
        get_db_msg.setIcon(QMessageBox.Icon.Critical)

        if self.first_run_mode:
            msg = ("As this is Harvester's first run, you can either create a "
                   "database, or load a previously created database.")
        else:
            msg = 'The previous database could not be found.'
        get_db_msg.setText(msg)
        btn_create_db = get_db_msg.addButton('Create DB', QMessageBox.ButtonRole.AcceptRole)
        btn_load_db = get_db_msg.addButton('Load DB', QMessageBox.ButtonRole.AcceptRole)
        btn_quit = get_db_msg.addButton('Quit', QMessageBox.ButtonRole.DestructiveRole)
        get_db_msg.exec()
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
        logging.info(f'Loading DB file {db_filename}')
        db = sqlitelib.connect_DB_file(db_filename)
        #db_ok = sqlitelib.retrieve_feedlist(db[0], db[1])
        while not db: # or not db_ok:
            logging.error(f'Attempt to load DB file {db_filename} failed.')
            self.db_filename = None
            db_filename = self.locate_db()
            db = sqlitelib.connect_DB_file(db_filename)

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
            logging.info('Loading file cancelled.')
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
            logging.debug('Locating Reddit directory.')
            rd = str(QFileDialog.getExistingDirectory(self, "Select Reddit Directory"))
            if rd:
                self.redd_dir = rd
                self.setup_tree()

    def closeEvent(self, event):
        self.exit_app()

    def load_feed_data(self):
        self.feeds = {}
        feeds = rsslib.import_feeds_from_db(self.db_curs, self.db_conn)
        if feeds:
            for f in feeds:
                self.feeds[f.id] = f

            # find all folders
            self.folderlist = set([x.folder for x in feeds if x.folder not in [None, '', 'None']])
            self.folderlist = sorted(self.folderlist)

        self.update_feeds_unread_counts()

    def update_feeds_unread_counts(self):
        unreads = sqlitelib.count_all_unread(self.db_curs, self.db_conn)
        for k, v in self.feeds.items():
            self.feeds[k].unread = unreads[k] if k in unreads else 0

    def format_folder_node(self, feed_id):
        folder = self.feeds[feed_id].folder
        if not folder or folder in ('', 'None'):
            return
        parent_node = self.feeds[feed_id].treenode.parent()
        if not parent_node:
            return
        folder_unread = sum(f.unread for f in self.feeds.values() if f.folder == folder)
        label = f'{folder} ({folder_unread})' if folder_unread else folder
        parent_node.setText(0, label)
        weight = QFont.Weight.Bold if folder_unread else QFont.Weight.Normal
        parent_node.setFont(0, _ui_font(weight))

    def update_feed_icon(self, incdata):
        feed_id, icondata = incdata
        logging.debug(f'Updating icon for {feed_id}')
        self.feeds[feed_id].favicon = icondata
        self.format_feed_tree_node(self.feeds[feed_id].treenode, feed_id)

    def format_feed_tree_node(self, treenode, feed_id):
        if self.feeds[feed_id].unread:
            unread_count_str = f' ({self.feeds[feed_id].unread})'
        else:
            unread_count_str = ''

        try:
            treenode.setText(0, f'{self.feeds[feed_id].title}{unread_count_str}')
            treenode.setText(1, feed_id)
            fontweight = QFont.Weight.Bold if unread_count_str else QFont.Weight.Normal
            treenode.setFont(0, _ui_font(fontweight))

            default_icon = QIcon(':/icons/icons/icons8-open-book-100-2.png')
            fav = self.feeds[feed_id].favicon
            if fav:
                try:
                    pmap = QPixmap()
                    pmap.loadFromData(self.feeds[feed_id].favicon)
                    testicon = QIcon(pmap)
                except Exception as err:
                    logging.error(f'Error setting pixmap - value was {self.feeds[feed_id].favicon}')
                else:
                    if not testicon.isNull():
                        default_icon = testicon
            treenode.setIcon(0, default_icon)

        except RuntimeError as err: # caused by QT hiding or deleting a node
            pass

    def _get_expanded_folders(self):
        expanded = set()
        root = self.ui.treeMain.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(1) == 'folder' and item.isExpanded():
                expanded.add(item.data(0, Qt.ItemDataRole.UserRole) or item.text(0))
        return expanded

    def setup_tree(self):
        expanded_folders = self._get_expanded_folders() or getattr(self, '_saved_expanded_folders', set())
        self._saved_expanded_folders = set()
        self.ui.treeMain.clear()

        for f in self.folderlist:
            folderfeeds = sorted([v for v in self.feeds.values() if v.folder == f],
                                  key=lambda x:x.title.lower())
            folder_unread = sum(feed.unread for feed in folderfeeds)
            folder_label = f'{f} ({folder_unread})' if folder_unread else f
            foldernode = QTreeWidgetItem(self.ui.treeMain, [folder_label, 'folder'])
            foldernode.setData(0, Qt.ItemDataRole.UserRole, f)
            weight = QFont.Weight.Bold if folder_unread else QFont.Weight.Normal
            foldernode.setFont(0, _ui_font(weight))
            foldernode.setIcon(0, QIcon(':/icons/icons/icons8-folder-100.png'))
            for feed in folderfeeds:
                newnode = QTreeWidgetItem(foldernode)
                self.feeds[feed.id].treenode = newnode
                self.format_feed_tree_node(newnode, feed.id)
            self.ui.treeMain.blockSignals(True)
            foldernode.setExpanded(f in expanded_folders)
            self.ui.treeMain.blockSignals(False)

        # add folderless feeds
        for feed in [v for v in self.feeds.values() if v.folder in [None, '', 'None']]:
            newnode = QTreeWidgetItem(self.ui.treeMain)
            self.feeds[feed.id].treenode = newnode
            self.format_feed_tree_node(newnode, feed.id)

        # add redd folder
        if self.redd_dir:
            foldernode = QTreeWidgetItem(self.ui.treeMain, ['ReddFiles', 'folder'])
            foldernode.setFont(0, _ui_font(QFont.Weight.Bold))
            foldernode.setIcon(0, QIcon(':/icons/icons/icons8-reddit-100-2.png'))
            
            try:
                reddfiles = sorted(listdir(self.redd_dir), key=lambda x:x.lower())
            except FileNotFoundError:
                reddfiles = []
                logging.error(f'Unable to locate reddit directory from registry: {self.redd_dir}')

            self.ui.treeMain.blockSignals(True)
            foldernode.setExpanded('ReddFiles' in expanded_folders)
            self.ui.treeMain.blockSignals(False)
            for rf in reddfiles:
                newnode = QTreeWidgetItem(foldernode, [f'{rf}', 'reddfile'])
                newnode.setFont(0, _ui_font())

    def generate_filtered_tree(self, srchtext):
        logging.debug(f'Searching for feeds with {srchtext} in name...')
        self.ui.treeMain.clear()
        srchtext = srchtext.lower()

        for feed in self.feeds.values():
            if srchtext in feed.title.lower():
                newnode = QTreeWidgetItem(self.ui.treeMain)
                self.ui.treeMain.addTopLevelItem(newnode)
                self.feeds[feed.id].treenode = newnode
                self.format_feed_tree_node(newnode, feed.id)

        # add redd folder
        if self.redd_dir:
            reddfiles = listdir(self.redd_dir)
            for rf in reddfiles:
                if srchtext in rf:
                    newnode = QTreeWidgetItem(self.ui.treeMain, [f'{rf}', 'reddfile'])
                    newnode.setFont(0, _ui_font())

    def exit_app(self):
        logging.info('Exiting app...')
        self.save_state()
        self.db_conn.close()
        self.close()
        QApplication.quit()

    def create_db(self):
        # QQQQ offer to add sample feeds to new DB
        new_db = None
        try:
            dlg = QFileDialog.getSaveFileName(self, "Create New Database")
            if dlg:
                new_db = dlg[0]
        except Exception as err:
            logging.error(f'{err}')
        if new_db:
            if sqlitelib.create_DB(new_db):
                logging.info(f'New database {new_db} created.')
                loadnew = QMessageBox.question(self, "Load new DB?",
                          "Would you like to load the new database?",
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
                if loadnew == QMessageBox.StandardButton.Yes:
                    '''
                    load_sample = QMessageBox.question(self, "Import Sample Feeds?",
                                  "Would you like to add some sample feeds to the "
                                  "new database? If not, the new database will be empty.",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
                    if load_sample == QMessageBox.StandardButton.Yes:
                        #new, dupes = rsslib.import_opml_to_db(dlg[0], self.feeds,
                                      self.db_curs, self.db_conn)
                        pass
                    '''
                    self.db_filename = new_db
                    self.db_curs, self.db_conn = sqlitelib.connect_DB_file(new_db)
                    self.init_data()
                return self.db_filename

    def tree_click(self):
        #QQQQ also needs to update page controls, as max_page doesn't seem to update
        # if a new page is added
        node_title = self.ui.treeMain.currentItem().text(0)
        node_id = self.ui.treeMain.currentItem().text(1)

        self.curr_page = 1
        self.handle_nextprev_buttons()

        is_feed = node_id not in ('folder', 'reddfile', '')
        self.ui.actionUpdate_Current_Feed.setEnabled(is_feed)

        if node_id == 'reddfile':
            reddurl = path.join(self.redd_dir, node_title)
            self.setWindowTitle(f'{self.version_str} - {reddurl}')
            self.ui.webEngine.setZoomFactor(self.web_zoom)
            self.ui.webEngine.load(QUrl.fromLocalFile(reddurl))
            self.curr_page, self.max_page = 1, 1
            self.ui.labelPage.setText(f'Page 1 of 1')
            self.handle_nextprev_buttons()
        elif node_id == 'folder':
            self.setWindowTitle(f'{self.version_str} - {self.db_filename}')
            curr_node = self.ui.treeMain.findItems(node_title, Qt.MatchFlag.MatchContains, 0)[0]
            curr_state = curr_node.isExpanded()
            curr_node.setExpanded(not curr_state)
        else:
            #logging.debug(f'Tree clicked - {node_title} selected with ID {node_id}.')
            self.anchor_id = 0
            self.setWindowTitle(f'{self.version_str} - {self.db_filename} - {node_title}')
            self.display_post_data(sqlitelib.get_feed_posts(node_id, self.db_curs, self.db_conn))
            self.feeds[node_id].last_read = datetime.now(timezone.utc).isoformat('T', 'seconds')
            self.feeds[node_id].unread = 0
            sqlitelib.mark_feed_read(node_id, self.db_curs, self.db_conn)
            self.format_feed_tree_node(self.ui.treeMain.currentItem(), node_id)
            self.format_folder_node(node_id)
            self.jump_to_current_anchor()

    def display_post_data(self, results):
        self.results = results
        posthtml = self.generate_posts_page(results)
        self.ui.webEngine.setHtml(posthtml, QUrl("file://"))

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
        logging.debug(f'Showing {num} most recent posts.')
        startposts = sqlitelib.get_most_recent(num, self.db_curs, self.db_conn)
        if not startposts:
            self.results = []
        posthtml = self.generate_posts_page(startposts)
        self.ui.webEngine.setHtml(posthtml, QUrl("file://"))
        self.anchor_id = 0
        self.jump_to_current_anchor()

    def maintain_DB(self):
        self.ui.statusbar.showMessage('Running DB maintenance.')
        sqlitelib.vacuum(self.db_conn)

    def mark_all(self):
        sqlitelib.mark_all_read(self.db_curs, self.db_conn)
        for feed in self.feeds.values():
            feed.unread = 0
        self.setup_tree()

    def mark_folder_read(self):
        folder_name = self.markFolderReadAction.data()
        if not folder_name:
            return
        for feed in [f for f in self.feeds.values() if f.folder == folder_name]:
            sqlitelib.mark_feed_read(feed.id, self.db_curs, self.db_conn)
            feed.unread = 0
            self.format_feed_tree_node(feed.treenode, feed.id)
        self.format_folder_node(next(f.id for f in self.feeds.values() if f.folder == folder_name))

    def mark_older(self):
        sqlitelib.mark_old_as_read(3, self.db_curs, self.db_conn)
        self.update_feeds_unread_counts()
        self.setup_tree()

    def delete_older_posts(self):
        print('Deleted older posts.')
        sqlitelib.mass_delete_all_but_last_n(100, self.db_curs, self.db_conn)

    def find_in_page(self, srchtext=None):
        #file_menu.addAction('&Find...', self.search_toolbar.show, shortcut=QKeySequence.StandardKey.Find)
        #self.ui.find_in_page = QLineEdit()
        #self.ui.statusbar.addWidget(self.ui.find_in_page)
        #self.ui.find_in_page.setFocus()
        #flags = QWebEnginePage.FindFlag(0)
        #self.ui.webEngine.findText("new", flags)
        self.ui.search_toolbar.show()

    def update_tree_node_background(self, feed_id, mode):
        treenode = self.feeds[feed_id].treenode
        if treenode:
            try:
                if mode == 'downloading':
                    treenode.setBackground(0, QtGui.QBrush(QtGui.QColor(61, 174, 233, 255)))
                    treenode.setForeground(0, QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                elif mode == 'finished':
                    treenode.setData(0, Qt.ItemDataRole.BackgroundRole, None)
                    treenode.setData(0, Qt.ItemDataRole.ForegroundRole, None)
            except Exception as err:
                pass

    def _update_spinner_icons(self):
        frame_icon = QIcon(self._spinner.currentPixmap())
        for feed_id in self._downloading_feeds:
            treenode = self.feeds[feed_id].treenode
            if treenode:
                try:
                    treenode.setIcon(0, frame_icon)
                except RuntimeError:
                    pass

    def node_started_downloading_update_ui(self, data):
        msg, feed_id = data[0], data[1]
        self.ui.statusbar.showMessage(msg)
        self._downloading_feeds.add(feed_id)
        self.update_tree_node_background(feed_id, 'downloading')

    def node_error_update_ui(self, indata):
        feed_id = indata[0]
        count = self._feed_errors.get(feed_id, (0, None))[0] + 1
        hours = min(2 ** (count - 1), 24)
        retry_after = datetime.now(timezone.utc) + timedelta(hours=hours)
        self._feed_errors[feed_id] = (count, retry_after)
        logging.warning(f'Feed {feed_id} error #{count}, backing off for {hours}h')

    def node_finished_downloading_update_ui(self, indata):
        num_new, feed_id = indata
        self._feed_errors.pop(feed_id, None)
        self._downloading_feeds.discard(feed_id)
        self.feeds[feed_id].unread = num_new
        self.format_feed_tree_node(self.feeds[feed_id].treenode, feed_id)
        self.format_folder_node(feed_id)
        self.update_tree_node_background(feed_id, 'finished')

    def generate_view_sorted_feed_queue(self):
        # generate queue in tree display order rather than alphabetically
        now = datetime.now(timezone.utc)
        q = Queue()
        view_sort = sorted([x for x in self.feeds.values() if x.folder],
                    key = lambda x: (x.folder, x.title.lower()))
        view_sort += sorted([x for x in self.feeds.values() if not x.folder],
                    key = lambda x: x.title.lower())
        for feed in view_sort:
            err = self._feed_errors.get(feed.id)
            if err and now < err[1]:
                logging.debug(f'Skipping {feed.id} — in backoff until {err[1].isoformat()}')
                continue
            q.put(feed)
        return q

    def update_queued_feeds(self, specified_feeds=None, dl_feeds=True, dl_icons=False,
                            dl_imgs=False):
        if not is_internet_on():
            self.ui.statusbar.showMessage(f'Not connected to the Internet.')
            return

        if specified_feeds:
            q = Queue()
            for f in specified_feeds:
                q.put(f)
        else:
            q = self.generate_view_sorted_feed_queue()
        max_q_size = q.qsize()

        for num in range(min(self.threadpool.maxThreadCount(), q.qsize())):
            worker = downloader.Worker(max_q_size, num, q, self.feeds, dl_feeds, dl_icons,
                                       db_filename=self.db_filename)
            worker.signals.started.connect(self.node_started_downloading_update_ui)
            worker.signals.finished.connect(self.node_finished_downloading_update_ui)
            worker.signals.error.connect(self.node_error_update_ui)
            worker.signals.icondata.connect(self.update_feed_icon)
            self.threadpool.start(worker)

        self.timer.setInterval(self.auto_update_interval * 1000)

    def new_sub(self):
        # QQQQ should probably use threading for instances where other DB activity is happening
        newsubform = NewSubDialog(self)
        if newsubform.exec():
            newfeed = newsubform.get_inputs()
            self.ui.statusbar.showMessage(f'Adding new subscription: {newfeed.title} - '
                                          f'{newfeed.rss_url} to folder {newfeed.folder}')
            sqlitelib.write_feed(newfeed, self.db_curs, self.db_conn)
            self.feeds[newfeed.id] = newfeed
            self.setup_tree()
            self.update_queued_feeds([newfeed], True, True)

    def mark_read(self):
        logging.debug(f'Mark feed {self.node_name} - {self.node_id} read.')

    def import_feeds_from_opml(self):
        dlg = QFileDialog.getOpenFileName(self, "Open OPML File", "", \
            "OPML Files (*.opml);;All files (*.*)")
        if dlg[0] != '':
            new, dupes = rsslib.import_opml_to_db(dlg[0], self.feeds, self.db_curs,
                                                  self.db_conn)
            if new:
                self.load_feed_data()
                self.setup_tree()
                msg = f'Imported {new} new feeds'
                add = '.' if not dupes else f' and skipped {dupes} duplicates.'
                self.ui.statusbar.showMessage(msg + add)
                self.update_queued_feeds(None, True, True)
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
            for feed in [v for v in self.feeds.values() if v.folder == folder]:
                feed = feed.sanitize()
                opml.append(f'\t\t\t<outline text="{feed.title}" title="{feed.title}" '
                            f'type="{feed.f_type}" xmlUrl="{feed.rss_url}" '
                            f'htmlUrl="{feed.html_url}"/>\n')
            opml.append('\t\t</outline>\n')

        # folderless feeds
        for feed in [v for v in self.feeds.values() if v.folder in [None, '', 'None']]:
            feed = feed.sanitize()
            opml.append(f'\t\t<outline text="{feed.title}" title="{feed.title}" '
                        f'type="{feed.f_type}" xmlUrl="{feed.rss_url}" '
                        f'htmlUrl="{feed.html_url}"/>\n')

        opml.append('\t</body>\n</opml>')

        opml = ''.join(opml)
        with open(fname, 'w', encoding='utf-8') as outfile:
            outfile.write(opml)

        self.ui.statusbar.showMessage(f'Feeds exported to file {fname}.')

    def update_single_feed(self, feed=None):
        if not feed:
            node_id = self.ui.treeMain.currentItem().text(1)
            feed = self.feeds[node_id]
        logging.debug(f'Updating {feed.title}')
        self.ui.statusbar.showMessage(f'Updating {feed.title}')
        self.update_queued_feeds([feed], True, True, True)
        # QQQQ should update current page

    def search_feeds(self):
        srchdialog = SrchDialog(self)
        srchdialog.exec()
        if self.srchtext:
            logging.debug(f'Searching feeds DB for "{self.srchtext}" in {self.srchtime.lower()}.')
            results = sqlitelib.text_search(self.srchtext, self.db_curs, self.db_conn,
                                            100, self.srchtime)
            if results:
                self.ui.statusbar.showMessage(f'{len(results)} results found.')
                posthtml = self.generate_posts_page(results)
                self.ui.webEngine.setHtml(posthtml, QUrl("file://"))
            else:
                self.ui.statusbar.showMessage(f'No results found for search "{self.srchtext}"')

    def search_single_feed(self):
        if self.ui.treeMain.currentItem():
            node_title = self.ui.treeMain.currentItem().text(0)
            node_id = self.ui.treeMain.currentItem().text(1)

            srchdialog = SrchDialog(self)
            srchdialog.exec()
            if self.srchtext:
                logging.debug(f'Searching {node_title} for "{self.srchtext}" in '
                            f'{self.srchtime.lower()}.')
                results = sqlitelib.text_search(self.srchtext, self.db_curs,
                                                self.db_conn, 100, self.srchtime, node_id)
                if results:
                    self.ui.statusbar.showMessage(f'{len(results)} results found.')
                    posthtml = self.generate_posts_page(results)
                    self.ui.webEngine.setHtml(posthtml, QUrl("file://"))
                else:
                    self.ui.statusbar.showMessage(f'No results found for search '
                                                  f'"{self.srchtext}"')
        else:
            self.ui.statusbar.showMessage(f'No feed currently selected.')

    def update_reddit(self):
        # QQQQ should locate correct file
        Popen(['start', 'python', r'e:\Code\blw\redditcrawl4.py'], shell=True)

    def unsubscribe_feed(self):
        if self.node_id not in ['folder', 'reddfile']:
            confirm = QMessageBox.question(self, "Unsubscribe from feed?",
                     "This will unsubscribe you from the feed and delete all saved posts. "
                     "Are you sure?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                res = sqlitelib.delete_feed(self.node_id, self.db_curs, self.db_conn)
                if res:
                    logging.info(f'Unsubscribed from {self.feeds[self.node_id].title}.')
                    self.ui.statusbar.showMessage(f'Unsubscribed from {self.feeds[self.node_id].title}.')
                    del self.feeds[self.node_id]
                    self.load_feed_data()
                    self.setup_tree()

    def generate_jump_buttons(self, anchor_id):
        anchor = ''
        if anchor_id < len(self.results) - 1:
            anchor = (f'<a href="#anchor{anchor_id+1}"><img alt="Next" '
                       'style="float:right" title="Next post" '
                       'src="qrc:/icons/icons/icons8-download-100-3.png" '
                      f'width="{self.pagenav_icon_size}" '
                      f'height="{self.pagenav_icon_size}"></a>')
        if anchor_id != 0:
            anchor += (f'<a href="#anchor{anchor_id-1}"><img alt="Prev" '
                        'style="float:right" title="Previous post" '
                        'src="qrc:/icons/icons/icons8-upload-100-2.png" '
                       f'width="{self.pagenav_icon_size}" '
                       f'height="{self.pagenav_icon_size}"></a>')
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
        self.max_page = int(len(results) / self.page_size) +\
                        (len(results) % self.page_size > 0)
        self.max_page = max(self.max_page, 1)
        self.handle_nextprev_buttons()
        results = results[startpost:endpost]
        anchor_id = startpost

        self.ui.labelPage.setFont(_ui_font(QFont.Weight.Bold))
        self.ui.labelPage.setText(f'Page {self.curr_page} of {self.max_page}')

        # QQQQ should edit post.contents to strip image data if img_loading is
        # disabled - older posts may have had it enabled

        if results:
            for post in results:
                convdate = convert_isodate_to_fulldate(post.date)
                anchortext = self.generate_jump_buttons(anchor_id)
                isread = 'unread' if post.flags == 'None' else 'read'
                page.append('<div class="post">'
                            f'<a id="anchor{anchor_id}" class="{isread}" '
                            f'href="{post.url}">{post.title}</a> '
                            f'{anchortext} '
                            f'<h5><i><a href="{post.feed_id}">{self.feeds[post.feed_id].title}</a> - '
                            f'{post.author} on {convdate}</i></h5>'
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
            self.ui.webEngine.setHtml(posthtml, QUrl("file://"))
            self.anchor_id = (self.curr_page - 1) * self.page_size
            self.jump_to_current_anchor()
            logging.debug(f'Anchor is now {self.anchor_id}')
        if self.curr_page == self.max_page:
            self.ui.buttonNextPage.setDisabled(True)

    def prev_page(self):
        if self.curr_page > 1:
            self.curr_page -= 1
            self.ui.buttonNextPage.setDisabled(False)
            posthtml = self.generate_posts_page()
            self.ui.webEngine.setHtml(posthtml, QUrl("file://"))
            if self.anchor_id % self.page_size != self.page_size - 1:
                self.anchor_id = (self.curr_page - 1) * self.page_size
            logging.debug(f'Anchor is now {self.anchor_id}')
        if self.curr_page == 1:
            self.ui.buttonPrevPage.setDisabled(True)

    def handle_nextprev_buttons(self):
        self.ui.buttonNextPage.setDisabled(self.curr_page == self.max_page)
        self.ui.buttonPrevPage.setDisabled(self.curr_page == 1)

        if self.curr_page == self.max_page:
            self.ui.buttonNextPage.setStyleSheet("")
        else:
            self.ui.buttonNextPage.setStyleSheet("border-image : "
                "url(:/icons/icons/icons8-fast-forward-100.png);")

        if self.curr_page == 1:
            self.ui.buttonPrevPage.setStyleSheet("")
        else:
            self.ui.buttonPrevPage.setStyleSheet("border-image : "
                "url(:/icons/icons/icons8-rewind-100.png);")

    def next_post(self):
        self.anchor_id += 1
        logging.debug(f'Next -> Anchor is {self.anchor_id}')
        if self.anchor_id % self.page_size == 0:
            self.ui.buttonNextPage.click()
        self.jump_to_current_anchor()

    def prev_post(self):
        self.anchor_id = max(0, self.anchor_id - 1)
        logging.debug(f'Prev -> Anchor is {self.anchor_id}')
        if self.anchor_id % self.page_size == self.page_size - 1:
            self.ui.buttonPrevPage.click()
        self.jump_to_current_anchor()

    def jump_to_current_anchor(self):
        if self.anchor_id > 0:
            anchor_str = f'anchor{self.anchor_id}'
            js = f"document.getElementById('{anchor_str}').scrollIntoView();"
        else:
            js = 'window.scroll(0, 0)'
        self.ui.webEngine.page().runJavaScript(js)

    def new_folder(self):
        newfolder, ok = QInputDialog.getText(self, 'New Folder Name', 'Enter folder name:')
        if ok:
            #print(str(newfolder))
            newfoldernode = QTreeWidgetItem(self.ui.treeMain, [newfolder, 'folder'])
            newfoldernode.setFont(0, _ui_font(QFont.Weight.Bold))
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
        """Generates basic size reports for the current feed DB"""
        report = sqlitelib.usage_report(self.db_curs, self.db_conn)
        page = ['<!DOCTYPE html><html><head>']
        if style := load_css_file():
            page.append('<style>' + style + '</style>')

        db_size = path.getsize(self.db_filename)

        page.append(f'<b>Total database size:</b> {self.format_filesize_str(db_size)}.<p>')
        page.append(f'<b>Total feeds:</b> {len(self.feeds)}.<p>')
        mean_str = self.format_filesize_str(db_size / len(self.feeds))
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
        """Lists feeds with no posts"""
        dead = sqlitelib.find_dead_feeds(self.db_curs, self.db_conn)
        if dead:
            page = ['<!DOCTYPE html><html><head>']
            if style := load_css_file():
                page.append('<style>' + style + '</style>')

            page.append('<b>Dead Feeds</b><p><ol>')

            for k, v in dead.items():
                page.append(f'<li>{v}</li>')
            page.append('</ol>')

            page = ''.join(page)
            self.ui.webEngine.setHtml(page)
            self.curr_page, self.max_page = 1, 1
            self.ui.labelPage.setText(f'Page 1 of 1')
            self.handle_nextprev_buttons()

    def view_feed_properties(self):
        if self.node_id not in ['folder', 'reddfile']:
            node_id = self.ui.treeMain.currentItem().text(1)
            feed = self.feeds[node_id]
            props = QMessageBox(self)
            props.setWindowTitle(f"Feed Properties")
            props.setTextFormat(Qt.TextFormat.RichText)
            pmap = QPixmap()
            pmap.loadFromData(self.feeds[feed.id].favicon)
            props.setIconPixmap(pmap)
            props.setText(f'<h4><u>{feed.title}</u></h4>'
                          '<p style="margin-bottom: -20px;">'
                          '<ul style="margin-left: -30px; margin-top: -20px;">'
                          f'<li>RSS URL: <a href="{feed.rss_url}" style="color: deepskyblue">{feed.rss_url}</a>'
                          f'<li>Home Page: <a href="{feed.html_url}" style="color: deepskyblue">{feed.html_url}</a>'
                          f'<li>Last Read: {feed.last_read}'
                          '</ul>')
            props.setStandardButtons(QMessageBox.StandardButton.Ok)
            props.setDefaultButton(QMessageBox.StandardButton.Ok)
            props.exec()
            props.deleteLater()

    def about_harv(self):
        #Information page for the program
        about = QMessageBox(self)
        about.setWindowTitle("About Harvester")
        about.setTextFormat(Qt.TextFormat.RichText)
        about.setIconPixmap(QPixmap(':/icons/icons/icons8-combine-harvester-100-2.png'))
        about.setText('<h4>Harvester 0.2</h4>A cross-platform RSS reader.'
                      '<p style="margin-bottom: -20px;">Credits:'
                      '<ul style="margin-left: -30px; margin-top: -20px;">'
                      '<li>Icons from <a href="https://icons8.com">Icons8</a></ul>')
        about.setStandardButtons(QMessageBox.StandardButton.Ok)
        about.setDefaultButton(QMessageBox.StandardButton.Ok)
        about.exec()
        about.deleteLater()

#=========================================================================

class SrchDialog(QDialog):
    """UI elements for searching of single or multiple feeds"""
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

#=========================================================================

class SearchPanel(QWidget):
    """UI elements for text search of the current page from the status bar"""
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

        QShortcut(QKeySequence.StandardKey.FindNext, self, activated=next_button.animateClick)
        QShortcut(QKeySequence.StandardKey.FindPrevious, self, activated=prev_button.animateClick)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_le, activated=self.closed)

    @pyqtSlot()
    def on_preview_find(self):
        self.update_searching(QWebEnginePage.FindFlag.FindBackward)

    @pyqtSlot()
    def update_searching(self, direction=QWebEnginePage.FindFlag(0)):
        flag = direction
        if self.case_button.isChecked():
            flag |= QWebEnginePage.FindFlag.FindCaseSensitively
        self.searched.emit(self.search_le.text(), flag)

    def showEvent(self, event):
        super(SearchPanel, self).showEvent(event)
        self.setFocus(True)

# ============================================================================

def is_internet_on():
    try:
        socket.setdefaulttimeout(3)
        with socket.create_connection(("www.google.com", 80)) as _:
            return True
    except OSError:
        pass
    return False

def convert_isodate_to_fulldate(isodate):
    # check this works on Linux - may need %-I there instead
    formatstr = '%A, %d %B %Y %#I:%M %p'
    try:
        # Strip redundant trailing Z when an explicit UTC offset is already present
        # e.g. "2026-04-19T09:00:12+00:00Z" — malformed data produced by some feeds
        cleaned = re.sub(r'([+-]\d{2}:\d{2})Z$', r'\1', isodate)
        utctime = dateutil_parse(cleaned, tzinfos=rsslib._TZINFOS)
        localtz = tz.tzlocal()
        localtime = utctime.astimezone(localtz)
        return localtime.strftime(formatstr)
    except Exception as err:
        logging.error(f'Timezone conversion error - {err}')
        return isodate

def load_css_file():
    f = QFile(":/resources/pagestyle.css")
    if f.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text):
        return QTextStream(f).readAll()
    logging.error('Unable to load pagestyle.css from resources.')

def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)

def main():
    pass

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # set stylesheet
    # file = QFile(":/dark/stylesheet.qss")
    # file.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text)
    # stream = QTextStream(file)
    # app.setStyleSheet(stream.readAll())

    sys._excepthook = sys.excepthook
    sys.excepthook = exception_hook

    Reader = ReaderUI()
    sys.exit(app.exec())
