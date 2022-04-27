import sys
import pytest

sys.path.append('..')
from rsslib import *

@pytest.fixture
def good_feed():
    return Feed('GoodFeed01', 'Good Feed', 'MainFolder', 'rss', 'http://goodfeed.com/rss',
                'http://goodfeed.com', ['alpha', 'beta'], 5, None)

@pytest.fixture
def bad_feed():
    return Feed('bad&feed01<>', '"Bad" & Test <Feed>', 'MainFolder', 'rss', 'http://badfeed.com/rss',
                'http://badfeed.com', None, 0, None)

def test_feed_class_basics(good_feed):
    assert good_feed.feed_id == 'GoodFeed01'
    assert good_feed.title == 'Good Feed'
    assert good_feed.tags == ['alpha', 'beta']

def test_feed_none():
    with pytest.raises(TypeError):
        f = Feed()

def test_feed_title_sanitize(bad_feed):
    assert bad_feed.sanitize().title == '&quot;Bad&quot; &amp; Test &lt;Feed&gt;'
