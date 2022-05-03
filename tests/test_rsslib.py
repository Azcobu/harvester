import sys
import pickle
import pytest
import feedparser
from os import listdir, path

sys.path.append('..')
import rsslib

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
def good_opml():
    with open('valid.opml', 'r') as infile:
        return infile.read()

@pytest.fixture
def rss_feed():
    with open('rss-feed.txt', 'r') as infile:
        return infile.read()

@pytest.fixture
def posts():
    """builds a list containing raw feed data strings"""
    postlist = []
    postfiles = sorted([x for x in listdir('testdata') if 'example-post' in x])
    for pname in postfiles:
        with open(path.join('testdata', pname), 'rb') as infile:
            postlist.append(pickle.load(infile))
    return postlist

def test_feed_class_basics(good_feed):
    assert good_feed.feed_id == 'GoodFeed01'
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

def test_opml_parse(good_opml):
    f = rsslib.parse_opml('valid.opml')
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
