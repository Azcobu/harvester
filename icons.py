import favicon
import requests
import sqlitelib

def save_icon(feed_id, html_url, curs, conn):
    try:
        icons = favicon.get(html_url)
        # get icon > 0 and about 64
        poss = [x for x in icons if x.height <= 64]
        if poss:
            icon = sorted(poss, key=lambda x:x.height, reverse=True)[0]
        else:
            icon = sorted(icons, key=lambda x:x.height)[0]
        response = requests.get(icon.url, stream=True)
    except Exception as err:
        print(f'Icon get failed for {f} - {err}')
    else:
        if 'text/html' not in response.headers['content-type']:
            data = b''
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    data += chunk
            sqlitelib.update_favicon(feed_id, data, curs, conn)
        else:
            print(f'{f} - Response was text rather than binary.')

def main():
    # still need to sanitize name as it does not handle added url elements well
    # http://www.theregister.co.uk/
    dbfile = 'd:\\tmp\\posts.db'
    curs, conn = sqlitelib.connect_DB_file(dbfile)
    #feedlist = sqlitelib.list_feeds_over_post_count(0, curs, conn)
    vd = 'https://voxday.net'
    feedlist = [vd]
    save_icon(feedlist, curs, conn)

if __name__ == '__main__':
    main()
