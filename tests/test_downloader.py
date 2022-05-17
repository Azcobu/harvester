import sys
import pytest
from queue import Queue
from unittest.mock import Mock, patch

sys.path.append('..')
import rsslib
import downloader

@pytest.fixture()
def feed():
    return rsslib.Feed("http://new-sun.gov", "New Sun", "Main Folder",
                       "rss", "http://new-sun.gov/rss", "http://new-sun.gov",
                       None, "1970-01-01T00:00:00+00:00", '0',
                       "Thu, 1 Jan 1970 00:00:00 GMT", None)
@pytest.fixture
def worker(feed):
    q, db_q = Queue(), Queue()
    q.put(feed)
    return downloader.Worker(10, 0, q, db_q, {feed.id:feed}, True, True)

@pytest.fixture()
def parsedfeed():
    m = Mock()
    m.configure_mock(status=200)
    return m

def test_create_worker(worker, feed):
    assert isinstance(worker, downloader.Worker)

def test_status_returns(worker, parsedfeed, feed):
    assert parsedfeed.status == 200
    assert worker.check_return_status_ok(parsedfeed, feed) == True

@pytest.mark.parametrize("status, expected", [(200, True), (304, None), (404, None)])
def test_more_status_returns(worker, feed, status, expected):
    m = Mock()
    m.configure_mock(status=status)
    assert worker.check_return_status_ok(m, feed) == expected

'''
@patch('feedparser.parse')
def test_dl_feed(feed):
    with patch('feedparser.parse', feed) as mock_get:
        mock_get.status = 200
        q, db_q = Queue(), Queue()
        q.put(feed)
        w = downloader.Worker(10, 0, q, db_q, {feed.id:feed}, True, True)
        assert w.dl_feed(feed) is not None
'''

def main():
    pass

if __name__ == '__main__':
    main()
