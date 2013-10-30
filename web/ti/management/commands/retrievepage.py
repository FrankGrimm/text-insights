from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti import models

import facebook
import logging
from dateutil import parser
import urllib
import urlparse
import cgi
import subprocess
import warnings
import time
import random
import string
import datetime

# hide facebook deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# global logging setup
logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    args = '<page_id> <oauth_token>'
    help = 'Retrieves data for the given fb page'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self._log = logging.getLogger('cmd')

    def handle(self, *args, **options):
        if args is None or len(args) < 2:
            raise CommandError('Invalid arguments. Expected: <page_id> <oauth_token>\r\nRetrieve a token at https://developers.facebook.com/tools/explorer/')

        page_id = args[0]
        oauth_token = args[1]
        self._log.info('RetrievePageCommand initializing.')
        self._log.info('Page-Id: %s' % page_id)
        self._log.info('OAuth-Token: %s' % oauth_token)

        self.anon = AnonymizeUsers()
        self.oauth_access_token = oauth_token
        self.fbConnect()

        self.pc = PageCrawler(self.graph)
        self.pc.retrievePageContent(page_id, self.anon)

    def fbConnect(self):
        self.graph = facebook.GraphAPI(self.oauth_access_token)
        self._log.info("GraphAPI instance authenticated" % self.graph)

class PageCrawler(object):
    def __init__(self, graph):
        self._log = logging.getLogger('crawler')
        self._log.info("Initializing")
        self.maxpages = 20
        self.pagecount = 0
        self.graph = graph
        self.posts = []

    def retrievePageContent(self, pageid, anon):
        self.abort = False
        self.anon = anon
        graph = self.graph
        log = self._log
        pageinfo = graph.get_object(pageid)
        log.info("Processing page \"%s\" (id %s, category %s, likes: %s)" % (pageinfo["username"], pageinfo["id"], pageinfo["category"], pageinfo["likes"]))

        try:
            pagefeed = graph.get_object(pageid + "/feed")
            self.processFeed(pagefeed)
        except Exception, e:
            self._log.warn(e)
            raise e
        log.info("Pages processed: %s" % self.pagecount)
        log.info("Posts: %s" % len(self.posts))

        texts = []

        types = []
        ccount = 0
        clikes = 0
        for post in self.posts:
            ccount = ccount + len(post.comments)
            clikes = clikes + post.likecount
            for comment in post.comments:
                texts.append(comment.content)
                clikes = clikes + comment.likecount
            if not post.type in types:
                types.append(post.type)

        log.info("Comments: %s" % ccount)
        log.info("Post types: %s" % ','.join(types))

        textcharcount = 0
        wordcount = 0
        to_be_removed = ".,:!"

        for text in texts:
            textcharcount = textcharcount + len(text)
            s = text
            for c in to_be_removed:
                s = s.replace(c, '')
            wordcount = wordcount + len(s.split())
        log.info("Average comment length: %s" % (float(textcharcount) / float(len(texts))))
        log.info("Average words per comment: %s" % (float(wordcount) / float(len(texts))))
        log.info("Unique commenters: %s" % len(anon.usedaliases))

        log.info("Trying to populate db")
        # page owner
        p_owner, created = models.User.objects.get_or_create(id=long(pageinfo["id"]), defaults={'fullname':pageinfo["name"], 'alias':("page-%s" % pageinfo["username"])} )
        p_owner.save()
        if created:
            log.info("Created user entry for the page. %s" % pageinfo["id"])
        else:
            log.info("Using existing page user entry. %s" % pageinfo["id"])

        # page
        p = None
        try:
            p = models.Page.objects.get(fb_page_id=pageinfo["id"])
            log.info("Page entry already exists.")
        except ObjectDoesNotExist:
            log.info("New page entry required. Creating.")
            p = models.Page.objects.create(fb_page_id=pageinfo["id"], fb_page_name=pageinfo["name"], last_updated=datetime.datetime.today(), owner=p_owner)

        p.save()

        # users
        for user_id in self.anon.userlist:
            userinfo = self.anon.userlist[user_id]
            userobj, created = models.User.objects.get_or_create(id=long(user_id), defaults={'fullname': userinfo["name"], 'alias':userinfo["alias"]})
            if created:
                userobj.save()
                log.info("Created new user #%s (alias: %s)" % (userobj.id, userobj.alias))

        # posts
        for post in self.posts:
            postts = parser.parse(post.timestamp).replace(tzinfo=None)
            postuser = models.User.objects.get(id=long(post.user["id"]))
            postobj, created = models.Post.objects.get_or_create(fb_post_id=post.id, defaults={'posttype': post.type, 'text': post.content, 'createtime': postts, 'parent': None, 'page': p, 'createuser': postuser, 'likes': post.likecount})
            if created:
                postobj.save()
                log.info("Post %s saved to database" % post.id)
            else:
                log.info("Post %s already stored" % post.id)

            for comment in post.comments:
                commentts = parser.parse(comment.timestamp).replace(tzinfo=None)
                commentuser = models.User.objects.get(id=long(comment.user["id"]))
                commentobj, created = models.Post.objects.get_or_create(fb_post_id=comment.id, defaults={'posttype': comment.type, 'text': comment.content, 'createtime': commentts, 'parent': postobj, 'page': p, 'createuser': commentuser, 'likes': comment.likecount})
                if created:
                    commentobj.save()
                    log.info("Comment %s saved to database" % comment.id)
                else:
                    log.info("Comment %s already stored" % comment.id)

    def processFeed(self, pagefeed):

        graph = self.graph
        log = self._log

        self.maxpages = self.maxpages - 1
        if self.maxpages <= 0:
            self.abort = True
            log.info("Not fetching more pages. Maximum exceeded.")

        self.pagecount = self.pagecount + 1
        try:
            nextpage = pagefeed["paging"]["next"]

            if nextpage.startswith("https://graph.facebook.com/"):
                print nextpage
                nextpage = urlparse.urlparse(nextpage)
                qs = cgi.parse_qs(nextpage.query)
                print qs
                #del qs['access_token']
                nextpage = nextpage.path #+ "?" + urllib.urlencode(qs, True)
                nextpage = nextpage[1:]
                nextpage_args = qs

        except KeyError:
            # no next page
            log.info("Hit last page. Aborting.")
            self.abort = True

        pagedata = pagefeed["data"]
        lpd = len(pagedata)
        log.info("Processing %s feed items" % lpd)
        self.addData(pagedata, self.posts)

        if lpd == 0:
            log.info("Hit empty data response. Aborting.")
            self.abort = True

        if not self.abort:
            log.info("Requesting next page of data <%s>" % nextpage)
            pagefeed = graph.request(nextpage, nextpage_args)
            time.sleep(1)
            self.processFeed(pagefeed)

    def addData(self, data, target):
        for postdata in data:
            id = postdata["id"]
            try:
                type = postdata["type"]
            except:
                type = "comment"

            user = dict(id=postdata["from"]["id"], name=postdata["from"]["name"])
            content = ""
            try:
                content = postdata["message"]
            except:
                pass
            try:
                content = postdata["story"]
            except:
                pass

            timestamp = postdata["created_time"]
            likecount = 0
            try:
                likecount = len(postdata["likes"]["data"])
            except:
                pass
            p = Post(id, type, user, content, timestamp, likecount, self.anon)

            comments = None
            try:
                comments = postdata["comments"]["data"]
            except:
                pass

            if comments is not None:
                self.addData(comments, p.comments)

            self._log.info("%s" % p)
            for comment in p.comments:
                comment.post = p

            target.append(p)

class AnonymizeUsers(object):
    def __init__(self):
        self.userlist = dict()
        self.usedaliases = []

    def getUserById(self, user_id):
        if user_id in self.userlist:
            return self.userlist[user_id]

    def getUserByName(self, user_name):
        for user_key in self.userlist:
            user = self.userlist[user_key]
            if user["name"] == user_name:
                return user
        return None

    def getUserId(self, user):
        if not user["id"] in self.userlist:
            self.userlist[user["id"]] = dict(id = user["id"], name=user["name"], alias=None)

            newalias = None
            while newalias is None or newalias in self.usedaliases:
                newalias = self.generateAlias()
            self.userlist[user["id"]]["alias"] = newalias
            self.usedaliases.append(newalias)

        return self.userlist[user["id"]]["alias"]

    def generateAlias(self):
        #http://stackoverflow.com/questions/2257441/python-random-string-generation-with-upper-case-letters-and-digits
        newalias = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(7))
        return newalias

class Post(object):
    def __init__(self, id, type, user, content, timestamp, likecount, anoninstance):
        self.id = id
        self.user = user
        self.type = type
        self.content = content
        self.timestamp = timestamp
        self.likecount = likecount
        self.comments = []
        self.post = None
        self.anon = anoninstance

    def __str__(self):
        return "Post[id=%s;type=%s;user=%s(%s):%s:;ts=%s;likes=%s;comments=%s]:\r\n%s" % (self.id, self.type, self.user["name"], self.user["id"], self.anon.getUserId(self.user), self.timestamp, self.likecount, len(self.comments), self.content)


