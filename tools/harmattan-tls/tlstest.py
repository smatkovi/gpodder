import sys, socket, time, urllib2, urllib, logging
logging.basicConfig(level=logging.INFO)
# run with the package installed (or PYTHONPATH=src from a checkout)
from gpodder import tlsfix
print 'install ->', tlsfix.install()
socket.setdefaulttimeout(15)
urls = [
    'https://feeds.npr.org/510289/podcast.xml',
    'https://feeds.simplecast.com/54nAGcIl',
    'https://anchor.fm/s/1e6bb0c8/podcast/rss',
    'https://letsencrypt.org/',
    'https://gpodder.net/api/2/tags/5.json',
    'https://www.youtube.com/feeds/videos.xml?channel_id=UCXuqSBlHAE6Xw-yeJA0Tunw',
]
for u in urls:
    t = time.time()
    try:
        r = urllib2.urlopen(u)
        data = r.read()
        print 'OK  ', u, r.getcode(), len(data), 'bytes', '%.1fs' % (time.time()-t)
    except Exception, e:
        print 'FAIL', u, repr(e)
# urllib.FancyURLopener path (download.py)
t = time.time()
try:
    fp = urllib.FancyURLopener().open('https://feeds.npr.org/510289/podcast.xml')
    print 'OK   FancyURLopener', len(fp.read()), 'bytes', '%.1fs' % (time.time()-t)
except Exception, e:
    print 'FAIL FancyURLopener', repr(e)
# negative tests
for u in ('https://expired.badssl.com/', 'https://wrong.host.badssl.com/', 'https://self-signed.badssl.com/'):
    try:
        urllib2.urlopen(u).read()
        print 'BAD  accepted', u
    except Exception, e:
        print 'GOOD rejected', u, str(e)[:120]
# raw cipher info
s = socket.create_connection(('feeds.npr.org', 443), 10)
ts = tlsfix.TLSSocket(s, 'feeds.npr.org')
print 'cipher', ts.cipher()
ts.close()
