#!/usr/bin/python
# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti.models import *

from django.db.models.query import QuerySet
from django.db.models import Max, Min, Count

from decimal import Decimal, Context, Inexact
import json
from math import log
import logging
from dateutil import parser
import urllib
import urllib2
import urlparse
import cgi
import subprocess
import warnings
import time
import random
import string
import datetime
import nltk
import os
from django.conf import settings
from postagger import POSTagger

# hide deprecation warnings
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
        self.stop_words = None
        self.token_stemmer = None
        self.token_lemmatizer = None

    def handle(self, *args, **options):
        if args is None or len(args) < 2:
            pages = Page.objects.all()
            for page in pages:
                self._log.info("Page #%s: %s" % (page.id, page.fb_page_name))
            raise CommandError('Invalid arguments. Expected: <page_id> <action>, where action might be: extract, tfidf, webidf')


        page_id = args[0]
        action = args[1]

        if page_id == 'setup':
            self._log.info("invoking nltk download")
            nltk.download()
            exit()

        self._log.info('AnalyticsCommand initializing.')

        self._log.info('Page-Id: %s' % page_id)
        page = Page.objects.get(id=page_id)

        if action == "extract":
            self.processPageExtract(page)
        elif action == "tfidf":
            self.processTfIdf(page)
        elif action == "webidf":
            self.processWebIdf(page)
        else:
            self._log.warn("Unknown action: %s" % action)

        self._log.info("All done for now.")

    def is_stop_word(self, term):
        # read stop word file (only executed once)
        self.read_stop_words()
        return term in self.stop_words

    def read_stop_words(self):
        if not self.stop_words is None:
            return
        res = {}
        for word in open(os.path.join(settings.STATIC_ROOT, 'stop_words'), 'rt').read().split('\r\n'):
            if not word is None and word != '' and not word in res:
                res[word] = True
        self.stop_words = res

    #http://stackoverflow.com/questions/16080952/django-cannot-convert-float-to-decimal-first-convert-the-float-to-a-string
    def float_to_decimal(self, f):
        "Convert a floating point number to a Decimal with no loss of information"
        n, d = f.as_integer_ratio()
        numerator, denominator = Decimal(n), Decimal(d)
        ctx = Context(prec=60)
        result = ctx.divide(numerator, denominator)
        while ctx.flags[Inexact]:
            ctx.flags[Inexact] = False
            ctx.prec *= 2
            result = ctx.divide(numerator, denominator)
        return result


    def processWebIdf(self, currentpage):
        kp_method_source = KeyphraseMethod.objects.get(name='pos_sequence')
        kp_method, created = KeyphraseMethod.objects.get_or_create(name='webidf_wiki')
        for cur_kp in Keyphrase.objects.filter(method=kp_method_source).all():
            kp_term = "\"" + cur_kp.term.encode('utf-8') + "\""
            apiurl = "http://en.wikipedia.org/w/api.php?action=query&list=search&" + urllib.urlencode({'srsearch': kp_term}, True) + "&srprop=timestamp&format=json"
            json_response = urllib2.urlopen(apiurl)
            res = json.loads(json_response.read())
            if 'query' in res and 'searchinfo' in res['query'] and 'totalhits' in res['query']['searchinfo']:
                idftotal = float(res['query']['searchinfo']['totalhits']) / float(4376448)
                kps, created = Keyphrase.objects.get_or_create(term=cur_kp.term, method=kp_method, defaults={'val': self.float_to_decimal(idftotal)})
                if created:
                    self._log.info("Keyphrase \"%s\" <- %s (created)" % (kps.term, kps.val))
                else:
                    self._log.info("Keyphrase \"%s\" <- %s" % (kps.term, kps.val))
            else:
                self._log.warn("Invalid JSON response:")
                print json_result
                exit()

        #kp_method = KeyphraseMethod.objects.get(name='webidf-wiki')
        #kps = Keyphrase.objects.get_or_create(term=cur8'term', method=kp_method, defaults={'val': str(curcount)0)

    def processTfIdf(self, currentpage):
        for ngram_level in range(1, self.max_ngram_level+1):
           #self.processTf(currentpage, ngram_level)
            self.processIdf(currentpage, ngram_level)
        self.processIdfGeneric(currentpage, "pos_sequence", "idf-pos")

    def processTf(self, currentpage, ngram_level):
        self._log.info("Processing term frequencies for ngram level %s" % ngram_level)
        raw_freq = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = currentpage, method__name__exact = "ngram-%s" % ngram_level).values('term').distinct().annotate(dcount=Count('term'))
        self._log.info("NGrams total at level %s: %s" % (ngram_level, len(raw_freq)))
        # TODO delete previous
        ngram_freqs = raw_freq
        kp_method = KeyphraseMethod.objects.get(name="tf-raw-%s" % ngram_level)
        for cur in ngram_freqs:
            kp, created = Keyphrase.objects.get_or_create(term=cur['term'], method=kp_method, defaults={'val': str(cur['dcount'])})
            if created:
                print kp
                kp.save()

    def processIdf(self, currentpage, ngram_level):
        self._log.info("Processing inverse document frequencies for ngram level %s" % ngram_level)
        self.processIdfGeneric(currentpage, "ngram-%s" % ngram_level, "idf-%s" % ngram_level)

    def processIdfGeneric(self, currentpage, kp_source, kp_target):
        kp_method = KeyphraseMethod.objects.get(name=kp_target)

        document_count = Post.objects.filter(page=currentpage).count()
        source_ngrams = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = currentpage, method__name__exact = kp_source).annotate(num_docs=Count('postkeyphraseassoc'))
        print source_ngrams[1:10]
        print source_ngrams[0].num_docs
        print document_count
        for cur_ngram in source_ngrams:
            curidf = log(document_count / cur_ngram.num_docs)
            kp, created = Keyphrase.objects.get_or_create(term=cur_ngram.term, method=kp_method, defaults={'val': str(curidf), 'normalized': cur_ngram.normalized})
            if created:
                print kp
                kp.save()

    def processPageExtract(self, currentpage):
        self._log.info("Starting processing on content in page %s" % currentpage.fb_page_name)

        self.postagger = POSTagger(self.callbackPOS)

        posts = Post.objects.filter(page=currentpage).exclude(posttype__exact='comment')
        self._log.info("%s posts" % len(posts))

        for post in posts:
            self.processPost(post)
            comments = Post.objects.filter(page=currentpage, parent=post, posttype__exact='comment')
            self._log.info("Post #%s: Comments: %s" % (post.id, len(comments)))
            for comment in comments:
                self.processPost(comment)

        # tag remaining posts
        self.postagger.enqueue(forceProcessing=True)

    def callbackPOS(self, opost, text, tagged):
        valid_keyphrases = self.extractKeyphrases(tagged)
        kp_method = KeyphraseMethod.objects.get(name="pos_sequence")

        for kp_text, kp_offset, kp_len in valid_keyphrases:
            if kp_text == opost.page.name.lower():
                continue # skip terms that equal the page name
            self._log.info('KP:%s' % kp_text)
            kp, created = Keyphrase.objects.get_or_create(term=kp_text, method=kp_method, defaults={'val': "1.0", 'normalized': kp_text}) # TODO normalize these terms?
            if created:
                print kp
                kp.save()
            kp_assoc, created = PostKeyphraseAssoc.objects.get_or_create(post=opost, keyphrase=kp, offset=kp_offset, length=kp_len)
            if created:
                print kp_assoc
                kp.save()

    def sliceParallel(self, list_a, list_b, length):
        for idx in range(len(list_a) - length):
            yield [list_a[idx:idx + length], list_b[idx : idx+length], idx, length]

    def extractKeyphrases(self, tagged):
        kp_len_max = 5
        kp_len_min = 2

        tokens = []
        tags = []
        for token, tag, confidence in tagged:
            tokens.append(token)
            tags.append(tag)

        kp_results = []

        for kp_cur_len in reversed(range(kp_len_min, kp_len_max)):
            for slice_tags, slice_tokens, offset, length in self.sliceParallel(tags, tokens, length=kp_cur_len):
                if self.isKeyphraseSequence(slice_tags):
                    self._log.info("Tag sequence (%s) for token sequence (%s) is considered a valid keyphrase" % (" ".join(slice_tokens), " ".join(slice_tags)))
                    kp_results.append([" ".join(slice_tokens), offset, len(slice_tokens)])

        return kp_results

    def isKeyphraseSequence(self, tags):
        all_nouns = True
        seen_non_adj = False
        all_nouns_after_adj = True
        last_adj = -1

        for idx in range(len(tags)):
            tag = tags[idx]
            if tag == 'A':
                last_adj = idx
            else:
                seen_non_adj = True

            if seen_non_adj and tag != 'N':
                all_nouns_after_adj = False

            if tag != 'N':
                all_nouns = False

        ends_with_noun = tags[len(tags)-1] == 'N'

        return all_nouns or (all_nouns_after_adj and last_adj > -1)

    def processPost(self, post):
        if post.text is not None and post.text != "":
            curtext = post.text.encode('utf-8')
            tokens = [word for sent in nltk.sent_tokenize(curtext) for word in nltk.word_tokenize(sent)]
            tokens = self.normalizeTokens(tokens)
            text = nltk.Text(tokens)
            self.processText(post, text)

    def processText(self, post, text):
        # enqueue post for POS tag batch processing
        tagged_text = self.postagger.enqueue(post, text)

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
            if term in [".", ",", "-", "+", "%", "?", "!", "$", "&", "/", "\"", "'", "`", "`", "|", ":", ";", ")", "(", "[", "]", "{", "}"]:
                return False
            if self.is_number(term):
                return False
            if self.is_stop_word(term):
                return False
            if term.find('.') > -1: # or term.find('/') > -1 or term.find("?"): # url parts
                return False
        return True

    def storeNGrams(self, opost, ngram_level, ngram_coll):
        kp_method = KeyphraseMethod.objects.get(name="ngram-%s" % ngram_level)

        curoffset = 0
        for curngram in ngram_coll:
            curoffset = curoffset + 1
            if not self.isValidNGram(curngram):
                continue
            curngram = [self.stripSpecialChars(w) for w in curngram]
            curterm = " ".join(curngram)
            curterm_normalized = " ".join(self.normalizeNGram(curngram))

            kp, created = Keyphrase.objects.get_or_create(term=curterm, method=kp_method, defaults={'val': "1.0", 'normalized': curterm_normalized})
            if created:
                print kp
                kp.save()
            kp_assoc, created = PostKeyphraseAssoc.objects.get_or_create(post=opost, keyphrase=kp, offset=curoffset, length=ngram_level)
            if created:
                print kp_assoc
                kp.save()

    def normalizeNGram(self, tokens):
        if self.token_stemmer is None:
            #self.token_stemmer = nltk.PorterStemmer()
            self.token_stemmer = nltk.LancasterStemmer()
        #if self.token_lemmatizer is None:
            #self.token_lemmatizer = nltk.WordNetLemmatizer()

        return [self.token_stemmer.stem(w) for w in tokens]
        #return [self.token_lemmatizer.lemmatize(w) for w in tokens]

    def normalizeTokens(self, tokens):
        return [w.lower() for w in tokens]

    def stripSpecialChars(self, word):
        return word.strip("\r\n.,-+%?!$&/\\'`|:;)([]{}\t\" ")

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

