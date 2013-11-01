#!/usr/bin/python
# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti.models import *

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
import nltk

# hide facebook deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# global logging setup
logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    args = '<page_id> <method>'
    help = 'Retrieves data for the given fb page'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self._log = logging.getLogger('cmd')
        self.max_ngram_level = 2

    def handle(self, *args, **options):
        if args is None or len(args) < 2:
            pages = Page.objects.all()
            for page in pages:
                self._log.info("Page #%s: %s" % (page.id, page.fb_page_name))
            raise CommandError('Invalid arguments. Expected: <page_id> <action>, where action might be: ngrams, ')

        page_id = args[0]
        action = args[1]

        if page_id == 'setup':
            self._log.info("invoking nltk download")
            nltk.download()
            exit()

        self._log.info('AnalyticsCommand initializing.')

        self._log.info('Page-Id: %s' % page_id)
        page = Page.objects.get(id=page_id)

        if action == "ngrams":
            self.processPageNGrams(page)
        else:
            self._log.warn("Unknown action: %s" % action)

        self._log.info("All done for now.")

    def processPageNGrams(self, currentpage):
        self._log.info("Starting processing on content in page %s" % currentpage.fb_page_name)

        posts = Post.objects.filter(page=currentpage).exclude(posttype__exact='comment')
        self._log.info("%s posts" % len(posts))

        for post in posts:
            self.processPost(post)
            comments = Post.objects.filter(page=currentpage, parent=post, posttype__exact='comment')
            self._log.info("Post #%s: Comments: %s" % (post.id, len(comments)))
            for comment in comments:
                self.processPost(comment)

    def processPost(self, post):
        if post.text is not None and post.text != "":
            curtext = post.text.encode('utf-8')
            tokens = [word for sent in nltk.sent_tokenize(curtext) for word in nltk.word_tokenize(sent)]
            tokens = self.normalizeTokens(tokens)
            text = nltk.Text(tokens)
            self.processText(post, text)

    def processText(self, post, text):
        for cur_ngram_level in range(1, self.max_ngram_level+1):
            current_ngrams = nltk.ngrams(text, cur_ngram_level)
            self.storeNGrams(post, cur_ngram_level, current_ngrams)

    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def isValidNGram(self, curngram):
        for term in curngram:
            if term in [".", ",", "-", "+", "%", "?", "!", "$", "&", "/", "\"", "'", "`", "`", ":", ";", ")", "(", "[", "]", "{", "}"] or self.is_number(term):
                return False
        return True

    def storeNGrams(self, opost, ngram_level, ngram_coll):
        kp_method = KeyphraseMethod.objects.get(name="ngram-%s" % ngram_level)

        curoffset = 0
        for curngram in ngram_coll:
            curoffset = curoffset + 1
            if not self.isValidNGram(curngram):
                continue
            curterm = " ".join(curngram)
            kp, created = Keyphrase.objects.get_or_create(term=curterm, method=kp_method, defaults={'val': "1.0"})
            if created:
                print kp
                kp.save()
            kp_assoc, created = PostKeyphraseAssoc.objects.get_or_create(post=opost, keyphrase=kp, offset=curoffset, length=ngram_level)
            if created:
                print kp_assoc
                kp.save()

    def normalizeTokens(self, tokens):
        return [w.lower() for w in tokens]

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

