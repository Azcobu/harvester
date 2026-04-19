import pickle
import pytest
import feedparser
from os import listdir, path

import rsslib


class MockEntry(dict):
    """Dict subclass that also supports attribute access, mimicking feedparser entries."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

@pytest.fixture
def good_feed():
    return rsslib.Feed('GoodFeed01', 'Good Feed', 'MainFolder', 'rss',
                       'http://goodfeed.com/rss', 'http://goodfeed.com',
                       ['alpha', 'beta'], 5, None)

@pytest.fixture
def bad_feed():
    return rsslib.Feed('bad&feed01<>', '"Bad" & Test <Feed>', 'MainFolder', 'rss',
                       'http://badfeed.com/rss', 'http://badfeed.com', None, 0, None)

@pytest.fixture
def test_post():
    return rsslib.Post(2, "http://new-sun.gov", "Chapter 1 - On Symbols",
        "Gene Wolfe", "http://order-of-seekers.gov", '2022-01-01',
        "We believe that we invent symbols. The truth is that they invent us; we "
        "are their creatures, shaped by their hard, defining edges. "
        "Also, img tags: <img src = 'empty.jpg'>", "None")

@pytest.fixture
def posts():
    """builds a list containing raw feed data strings"""
    postlist = []
    testdata_dir = path.join(path.dirname(__file__), 'testdata')
    postfiles = sorted([x for x in listdir(testdata_dir) if 'example-post' in x])
    for pname in postfiles:
        with open(path.join(testdata_dir, pname), 'rb') as infile:
            postlist.append(pickle.load(infile))
    return postlist

@pytest.fixture
def feeds():
    """builds a list containing raw feed data strings"""
    feedlist = []
    testdata_dir = path.join(path.dirname(__file__), 'testdata')
    feedfiles = sorted([x for x in listdir(testdata_dir) if 'example-feed' in x])
    for fname in feedfiles:
        with open(path.join(testdata_dir, fname), 'rb') as infile:
            feedlist.append(pickle.load(infile))
    return feedlist

def test_feed_class_basics(good_feed):
    assert good_feed.id == 'GoodFeed01'
    assert good_feed.title == 'Good Feed'
    assert good_feed.tags == ['alpha', 'beta']
    assert str(good_feed) == 'Feed: Good Feed (http://goodfeed.com)'

def test_feed_none():
    with pytest.raises(TypeError):
        f = rsslib.Feed()

def test_feed_title_sanitize(bad_feed):
    assert bad_feed.sanitize().title == '&quot;Bad&quot; &amp; Test &lt;Feed&gt;'

def test_post_class_basics(test_post):
    assert test_post.p_id == 2
    assert test_post.feed_id == "http://new-sun.gov"
    assert str(test_post) == 'Post: Chapter 1 - On Symbols'

def test_post_strip_img_tags(test_post):
    imgstr = "<img src = 'empty.jpg'>"
    assert imgstr in test_post.content
    test_post.strip_image_tags()
    assert imgstr not in test_post.content

def test_opml_parse():
    f = rsslib.parse_opml(path.join(path.dirname(__file__), 'valid.opml'))
    assert len(f) == 8
    assert set([x.folder for x in f if x.folder]) == set(['News', 'Archaeology'])
    assert sum([1 for x in f if x.folder == 'News']) == 3
    assert sum([1 for x in f if x.folder == None]) == 2

@pytest.mark.parametrize("postnum, expected",
    [(0, 'tag:blogger.com,1999:blog-7255205.post-5422949711722588281'),
     (1, 'https://astralcodexten.substack.com/p/open-thread-222'),
     (2, 'https://marginalrevolution.com/?p=83467'),
     (3, 'http://tagn.wordpress.com/?p=99212'),
     (4, 'https://kerbaldevteam.tumblr.com/post/676183007734972416')])
def test_post_parse_id(good_feed, posts, postnum, expected):
    p = rsslib.parse_post(good_feed, posts[postnum])
    assert p.p_id == expected

def test_post_parsing_single_feed(good_feed, posts):
    for p in posts:
        assert isinstance(rsslib.parse_post(good_feed, p), rsslib.Post)

def test_post_parsing_multiple_feeds(good_feed, feeds):
    for postlist in feeds:
        for p in postlist:
            assert isinstance(rsslib.parse_post(good_feed, p), rsslib.Post)

def test_post_parse_ids(good_feed, feeds):
    for postlist in feeds:
        for p in postlist:
            p = rsslib.parse_post(good_feed, p)
            assert isinstance(p.p_id, str)

# --- parse_date ---

@pytest.mark.parametrize("indate, expected", [
    ("Thu, 19 Apr 2026 12:00:00 GMT",   "2026-04-19T12:00:00+00:00"),
    ("2026-04-19T12:00:00+00:00",        "2026-04-19T12:00:00+00:00"),
    ("2026-04-19T12:00:00+00:00Z",       "2026-04-19T12:00:00+00:00"),  # malformed trailing Z
    ("Thu, 19 Apr 2026 12:00:00 PST",   "2026-04-19T20:00:00+00:00"),  # PST = UTC-8
    ("Thu, 19 Apr 2026 00:00:00 EST",   "2026-04-19T05:00:00+00:00"),  # EST = UTC-5
])
def test_parse_date_valid(indate, expected):
    assert rsslib.parse_date(indate) == expected

def test_parse_date_invalid_returns_original():
    bad = "not a date at all"
    assert rsslib.parse_date(bad) == bad

# --- Feed.san ---

def test_feed_san_none_returns_none(good_feed):
    assert good_feed.san(None) is None

def test_feed_san_non_string_returns_none(good_feed):
    assert good_feed.san(42) is None

def test_feed_san_escapes_all_chars(good_feed):
    assert good_feed.san('a & b < c > d "e"') == 'a &amp; b &lt; c &gt; d &quot;e&quot;'

# --- Feed.tags default ---

def test_feed_tags_default_is_empty_list():
    f = rsslib.Feed('id', 'Title', None, 'rss', 'http://x.com/rss', 'http://x.com')
    assert f.tags == []

def test_feed_tags_preserved_when_provided():
    f = rsslib.Feed('id', 'Title', None, 'rss', 'http://x.com/rss', 'http://x.com',
                    tags=['a', 'b'])
    assert f.tags == ['a', 'b']

# --- parse_post fallbacks ---

def test_parse_post_missing_author(good_feed):
    entry = MockEntry(id='id1', title='T', link='http://x.com',
                      published='2026-01-01', summary='content')
    p = rsslib.parse_post(good_feed, entry)
    assert p.author == 'Unknown author'

def test_parse_post_missing_title(good_feed):
    entry = MockEntry(id='id1', link='http://x.com', author='A',
                      published='2026-01-01', summary='content')
    p = rsslib.parse_post(good_feed, entry)
    assert p.title == 'Untitled Post'

def test_parse_post_summary_fallback(good_feed):
    entry = MockEntry(id='id1', title='T', author='A', link='http://x.com',
                      published='2026-01-01', summary='summary text')
    p = rsslib.parse_post(good_feed, entry)
    assert p.content == 'summary text'

def test_parse_post_no_content_or_summary(good_feed):
    entry = MockEntry(id='id1', title='T', author='A', link='http://x.com',
                      published='2026-01-01')
    p = rsslib.parse_post(good_feed, entry)
    assert p.content == 'No content found.'

def test_parse_post_updated_date_fallback(good_feed):
    entry = MockEntry(id='id1', title='T', author='A', link='http://x.com',
                      updated='2026-06-01T00:00:00+00:00', summary='c')
    p = rsslib.parse_post(good_feed, entry)
    assert '2026-06-01' in p.date
