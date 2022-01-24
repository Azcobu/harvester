import feedparser
import opml
#http://www.reddit.com/r/python/.rss

class Feed:
    def __init__(self, f_id, title, folder, f_type, rss_url, html_url, tags=[]):
        self.f_id = f_id
        self.title = title
        self.folder = folder
        self.f_type = f_type
        self.rss_url = rss_url
        self.html_url = html_url
        self.tags = tags

class Post:
    pass

def open_opml_file(infile):
    try:
        with open(infile, 'r') as inf:
            outdata = inf.read()
    except Exception as err:
        print(err)
    return outdata

def parse_opml(infile):
    #data = open_opml_file(infile)
    currfolder = ''
    feedlist = opml.parse(infile)
    feeds = {}

    for x in range(len(feedlist)):
        currfolder = feedlist[x].text
        feeds[currfolder] = []
        #print(feedlist[x].text)
        for y in range(len(feedlist[x])):
            data = feedlist[x][y]
            if hasattr(data, 'htmlUrl'):
                #print(' - ' + data.text + ' - ' + data.htmlUrl)
                feeds[currfolder].append(data.title)

    feeds = {k:sorted(v) for k, v in feeds.items()}
    print(feeds)

def retrieve_feed(feed_url):
    feed = feedparser.parse(feed_url)

    #for post in feed.entries:
    #    print(post.title + ": " + post.link)

    post = feed.entries[0]
    print(post)
    return str(post)

def save_data(outdata):
    try:
        with open(r'd:/tmp/rss-test.txt', 'w') as outfile:
            outfile.write(outdata)
    except Exception as err:
        print(f'{err}')

def main():
    #retrieve_feed('http://www.reddit.com/r/python/.rss')
    slashdot = 'http://rss.slashdot.org/Slashdot/slashdotMain'
    posts = retrieve_feed(slashdot)
    save_data(posts)
    #parse_opml('d:\\tmp\\blw10.opml')

if __name__ == '__main__':
    main()
