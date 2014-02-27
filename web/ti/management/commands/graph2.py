#!/usr/bin/python
# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti.models import *

from django.db.models.query import QuerySet
from django.db.models import Max, Min, Count

from decimal import Decimal, Context, Inexact
from math import log
import logging
import cgi
import subprocess
import warnings
import time
import random
import string
import datetime
import numpy as np, scipy.sparse

import nltk
from nltk.tokenize.regexp import WhitespaceTokenizer

from itertools import combinations

# no interactive display
#import matplotlib as mpl
#mpl.use('Agg')

#import matplotlib.pyplot as plt
import networkx as nx

import os
from django.conf import settings

# hide deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# global logging setup
logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    args = '<page_id> <method>'
    help = 'Computes graph data for the given page'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self._log = logging.getLogger('cmd')

    def handle(self, *args, **options):
        if args is None or len(args) < 1:
            pages = Page.objects.all()
            for page in pages:
                self._log.info("Page #%s: %s" % (page.id, page.fb_page_name))
            raise CommandError('Invalid arguments. Expected: <page_id>')

        page_id = args[0]

        self._log.info('GraphCommand initializing.')

        self._log.info('Page-Id: %s' % page_id)
        page = Page.objects.get(id=page_id)

        self.allTextGraph(page)
        #self.kpGraph(page)
        #self.buildGraph(page)

        self._log.info("All done for now.")

    def getNextIndex(self):
        self.nextFreeIndex = self.nextFreeIndex + 1
        return self.nextFreeIndex - 1

    def allTextGraph(self, page):
        pageowner = page.owner
        pageposts = Post.objects.filter(page__exact=page)

        self.stop_words = None
        self.idfCache = {}

        userterms = {}

        pageusers = User.objects.filter(id__in = pageposts.exclude(createuser__exact=pageowner).values('createuser').distinct() )
        pageusers_count = len(pageusers)
        print "Calculating vectors for %s users" % pageusers_count

        self.nextFreeIndex = 0
        curuseridx = 0
        for currentuser in pageusers:
            curuseridx = curuseridx + 1
            print "tok+tf %s/%s" % (curuseridx, pageusers_count)
            terms = self.getUserTfVector(page, currentuser, pageposts)
            if not terms is None:
                userterms[currentuser.id] = terms
        print "Maximal index: %s" % self.nextFreeIndex

        self.postcount = len(pageposts)
        print "Calculating IDF, posts: %s, terms: %s" % (self.postcount, len(self.idfCache))
        curuseridx = 0
        terms_with_idf = {}
        for user_id in userterms:
            curuseridx = curuseridx + 1
            print "idf %s/%s" % (curuseridx, pageusers_count)
            tokens = self.calculateIdf(userterms[user_id])
            terms_with_idf[user_id] = tokens

        print "tfidf"
        curuseridx = 0
        for user_id in terms_with_idf:
            curuseridx = curuseridx + 1
            print "tfidf %s/%s" % (curuseridx, pageusers_count)
            tokens = self.calculateTfIdf(terms_with_idf[user_id])
            userterms[user_id] = tokens

        del terms_with_idf

        print "Terms: %s" % len(self.idfCache)
        print "Calculating term IDs"
        termIds = self.calculateTermIds(userterms)

        uservectors = self.getUserVectors(userterms, termIds, len(self.idfCache), pageusers_count)
        userswithindex, usermatrix = self.getUserMatrix(uservectors)

        print "Creating graph"
        graph = nx.Graph()

        graph.add_nodes_from(pageusers)
        for i1 in range(usermatrix.shape[0]-1):
            max_edge = None
            max_edge_val = 0.0
            for i2 in range(usermatrix.shape[0]-1):
                if i1 == i2:
                    continue
                u1 = userswithindex[i1]
                u2 = userswithindex[i2]
                u1u2val = usermatrix[i1][i2]
                if u1u2val > max_edge_val:
                    max_edge = u2
                    max_edge_val = u1u2val

            if max_edge_val > 0.0 and not max_edge is None:
                self.add_edge(graph, u1, max_edge)

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)
        print "Nodes: %s Edges: %s" % ( len(graph.nodes()), len(graph.edges()) )
        self.removeSingletons(graph)
        print "Nodes: %s Edges: %s" % ( len(graph.nodes()), len(graph.edges()) )

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)

        self.deleteClusters(page)

        print "storing"
        cpage = page
        for compidx in range(len(components)-1):
            component = components[compidx]
            newcluster = UserCluster.objects.create(page=cpage)
            newcluster.save()
            tags = {}
            tagcounts = {}
            for user_id in component:
                adduser = pageusers.filter(id__exact=user_id)[0]
                newassoc = UserClusterAssoc.objects.create(cluster = newcluster, clusteruser = adduser)
                print user_id
                newassoc.save()

                for t, tfidf in userterms[user_id]:
                    if not t in tagcounts:
                        tagcounts[t] = 1.0
                    else:
                        tagcounts[t] = tagcounts[t] + 1.0
                    if not t in tags:
                        tags[t] = tfidf
                    else:
                        tags[t] = tags[t] + tfidf
            for t in tags.keys():
                tweight = tags[t] / tagcounts[t]
                print t
                newterm = UserClusterTerm.objects.create(cluster = newcluster, clusterterm = t, termweight = tweight)
                newterm.save()

            print "Component #%s Users: %s Tags (%s): \"%s\"" % (compidx, len(component), len(tags.keys()), ",".join(tags.keys()))

    def deleteClusters(self, page):
        print "cleaning"
        delclusters = 0
        for currentcluster in UserCluster.objects.filter(page__exact=page):
            uca = UserClusterAssoc.objects.filter(cluster__exact=currentcluster)
            uca.delete()
            uct = UserClusterTerm.objects.filter(cluster__exact=currentcluster)
            uct.delete()
            currentcluster.delete()
            delclusters = delclusters + 1
        print "Deleted %s clusters" % delclusters

    def getUserMatrix(self, uservectors):
        userswithindex = uservectors.keys()
        usermatrix = np.zeros([len(userswithindex)+1, len(userswithindex)+1])

        u1idx = 0

        for u1 in userswithindex:
            u2idx = 0
            for u2 in userswithindex:
                u2idx = u2idx + 1
                if u1 == u2:
                    continue

                u1_vec = uservectors[u1][0]
                u2_vec = uservectors[u2][0]
                u1u2dot = np.dot(u1_vec, u2_vec)
                usermatrix[u1idx][u2idx] = u1u2dot

            u1idx = u1idx + 1
            print "matrix %s/%s" % (u1idx, len(userswithindex))
        return (userswithindex, usermatrix)

    def getUserVectors(self, userterms, termIds, vectorlen, pageusers_count):
        uservectors = {}

        curuseridx = 0
        for user_id in userterms.keys():
            curuseridx = curuseridx + 1
            print "vec %s/%s" % (curuseridx, pageusers_count)

            currentvector = [0.0] * vectorlen

            terms = []
            for w, tfidf in userterms[user_id]:
                terms.append(w)
                currentvector[ termIds[w] ] = tfidf

            uservectors[user_id] = (np.array(currentvector), terms)
            #print ", ".join(map(str, currentvector))
            #print ", ".join(terms)

        return uservectors

    def calculateTermIds(self, userterms):
        next_id = 0
        ids = {}
        for user_id in userterms:
            for w, tfidf in userterms[user_id]:
                if not w in ids:
                    ids[w] = next_id
                    next_id = next_id + 1
        return ids

    def getIdf(self, term):
        if term in self.idfCache:
            return float(self.postcount) / self.idfCache[term]

        print "Missing IDF: %s " % term
        exit()

    def getUserTfVector(self, page, currentuser, pageposts):
        tok = {}

        for post in pageposts.filter(createuser__exact=currentuser):
            usertokens = self.getToken(post)
            for w, tf in usertokens:
                if not w in tok:
                    tok[w] = tf
                else:
                    tok[w] = tok[w] + tf

        return [(w, tok[w]) for w in tok]

    def getToken(self, post):
        self.tokenizer = WhitespaceTokenizer()
        if post.text is not None and post.text != "":
            curtext = post.text.encode('utf-8')
            tokens = self.tokenize(curtext)
            tokens = self.normalizeTokens(tokens)
            tokens = self.stripSpecialChars(tokens)
            tokens = self.filterInvalid(tokens)
            tokens = self.calculateTf(tokens)
            return tokens
        return []

    def getTfIdf(self, w, tf, idf, tokens):
        return (tf * idf) / len(tokens)

    def calculateTfIdf(self, tokens):
        return [ (w, self.getTfIdf(w, tf, idf, tokens) ) for w, tf, idf in tokens ]

    # maximum normalized tf
    def calculateTf(self, tokens):
        if len(tokens) == 0:
            return []

        seen = {}
        max_tf = 1.0

        for w in tokens:
            if not w in seen:
                seen[w] = 1.0
                if not w in self.idfCache:
                    self.idfCache[w] = 1.0
                else:
                    self.idfCache[w] = self.idfCache[w] + 1.0
            else:
                seen[w] = seen[w] + 1.0
            if seen[w] > max_tf:
                max_tf = seen[w]

        res = []
        for w in tokens:
            res.append( (w, seen[w] / max_tf) )
        return res

    def calculateIdf(self, tokens):
        return [(w, tf, self.getIdf(w)) for w, tf in tokens]

    def filterInvalid(self, tokens):
        vt = [w for w in tokens if self.isValidTerm(w)]
        if vt is None:
            vt = []
        return vt

    def tokenize(self, curtext):
        return [word for sent in nltk.sent_tokenize(curtext) for word in self.tokenizer.tokenize(sent)]

    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def is_stop_word(self, term):
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

    def isValidTerm(self, term):
        if len(term) < 2:
            return False
        for t in [".", ",", "-", "+", "%", "?", "!", "$", "&", "/", "\"", "'", "`", "`", "|", ":", ";", ")", "(", "[", "]", "{", "}"]:
            if t in term:
                return False
        if self.is_number(term):
            return False
        if self.is_stop_word(term):
            return False

        try:
            term = term.decode('ascii')
        except:
            return False

        if term.find('.') > -1: # or term.find('/') > -1 or term.find("?"): # url parts
            return False
        return True

    def normalizeTokens(self, tokens):
        return [w.lower() for w in tokens]

    def stripSpecialChars(self, tokens):
        return [w.strip("\r\n.,-+%?!$&/\\'`|:;)([]{}\t\" ") for w in tokens]

    def kpGraph(self, page):
        # initialization
        self.nextFreeIndex = 0
        self.tokenIndices = {}
        self.allTerms = []

        pageowner = page.owner
        pageposts = Post.objects.filter(page__exact=page)

        pageusers = User.objects.filter(id__in = pageposts.exclude(createuser__exact=pageowner).values('createuser').distinct() )
        pageusers_count = len(pageusers)
        print "Calculating vectors for %s users" % pageusers_count

        kp_term_method = KeyphraseMethod.objects.get(name='pos_sequence')

        userterms = {}

        curuseridx = 0
        for currentuser in pageusers:
            curuseridx = curuseridx + 1
            print "%s/%s" % (curuseridx, pageusers_count)
            (terms, ids) = self.getUserVector(page, currentuser, kp_term_method)
            if not terms is None:
                userterms[currentuser.id] = (terms, ids)

        print "Maximal index: %s" % self.nextFreeIndex

        uservectors = {}
        vectorlen = self.nextFreeIndex
        for currentuser in userterms.keys():
            terms, ids = userterms[currentuser]
            currentvector = [0.0] * vectorlen

            for i in range(len(ids)-1):
                currentvector[ids[i]] = 1.0

            uservectors[currentuser] = (np.array(currentvector), terms)
            #print ", ".join(map(str, currentvector))
            #print ", ".join(self.allTerms)

        userswithindex = uservectors.keys()
        usermatrix = np.zeros([len(userswithindex)+1, len(userswithindex)+1])

        u1idx = 0

        for u1 in userswithindex:
            u2idx = 0
            for u2 in userswithindex:
                u2idx = u2idx + 1
                if u1 == u2:
                    continue

                u1_vec = uservectors[u1][0]
                u2_vec = uservectors[u2][0]
                u1u2dot = np.dot(u1_vec, u2_vec)
                usermatrix[u1idx][u2idx] = u1u2dot

            u1idx = u1idx + 1
            print "%s/%s" % (u1idx, len(userswithindex))

        print "Creating graph"
        graph = nx.Graph()

        graph.add_nodes_from(pageusers)
        for i1 in range(usermatrix.shape[0]-1):
            max_edge = None
            max_edge_val = 0.0
            for i2 in range(usermatrix.shape[0]-1):
                if i1 == i2:
                    continue
                u1 = userswithindex[i1]
                u2 = userswithindex[i2]
                u1u2val = usermatrix[i1][i2]
                if u1u2val > max_edge_val:
                    max_edge = u2
                    max_edge_val = u1u2val

            if max_edge_val > 0.0 and not max_edge is None:
                self.add_edge(graph, u1, max_edge)

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)
        print "Nodes: %s Edges: %s" % ( len(graph.nodes()), len(graph.edges()) )
        self.removeSingletons(graph)
        print "Nodes: %s Edges: %s" % ( len(graph.nodes()), len(graph.edges()) )

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)

        for compidx in range(len(components)-1):
            component = components[compidx]
            taglist = []
            for user_id in component:
                ut = userterms[user_id][0]
                for t in ut:
                    if not t in taglist:
                        taglist.append(t)

            print "Component #%s Users: %s Tags (%s): \"%s\"" % (compidx, len(component), len(taglist), ",".join(taglist))




        return

    def getIndex(self, token):
        if not token in self.tokenIndices:
            self.allTerms.append(token)
            self.tokenIndices[token] = self.getNextIndex()
        return self.tokenIndices[token]

    def getUserVector(self, page, currentuser, kp_term_method):
        user_posts = Post.objects.filter(page__exact=page, createuser__exact=currentuser)
        user_post_parents = Post.objects.filter(id__in=user_posts.values('parent').distinct())

        user_kps = PostKeyphraseAssoc.objects.filter(post__in = user_posts, keyphrase__method__exact=kp_term_method)
        user_kp_count = len(user_kps)

        terms_all = []
        terms_split = []
        terms_n = user_kps.values('keyphrase__normalized').distinct()
        terms_t = user_kps.values('keyphrase__term').distinct()

        for term in terms_n:
            t = term['keyphrase__normalized']
            if not t in terms_all:
                terms_all.append(t)

        for term in terms_t:
            t = term['keyphrase__term']
            if not t in terms_all:
                terms_all.append(t)

        for term in terms_all:
            for term_part in term.split(" "):
                if not term_part in terms_split:
                   terms_split.append(term_part)

        terms_all = terms_split

        #if (len(terms_all) > 0):
        #    for thread_post in user_post_parents:
        #        terms_all.append("POST%s" % (thread_post.id))

        print "User: %s Posts: %s Keyphrases: %s" % ( currentuser, len(user_posts), user_kp_count )
        print "Terms: %s" % ", ".join(terms_all)

        if user_kp_count == 0:
            return (None, None)

        res_terms = []
        res_ids = []
        for term in terms_all:
            term_idx = self.getIndex(term)
            res_terms.append(term)
            res_ids.append(term_idx)

        return (res_terms, res_ids)

    def add_edge(self, graph, obj_from, obj_to, add_weight=1.0):
        if not graph.has_edge(obj_from, obj_to):
            graph.add_edge(obj_from, obj_to, weight=add_weight)
        else:
            graph[obj_from][obj_to]['weight'] = graph[obj_from][obj_to]['weight'] + add_weight

    def addPostUser(self, graph, post, added_users):
        if not post.createuser in graph:
            graph.add_node(post.createuser)
            added_users.append(post.createuser)
        # edge: post -> createuser
        self.add_edge(graph, post, post.createuser)

    def addPostParent(self, graph, post):
        if not post.parent is None:
            if not post.parent in graph:
                graph.add_node(post.parent)
                self.add_edge(graph, post, post.parent)

    def addPostKeyPhrases(self, graph, post):
        # keyphrases in this post
        for pk in PostKeyphraseAssoc.objects.filter(post__exact=post):
            graph.add_node(pk.keyphrase)
            self.add_edge(graph, post, pk.keyphrase)

    def addUserMetaCategory(self, graph, user):
        metaentries = UserMeta.objects.filter(user__exact=user)
        for metaentry in metaentries:
            if metaentry is None:
                continue
            if metaentry.fb_category is None or metaentry.fb_category == '':
                continue
            nodeval = u'CAT_' + unicode(metaentry.fb_category)
            graph.add_node(nodeval)
            self.add_edge(graph, user, nodeval)

    def addUserMeta(self, graph, user):
        metaentries = UserMeta.objects.filter(user__exact=user)
        for metaentry in metaentries:
            if metaentry is None:
                continue
            nodeval = unicode(metaentry)
            graph.add_node(nodeval)
            self.add_edge(graph, user, nodeval)

    def removeNonConnectedUsers(self, graph, dist_threshold):
        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)

        print "Removing non-connected user nodes"
        remove_nodes = []
        for component in components:
            usernodes = []
            userdists = {}
            for node in component:
                if type(node) == User:
                    usernodes.append(node)
            u1idx = 0
            ulen = len(usernodes)
            for u1 in usernodes:
                u1idx = u1idx + 1
                print "%s/%s" % (u1idx, ulen)
                if not u1.id in userdists:
                    userdists[u1.id] = 1000
                for u2 in usernodes:
                    if u1 == u2:
                        continue
                    pathres = nx.dijkstra_path_length(graph,u1,u2)
                    if pathres < userdists[u1.id]:
                        userdists[pathres] = pathres
                    if userdists[u1.id] < dist_threshold:
                        break # condition satisfied
            for user in usernodes:
                if userdists[user.id] > dist_threshold: # shortest path to another user is > 5 -> remove
                    print "Removing user %s. Dist value: %s" % (user.id, userdists[user.id])
                    remove_nodes.append(user)
        print "Removing %s user nodes" % len(remove_nodes)
        graph.remove_nodes_from(remove_nodes)
        del remove_nodes

    def removeSingletons(self, graph):
        print "Removing singletons"
        singleton_nodes = [ n for n,d in graph.degree_iter() if d==0 ]
        graph.remove_nodes_from(singleton_nodes)
        del singleton_nodes


    def buildGraph(self, page):
        print "Building graph"
        pageowner = page.owner
        pageposts = Post.objects.filter(page__exact=page)

        graph = nx.Graph()

        #pageposts = pageposts[500:700] ##########################################

        print "nodes: posts"
        graph.add_nodes_from(pageposts)

        print "edges: user -> post"
        added_users = []

        for post in pageposts:
            # post.createuser
            self.addPostUser(graph, post, added_users)

            # post->parent post
            self.addPostParent(graph, post)

            # post->postkeyphraseassoc->keyphrase
            self.addPostKeyPhrases(graph, post)

            # post.createuser->usermeta
            #self.addUserMeta(graph, post.createuser)
            #self.addUserMetaCategory(graph, post.createuser)

        print "Graph nodes: %s" % len(graph.nodes())
        print "Graph edges: %s" % len(graph.edges())

        print "Removing page owner"
        graph.remove_node(pageowner)

        print "Graph nodes: %s" % len(graph.nodes())
        print "Graph edges: %s" % len(graph.edges())


        self.removeSingletons(graph)

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)

        print "Removing components with only 0/1 user nodes"
        remove_components = []
        for component in components:
            usercount = 0
            for node in component:
                if type(node) == User:
                    usercount = usercount + 1
            if usercount <= 1:
                remove_components.append(component)
            else:
                print "Found %s user nodes" % usercount
        print "Removing %s components" % len(remove_components)
        for component in remove_components:
            graph.remove_nodes_from(component)
        del remove_components

        components = nx.connected_components(graph)
        print "Number of connected components: %s" % len(components)

        print "Edges: %s" % len(graph.edges())
        remove_edges = []
        weight_threshold = 2.0
        for node_a, node_b, attr in sorted(graph.edges(data = True), key = lambda (a, b, attr): attr['weight']):
            if type(node_a) == Post or type(node_b) == Post: # exclude post connections
                continue
            if 'weight' in attr and attr['weight'] > weight_threshold:
                break
            remove_edges.append((node_a, node_b))
            #print('{a} {b} {w}'.format(a = node_a, b = node_b, w = attr['weight']))
        for node_a, node_b in remove_edges:
            graph.remove_edge(node_a, node_b)
        print "Edges: %s" % len(graph.edges())

        self.removeSingletons(graph)

        print "Graph dotfile"
        nx.write_dot(graph, '/home/double/graph_viz.dot')


        tmp = []
        for user in added_users:
            if user in graph:
                tmp.append(user)
        added_users = tmp
        print "Unique users in graph: %s" % len(added_users)

        usergraph = nx.Graph()
        usergraph.add_nodes_from(added_users)
        for user_a, user_b in combinations(added_users, 2):
            try:
                userpath = nx.shortest_path_length(graph, user_a, user_b, weight='weight')
                usergraph.add_edge(user_a, user_b, weight=userpath)
                print user_a, user_b, userpath
            except nx.NetworkXNoPath, e:
                #print e
                continue

        self.removeSingletons(usergraph)

        #print "Drawing graph"
        plt.ioff()

        #nx.draw(graph, node_size=10, font_size=8)
        #plt.savefig('/home/double/graph.png', dpi=1000)

        print "UserGraph nodes: %s" % len(usergraph.nodes())
        print "UserGraph edges: %s" % len(usergraph.edges())


        return

