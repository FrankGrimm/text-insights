from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti import models

import facebook
import logging
from dateutil import parser
import urlparse
import cgi
import subprocess
import warnings
import time
import random
import string
import datetime

import urllib2
from bs4 import BeautifulSoup
import mechanize
from fbutils import PageCrawler

# hide facebook deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# global logging setup
logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    args = '<page_id> <oauth_token>'
    help = 'Retrieves user data for the given fb page (has to be executed after retrievepage)'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self._log = logging.getLogger('cmd')

    def handle(self, *args, **options):
        if args is None or len(args) < 2:
            raise CommandError('Invalid arguments. Expected: <action>|<page_id> <oauth_token>\r\nRetrieve a token at https://developers.facebook.com/tools/explorer/ ')

        page_id = args[0]
        oauth_token = args[1]
        self._log.info('UserDataCommand initializing.')
        self._log.info('Page-Id: %s' % page_id)
        self._log.info('OAuth-Token: %s' % oauth_token)

        self.oauth_access_token = oauth_token
        self.fbConnect()

        #self.pc = PageCrawler(self.graph)
        #self.pc.retrievePageUsers(page_id)
        #self.gatherMetaData(page_id)
        if page_id == 'metadata':
            self.retrievePageMetaData()



    def retrievePageMetaData(self):
        metainfo = models.UserMeta.objects.filter(metatype__exact='page', fb_category='')
        ctr = 0
        cnt = 1#len(metainfo)
        for curentry in metainfo:
            ctr = ctr + 1
            self._log.info('[%s/%s] Checking page' % (ctr, cnt))
            #print curentry.text
            cururl = curentry.url
            if '' == cururl:
                continue
            if 'https://www.facebook.com/pages/' in cururl:
                cururl = cururl[len('https://www.facebook.com/pages'):]
                if '/' in cururl:
                    cururl = cururl[cururl.rindex('/'):]
            elif 'https://www.facebook.com/' in cururl:
                cururl = cururl[len('https://www.facebook.com'):]
            elif 'l.php?' in cururl:
                print 'External like'
                curentry.fb_category = 'External Page'
                curentry.save()
                continue

            try:
                pageinfo = self.graph.get_object(cururl)
                if 'id' in pageinfo:
                    curentry.fb_page = pageinfo['id']
                if 'category' in pageinfo:
                    curentry.fb_category = pageinfo['category']
                else:
                    curentry.fb_category = 'Undefined'
                if 'description' in pageinfo:
                    curentry.fb_page_desc = pageinfo['description']
                    #print pageinfo['description']
                curentry.save()
            except Exception, e:
                if ' was migrated to page ID ' in str(e):
                    curentry.fb_category = 'ERR:Page migrated'
                    curentry.save()
                    continue
                if 'Some of the aliases you requested do not exist' in str(e):
                    curentry.fb_category = 'ERR:Not found'
                    curentry.save()
                    continue
                print "Grapherror", e
                if 'An unexpected error has occurred' in str(e):
                    continue
                if 'Unsupported get request' in str(e):
                    continue
                exit()

    def gatherMetaData(self, page_id):
        log = self._log
        page = models.Page.objects.get(id=page_id)
        log.info("Processing page \"%s\"" % page.fb_page_name)
        pageuser_ids = models.Post.objects.filter(page__exact=page).values('createuser').distinct()
        pageusers = models.User.objects.filter(id__in=pageuser_ids)
        pageusercount = pageusers.count()

        user_idx = 0
        for user in pageusers:
            user_idx = user_idx + 1
            print "[%s/%s] User id %s" % (user_idx, pageusercount, user.id)
            if models.UserMeta.objects.filter(user__exact=user).count() == 0:
                self.gatherMetaDataForUser(page, user)

    def gatherMetaDataForUser(self, page, curuser):
        log = self._log
        user_uri = "https://facebook.com/%s?_fb_noscript=1" % curuser.id
        log.info("Retrieving page <%s>" % user_uri)

        ul2res = ""
        try:
            ul2res = urllib2.urlopen(user_uri).read()
        except urllib2.HTTPError, e:
            log.warn(e)
            return

        soup = BeautifulSoup(ul2res)

        #<link rel="alternate" media="handheld" href="https://www.facebook.com/XYZ" />
        username = ""
        try:
            row = soup('link', {'rel': 'alternate'})[0]
            username = row['href'].split("/")
            username = username[len(username)-1]
            print "Resolved username: <%s> " % username
        except:
            log.warn("Error retrieving username")
            return

        user_uri = "https://facebook.com/%s/about?_fb_noscript=1" % username
        log.info("Retrieving page <%s>" % user_uri)
        #br = mechanize.Browser()
        #br.set_handle_robots(False)
        #br.addheaders =[('User-Agent', "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; WOW64; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; Media Center PC 6.0; InfoPath.3; AskTB5.6)")]
        #r = br.open(user_uri)
        #ul2res = r.read()
        #log.info("Page title: %s" % br.title())

        ul2res = ""
        try:
            ul2res = urllib2.urlopen(user_uri).read()
        except urllib2.HTTPError, e:
            log.warn(e)
            return

        ul2res = ul2res.replace('<meta http-equiv="refresh" ', '<meta http-equiv="ignore_refresh" ')
        ul2res = ul2res.replace('--></code>', '')
        ul2resA = ul2res.split('<code class="hidden_elem" id="')
        ul2resB = [ ul2resA[0] ]
        for cur in ul2resA[2:len(ul2resA)]:
            idx = cur.find('"')
            if idx > -1:
                cur = cur[idx+6:len(cur)]
            ul2resB.append(cur)
        ul2res = ''.join(ul2resB)
        soup = BeautifulSoup(ul2res)

        favs = soup('div', {'id': 'favorites'})
        if len(favs) == 0:
            log.info('No fav info')
            return
        favs = favs[0]

        links = favs.find_all('a')
        for link in links:
            page_title = link.text
            page_link = link['href']

            if page_link == '#':
                log.info("Info: %s" % page_title)
                continue

            umo, created = models.UserMeta.objects.get_or_create(user=curuser, text=page_title, defaults={'url':page_link})
            if created:
                log.info('Created metadata entry %s' % umo)

        time.sleep(1)
        return

    def fbConnect(self):
        self.graph = facebook.GraphAPI(self.oauth_access_token)
        self._log.info("GraphAPI instance authenticated" % self.graph)

