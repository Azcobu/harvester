# Retrieves random posts from listed sources for use in automated testing

import pickle
import feedparser
from random import choice

post_sources = 'post-sources.txt'

def load_data():
    with open(post_sources, 'r') as infile:
        return [x.strip() for x in infile.readlines()]

def save_file(fname, indata):
    print(f'Saving {fname}...', end='')
    with open(fname, 'wb') as outfile:
        #indata = indata.encode('ascii', 'ignore').decode('ascii')
        outfile.write(indata)
    print('done.')

def save_posts(feedlist):
    for counter, p in enumerate(feedlist):
        parsedfeed = feedparser.parse(p)
        '''
        if parsedfeed.entries:
            post = choice(parsedfeed.entries)
        '''
        fname = f'example-feed{counter:02}.txt'
        pickled = pickle.dumps(parsedfeed.entries)
        save_file(fname, pickled)

def main():
    save_posts(load_data())

if __name__ == '__main__':
    main()