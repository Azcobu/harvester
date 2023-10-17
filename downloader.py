import requests
import shutil
import logging
from datetime import datetime
import feedparser
import favicon
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QRunnable
import rsslib
import lxml.html
import dbhandler
import os
from urllib.parse import urlparse, unquote

class WorkerSignals(QObject):
    started = pyqtSignal(tuple)
    finished = pyqtSignal(tuple)
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)
    icondata = pyqtSignal(tuple)

class Worker(QRunnable):
    def __init__(self, max_q_size, workernum, dl_queue, db_queue, feeds,
                 dl_feeds = True, dl_icons=False, dl_imgs=False):
        super(Worker, self).__init__()
        self.max_q_size = max_q_size
        self.workernum = workernum
        self.dl_queue = dl_queue
        self.db_queue = db_queue
        self.feeds = feeds
        self.dl_feeds = dl_feeds
        self.dl_icons = dl_icons
        self.dl_imgs = dl_imgs
        self.signals = WorkerSignals()
        self.feednum = 0
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    @pyqtSlot()
    def run(self):
        while not self.dl_queue.empty():
            dl_item = self.dl_queue.get()

            self.feednum = self.max_q_size - self.dl_queue.qsize()

            if isinstance(dl_item, rsslib.Feed):
                self.generate_status_msg(dl_item)
                if self.dl_feeds:
                    self.dl_feed(dl_item)

                if self.dl_icons:
                    self.dl_icon(dl_item)
            else:
                logging.debug(f'Downloading {dl_item[1]}')
                self.save_img_to_file(dl_item)

            self.dl_queue.task_done()

    def generate_status_msg(self, feed):
        msg = (f"{self.feednum}/{self.max_q_size}: Worker {self.workernum+1} "
               f"retrieving {feed.title}")
        #logging.info(msg)
        self.signals.started.emit((msg, feed.id))

    def dl_feed(self, feed):
        unread_count = 0
        postlist = []
        logging.info(f'DL starting for {feed.title}')

        try:
            parsedfeed = feedparser.parse(feed.rss_url,
                                          etag=feed.etag,
                                          modified=feed.last_modified)
        except Exception as err:
            logging.error(f"Failed to read feed {feed.title} - {err}")
        else:
            if self.check_return_status_ok(parsedfeed, feed):
                # update last modified time and etag, both locally and in DB
                self.update_lastmod_etag(parsedfeed, feed)

                if parsedfeed.entries:
                    for p in parsedfeed.entries:
                        newpost = rsslib.parse_post(feed, p)
                        if newpost:
                            if self.dl_imgs:
                                newpost.content = self.read_edit_img_urls(newpost)
                            else:
                                newpost.strip_image_tags()
                            postlist.append(newpost)
                if postlist:
                    # QQQQ this needs work
                    #unread_count = self.feeds[feed.id].unread
                    unread_count = sum([1 for p in postlist
                                        if p.date > self.feeds[feed.id].last_read])
                    self.db_queue.put(dbhandler.DBJob("write_post_list", postlist))
        finally:
            self.signals.finished.emit((unread_count, feed.id))

    def check_return_status_ok(self, parsedfeed, feed):
        if hasattr(parsedfeed, "status"):
            if parsedfeed.status == 304:
                logging.info(f"{self.feednum}/{self.max_q_size}: Skipping {feed.id} "
                             f"as it is unchanged.")
            elif str(parsedfeed.status)[0] in ["4", "5"]:
                logging.error(f"Error retrieving feed {feed.title} - "
                                  f"error code was {parsedfeed.status}")
            else: # this accepts any other 2-- and 3-- values, needed because
                  # some feeds return 3-- codes along with a valid feed. Be nice to
                  # handle 301 permanent redirects properly in future.
                return True

    def update_lastmod_etag(self, parsedfeed, feed):
        lastmod = (parsedfeed.modified if hasattr(parsedfeed, "modified")
                                       else "Thu, 1 Jan 1970 00:00:00 GMT")
        etag = parsedfeed.etag if hasattr(parsedfeed, "etag") else "0"

        if (self.feeds[feed.id].last_modified != lastmod
            or self.feeds[feed.id].etag != etag):
            self.feeds[feed.id].last_modified = lastmod
            self.feeds[feed.id].etag = etag

            self.db_queue.put(dbhandler.DBJob("update_lastmod_etag",
                              [feed.id, lastmod, etag]))

    def dl_icon(self, feed):
        if not feed.favicon:
            try:
                logging.debug(f'Getting icon for {feed.title}')
                icons = favicon.get(feed.html_url)
                # get icon > 0 and about 64
                poss = [x for x in icons if x.height <= 64]
                if poss:
                    icon = sorted(poss, key=lambda x:x.height, reverse=True)[0]
                else:
                    icon = sorted(icons, key=lambda x:x.height)[0]
                response = requests.get(icon.url, stream=True,
                                        headers={"User-Agent": "Harvester"})
            except Exception as err:
                logging.debug(f'Icon get failed for feed {feed.title} - {err}')
            else:
                if 'text/html' not in response.headers['content-type']:
                    data = b''
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            data += chunk
                    self.db_queue.put(dbhandler.DBJob("update_favicon", [feed.id, data]))
                    self.signals.icondata.emit((feed.id, data))
                else:
                    #logging.error(f'{feed.title} - Response was text rather than binary.')
                    pass

    def extract_base_filename(self, url):
        base = urlparse(url)
        base = unquote(base.path)
        return os.path.basename(base)

    def read_edit_img_urls(self, post):
        img_dir = 'd:\\tmp\\harvimg\\'

        if post.content:
            newcon = post.content
            tree = lxml.html.fromstring(post.content)
            images = tree.xpath("//img/@src")
            for i in images:
                basename = self.extract_base_filename(i)
                new_img_path = os.path.join(img_dir, basename)
                self.dl_queue.put([post.title, i])
                # should add feed/post IDs? complicated by other characters like / :
                newcon = newcon.replace(i, new_img_path)
            return newcon

    def save_img_to_file(self, indata):
        img_dir = 'd:\\tmp\\harvimg\\'

        post_title, file_url = indata
        basename = self.extract_base_filename(file_url)
        new_img_path = os.path.join(img_dir, basename)
        if os.path.exists(new_img_path):
            logging.debug(f'Skipping download of {basename} as it already exists.')
        else:
            response = requests.get(file_url, stream=True)
            with open(new_img_path, 'wb') as outfile:
                shutil.copyfileobj(response.raw, outfile)

def main():
    testfeed = rsslib.Feed("Test Feed", "New Sun", "Main Folder",
                           "rss", "http://bhagpuss.blogspot.com/feeds/posts/default", "http://new-sun.gov",
                           None, "1970-01-01T00:00:00+00:00", '0',
                           "Thu, 1 Jan 1970 00:00:00 GMT", None)
    b = ('<p></p><div class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEidqjIh2yqddKlluk4e94FPz8OlIxBSoVvVMOwxypAf9_6MRDArE1pus3EqLFaOGfRjhhDK0C-rrINe-KqFh944YPTcINDN_U3DyrOAC9Q52yRRoFEj7aQ4vTgDYnOMHD81PELYizHUy6yZcXp82S5sCjXxqsq-0e1pLgOz78wBWavv-AruprZDW8oI/s1914/tswia1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEidqjIh2yqddKlluk4e94FPz8OlIxBSoVvVMOwxypAf9_6MRDArE1pus3EqLFaOGfRjhhDK0C-rrINe-KqFh944YPTcINDN_U3DyrOAC9Q52yRRoFEj7aQ4vTgDYnOMHD81PELYizHUy6yZcXp82S5sCjXxqsq-0e1pLgOz78wBWavv-AruprZDW8oI/w640-h352/tswia1.png" '
 'width="640" /></a></div><br />Today I finally got around to removing '
 "<i>Microsoft</i>'s idea of a pretty picture (Clue: not mine.) from the "
 'lockscreen, which had reverted to type following The Incident. I set it to '
 'Slideshow and chose an old favorite: <i>The Secret World</i>.<br '
 '/><p></p><p></p><p>In <a '
 'href="https://bhagpuss.blogspot.com/2022/05/a-tale-of-two-emus.html"><span '
 'style="color: #ff00fe;">yesterday\'s post</span></a> I mentioned how I '
 'thought <i>Vanguard </i>was one of those mmorpgs that looks better when '
 "you're playing than you'd guess from screenshots. <i>Funcom</i>'s neglected "
 'gem looks great however you view it. </p><p>I was so happy to see some of my '
 "old favorites again, I thought I'd slap a few up on the blog just for the "
 'hell of it. No particular context or reason, just a good old screenshot post '
 "like the old days. It's possible I may have used some of them before, but "
 'there are more than twelve hundred in the folder so the odds are '
 'good.</p><div class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhn3YNxecSoVQmWVRcBXG-ESzoWak1tEx_4tePLEDqokL0DkXOM0_FKeatnCRCrREaYtvj947Ljw5rTtwW803OKkxSRPIFoMHS5-7uLr1_d7fqBOlaHL29KQuJTn4NN62LUw_Q3i3M8RZJ0CujS3MGNNSxLym7Bv-dRMuWDz8sCIOeyIZ1bEY9Vabig/s1920/tswglare1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhn3YNxecSoVQmWVRcBXG-ESzoWak1tEx_4tePLEDqokL0DkXOM0_FKeatnCRCrREaYtvj947Ljw5rTtwW803OKkxSRPIFoMHS5-7uLr1_d7fqBOlaHL29KQuJTn4NN62LUw_Q3i3M8RZJ0CujS3MGNNSxLym7Bv-dRMuWDz8sCIOeyIZ1bEY9Vabig/w640-h360/tswglare1.png" '
 'width="640" /></a></div><p>Sunset. I love everything about it. The sunlight '
 'filtering through the haze, the reflections in the water...</p><div '
 'class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgGy4GYKvntD7Ro1_ve5jt8M46vQHrJuWz7McCCsVcg-XcMw2IU-QvMt1gMpPFciISWe3kVFrutzSRpcxek2w2O17Ksvn1iwVP1UooX7YtnDDmX33morX-Zh0DhJNaWI66NytX5TQNxlQ-G0R56IoIXXVy1BmojvOb23ufmMlq4WAraRv-HtB7b0FyS/s1920/tswgreenhaze1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgGy4GYKvntD7Ro1_ve5jt8M46vQHrJuWz7McCCsVcg-XcMw2IU-QvMt1gMpPFciISWe3kVFrutzSRpcxek2w2O17Ksvn1iwVP1UooX7YtnDDmX33morX-Zh0DhJNaWI66NytX5TQNxlQ-G0R56IoIXXVy1BmojvOb23ufmMlq4WAraRv-HtB7b0FyS/w640-h360/tswgreenhaze1.png" '
 'width="640" /></a></div><p>I never tire of the way the light burns through '
 'the fog, the mist, the dust. Miasmas, everywhere.<br /></p><p></p><div '
 'class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgX9lsq02bTGiJOJPQFN8mfxZleg-SUziFfP2MJp5bkG5PKIeFdXE56vngrdPxHeFWHvZhDpaz4UY_FNkGSvDm1dvfXGrexUuHj0qt3q0OckZAxom4Q8RrRXariie1XZL3GafvUw3s8-MZBNRqoTLCP2NEeWPpY_cMcBu1okB8znEadrP1nAnIq4ahI/s1920/tswmoon1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgX9lsq02bTGiJOJPQFN8mfxZleg-SUziFfP2MJp5bkG5PKIeFdXE56vngrdPxHeFWHvZhDpaz4UY_FNkGSvDm1dvfXGrexUuHj0qt3q0OckZAxom4Q8RrRXariie1XZL3GafvUw3s8-MZBNRqoTLCP2NEeWPpY_cMcBu1okB8znEadrP1nAnIq4ahI/w640-h360/tswmoon1.png" '
 'width="640" /></a></div>They make everything glow. You could read a '
 'newspaper by that moon. &nbsp;<p></p><div class="separator" style="clear: '
 'both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhVu8CIVTh_RDR4rWdxEzcUyjVpw4-ECyJtcZ3LuNnPUfw92mQe6onLdpGqSoSjqOK1hcbV74WvLlVRxGexLv9BcEn0DI0GHQNSq5QCRXTIJigezFSrV8fric25GnrRDk9pd6ALiYOYhE1Ysghtlfv7iQLtjDeXEd0y5oQAVRfXGuCGdE2NPezl9uUi/s1920/tswdesertnight1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhVu8CIVTh_RDR4rWdxEzcUyjVpw4-ECyJtcZ3LuNnPUfw92mQe6onLdpGqSoSjqOK1hcbV74WvLlVRxGexLv9BcEn0DI0GHQNSq5QCRXTIJigezFSrV8fric25GnrRDk9pd6ALiYOYhE1Ysghtlfv7iQLtjDeXEd0y5oQAVRfXGuCGdE2NPezl9uUi/w640-h360/tswdesertnight1.png" '
 'width="640" /></a></div><p>Though you could always just turn on the '
 'lights.</p><div class="separator" style="clear: both; text-align: '
 'center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjFoRXuTomApOMlDL58OVBEdQywwcaK7ArrOcwtM4_FdKfgQxfT-jYWVLntk97-smIXXfZZU-11pqV0ObWFjTRTWvKjZmVntslRswK9YWT3xMEpPTCK9FYMPbzRxkK0gmr6lbQrRorNY5BW7mgSvaZUN3uF3tdCnSGbIAlfJ9E2Hl-_FCz7NUPIrEu7/s1914/tswfire1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjFoRXuTomApOMlDL58OVBEdQywwcaK7ArrOcwtM4_FdKfgQxfT-jYWVLntk97-smIXXfZZU-11pqV0ObWFjTRTWvKjZmVntslRswK9YWT3xMEpPTCK9FYMPbzRxkK0gmr6lbQrRorNY5BW7mgSvaZUN3uF3tdCnSGbIAlfJ9E2Hl-_FCz7NUPIrEu7/w640-h352/tswfire1.png" '
 'width="640" /></a></div><p>Or maybe light a fire.</p><div class="separator" '
 'style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjHy8ZcqJ4w5CFlo8DcSa6zWBELjaD78fgVNm_Z_T4-HlpW7q_oQFhONCZ0hniqYikHJQ6KSZcAK0O6pNTVlHLR1brrxYZTQQpZDZItTnP3vdnM2LyE2vi8DX9CWCkC5bNNGvuRQItO9rrBZfbgAIdviY6qX2iCftXK8uXhnUvneKdgWF8SbiUVC0Tm/s1920/tswghost1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjHy8ZcqJ4w5CFlo8DcSa6zWBELjaD78fgVNm_Z_T4-HlpW7q_oQFhONCZ0hniqYikHJQ6KSZcAK0O6pNTVlHLR1brrxYZTQQpZDZItTnP3vdnM2LyE2vi8DX9CWCkC5bNNGvuRQItO9rrBZfbgAIdviY6qX2iCftXK8uXhnUvneKdgWF8SbiUVC0Tm/w640-h360/tswghost1.png" '
 'width="640" /></a></div><p>Then again, not everyone needs light. Or '
 'color.<br /></p><div class="separator" style="clear: both; text-align: '
 'center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjZmvWN0s2wS9uA6X64IrONYSuEBrQv4BR9sRz-OAzsCHmEbeaHpWUpJUS7Nm8Mr1dIPabyabH9Du7fWh7qY6a28HO3MlhUxVcaDq-wUYyAiYezzV7tN3TsOnJCenaCyWwjElA9C5Oom4rxn3t1rhStL2Dflv5T5iXiLE8A6FcImqJGfePanfC8uRZW/s1914/tswglow1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjZmvWN0s2wS9uA6X64IrONYSuEBrQv4BR9sRz-OAzsCHmEbeaHpWUpJUS7Nm8Mr1dIPabyabH9Du7fWh7qY6a28HO3MlhUxVcaDq-wUYyAiYezzV7tN3TsOnJCenaCyWwjElA9C5Oom4rxn3t1rhStL2Dflv5T5iXiLE8A6FcImqJGfePanfC8uRZW/w640-h352/tswglow1.png" '
 'width="640" /></a></div><p>We all shine, in our own way.<br /></p><div '
 'class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEghnLFCFMJB_JvpSKdmZwpeCLgXLRBQAl_WPgLV9cSL220-2GCoAwx3ujlGGnpvykLxDqKkd1UJwRmFE2aUbQA3PIFFdGpZA7QtPOYX_dBdVhtEH_HhFv6eChjxnMoT7a1a-rP_ENF8yI_YjWJHD5AN8rBDtPWcw5Y8wY2_Pj9HGRzA5Rd5lYdkVrnB/s1914/tswwhitesuits1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEghnLFCFMJB_JvpSKdmZwpeCLgXLRBQAl_WPgLV9cSL220-2GCoAwx3ujlGGnpvykLxDqKkd1UJwRmFE2aUbQA3PIFFdGpZA7QtPOYX_dBdVhtEH_HhFv6eChjxnMoT7a1a-rP_ENF8yI_YjWJHD5AN8rBDtPWcw5Y8wY2_Pj9HGRzA5Rd5lYdkVrnB/w640-h352/tswwhitesuits1.png" '
 'width="640" /></a></div><p>Some of us by day.<br /></p><div '
 'class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjSKU94jyEJ4cROQbkXv64BbyyAp3YYWXH27l9ygweHmCd2loCStUZzcvtl9Vdi3gzP3lkOKA-uOC3PEXctF68co3vFQa8bFTyc1F56CFybc3uLYD82xGuR69uwTTNvyLWQgWdpIep7OIpKWyTfx58sKuQptlW_PQL7zkpvwYBgUcQhlOEVDokHSxc5/s1920/tswtennis1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjSKU94jyEJ4cROQbkXv64BbyyAp3YYWXH27l9ygweHmCd2loCStUZzcvtl9Vdi3gzP3lkOKA-uOC3PEXctF68co3vFQa8bFTyc1F56CFybc3uLYD82xGuR69uwTTNvyLWQgWdpIep7OIpKWyTfx58sKuQptlW_PQL7zkpvwYBgUcQhlOEVDokHSxc5/w640-h360/tswtennis1.png" '
 'width="640" /></a></div><p>Some of us by night. Anyone for tennis?<br '
 '/></p><div class="separator" style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhMK_TgKAs7xd_fwcOArdW5xldZ65EDpJkRNVnd0YLUmu3WHZVemzU_GrIlC7hpcJg4_nzyag2Ab9LJWfEdrUqoaYWy8POEQ5CcWv1IiwqBYgGOfGMlZtMCNZdScrEAW7kHPlKVN3v106PNBYL01KpO7Oh365Bxo5b9bnX_eehxYSmnfPRCDWoVfl-n/s1920/tswnt2.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhMK_TgKAs7xd_fwcOArdW5xldZ65EDpJkRNVnd0YLUmu3WHZVemzU_GrIlC7hpcJg4_nzyag2Ab9LJWfEdrUqoaYWy8POEQ5CcWv1IiwqBYgGOfGMlZtMCNZdScrEAW7kHPlKVN3v106PNBYL01KpO7Oh365Bxo5b9bnX_eehxYSmnfPRCDWoVfl-n/w640-h360/tswnt2.png" '
 'width="640" /></a></div><p>Yeah, I\'m on the night team but don\'t let that '
 'put you off. We\'re really not that good.</p><div class="separator" '
 'style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEj7bxt0sFP4EymSs6nh1tjsirD-Q-HfUzI5c513AvPiiPV3S2Fp6OaTyqzNTnSnvmW1s84n9fIJ30mxXZxN3NNdfNbNvpSShxXvNDrScGWzm4dzjxP0vpOoktbNVPPZ42QjcMcYDtM3NeJZdz2KOvRnVFqh1LKULxSSacUFv2mUovXmDHjfFdBKjsSA/s1914/tswff1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEj7bxt0sFP4EymSs6nh1tjsirD-Q-HfUzI5c513AvPiiPV3S2Fp6OaTyqzNTnSnvmW1s84n9fIJ30mxXZxN3NNdfNbNvpSShxXvNDrScGWzm4dzjxP0vpOoktbNVPPZ42QjcMcYDtM3NeJZdz2KOvRnVFqh1LKULxSSacUFv2mUovXmDHjfFdBKjsSA/w640-h352/tswff1.png" '
 'width="640" /></a></div><p>There can be a lot of distractions, '
 'y\'know?</p><div class="separator" style="clear: both; text-align: '
 'center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEg_FhqD-7uewOBYNe-4ve8e-4Q47eejh8PT-SswtJYg62o5KMUToFIrUTeE92YeM1Us1NdSJ5tX2leuMZamcZPDli7NuXvATTKQEWsv4dT5e6PSa0-kU9rP5Vwc47sjEIk96YrHl_SsaKvYJZEBF4oztFbFyUxLEkK7MpeR7coDQyRW6tgbnEPrxfMt/s1920/tswfight1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEg_FhqD-7uewOBYNe-4ve8e-4Q47eejh8PT-SswtJYg62o5KMUToFIrUTeE92YeM1Us1NdSJ5tX2leuMZamcZPDli7NuXvATTKQEWsv4dT5e6PSa0-kU9rP5Vwc47sjEIk96YrHl_SsaKvYJZEBF4oztFbFyUxLEkK7MpeR7coDQyRW6tgbnEPrxfMt/w640-h360/tswfight1.png" '
 'width="640" /></a></div><p>Some of them big.</p><div class="separator" '
 'style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhFh7qABEyAt8pjEiZ4fIlbjUIEOq0rjpZmQp-5b8eQ_AJlR7RQvpncIy8C0fTVkkuDt7N3UwD5yI7KpHNpKsKyZmhQiIh3_xrrSEaP5kfSN6MgSd2TEO2j7dECK32fovvnlurwUBCnHwDZJsmN0kAxIVjtVu6LvUDdf1RI2RXtm9sI78bu8MAHdOYz/s1920/tswcat1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhFh7qABEyAt8pjEiZ4fIlbjUIEOq0rjpZmQp-5b8eQ_AJlR7RQvpncIy8C0fTVkkuDt7N3UwD5yI7KpHNpKsKyZmhQiIh3_xrrSEaP5kfSN6MgSd2TEO2j7dECK32fovvnlurwUBCnHwDZJsmN0kAxIVjtVu6LvUDdf1RI2RXtm9sI78bu8MAHdOYz/w640-h360/tswcat1.png" '
 'width="640" /></a></div><p>Some of them small.</p><div class="separator" '
 'style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEisIS4kIaCBNhME_X17BeoRb0wR7R4GFa-InGgm7_c46QlUeGM30yiIlK2Z2H5XmtD4Ti-Vl6LY_q3nsopUIgEzODvxMsQb6Gk27yvyCHeAfFiVX63cS1OmtI4AoCfFQtyJpgO1LassWwPqeumI6Ze3_UG5Ibyj64XS62xikGJMAgIZCxfFg8CdUhx1/s1914/tswgg1.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="352" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEisIS4kIaCBNhME_X17BeoRb0wR7R4GFa-InGgm7_c46QlUeGM30yiIlK2Z2H5XmtD4Ti-Vl6LY_q3nsopUIgEzODvxMsQb6Gk27yvyCHeAfFiVX63cS1OmtI4AoCfFQtyJpgO1LassWwPqeumI6Ze3_UG5Ibyj64XS62xikGJMAgIZCxfFg8CdUhx1/w640-h352/tswgg1.png" '
 'width="640" /></a></div><p>In the end, though, it\'s nothing we can\'t '
 'handle...</p><div class="separator" style="clear: both; text-align: '
 'center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhxdC_2M0IKJO09s8VICZ_uiphqTTIZSTRcQu0bprORMVuxIP-UJ0dTW5uF5Txc0HWKm4vbMXx1Qy0y_u5InaPlq3h87fkoeuEzKxR65zoM_sJB7mon73hWP0zqtLLdUMosry7g34HbFXbeVwERgCLs4bKJRFiCXvwAL45nF5h98CNFQpSKxvotogEN/s1920/tswgg2.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhxdC_2M0IKJO09s8VICZ_uiphqTTIZSTRcQu0bprORMVuxIP-UJ0dTW5uF5Txc0HWKm4vbMXx1Qy0y_u5InaPlq3h87fkoeuEzKxR65zoM_sJB7mon73hWP0zqtLLdUMosry7g34HbFXbeVwERgCLs4bKJRFiCXvwAL45nF5h98CNFQpSKxvotogEN/w640-h360/tswgg2.png" '
 'width="640" /></a></div><p>A girl..</p><div class="separator" style="clear: '
 'both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhbsOjVUQ8pNkJQg8mpw-1dKbj2Ad6lw9NSwkayNYB85x1q6t66mdNwJ7GNO6nx6wA--niyZzGw3IhQoSXDl41yn4L2msxqRCUUWcrgOsM2x2kxmOM29AVKmWzbysd6cIpe_uHFg3_LtuQFpTF4I1YOu_y9S2aMP6hiNff1Rij6re9GgzowhyhWVI7q/s1920/tswgg3.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhbsOjVUQ8pNkJQg8mpw-1dKbj2Ad6lw9NSwkayNYB85x1q6t66mdNwJ7GNO6nx6wA--niyZzGw3IhQoSXDl41yn4L2msxqRCUUWcrgOsM2x2kxmOM29AVKmWzbysd6cIpe_uHFg3_LtuQFpTF4I1YOu_y9S2aMP6hiNff1Rij6re9GgzowhyhWVI7q/w640-h360/tswgg3.png" '
 'width="640" /></a></div><p>Her gun...</p><div class="separator" '
 'style="clear: both; text-align: center;"><a '
 'href="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhXkia7ArR8EsZ8dAcGy08b8XDsj-r0biFtEDw5qXZ96rWnO1v781FsI983OZ07qX38VcVgdrckoh6XlHo6FJeyY0AekFy7KgyAgOMF9zErbbUY4M7cSTJiLAyl12YY8t91U-XKaBRdwoesatv3ov5jLc9XmDk9dVY3H3_ZmLOrs0y4PQw-vA4ebU6H/s1920/tswgg5.png" '
 'style="clear: left; float: left; margin-bottom: 1em; margin-right: '
 '1em;"><img border="0" height="360" '
 'src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhXkia7ArR8EsZ8dAcGy08b8XDsj-r0biFtEDw5qXZ96rWnO1v781FsI983OZ07qX38VcVgdrckoh6XlHo6FJeyY0AekFy7KgyAgOMF9zErbbUY4M7cSTJiLAyl12YY8t91U-XKaBRdwoesatv3ov5jLc9XmDk9dVY3H3_ZmLOrs0y4PQw-vA4ebU6H/w640-h360/tswgg5.png" '
 'width="640" /></a></div>And the night.')

    newpost = rsslib.Post(1, "http://new-sun.gov", "Chapter 1 - Resurrection and Death",
        "Gene Wolfe", "http://order-of-seekers.gov", '0',
        b, "None")

    from queue import Queue
    dl_q, db_q = Queue(), Queue()
    dl_q.put(testfeed)

    w = Worker(5, 0, dl_q, db_q, {}, True, False, True)
    w.read_edit_img_urls(newpost)

if __name__ == "__main__":
    main()
