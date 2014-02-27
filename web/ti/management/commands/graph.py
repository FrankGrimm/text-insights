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

from itertools import combinations

# no interactive display
import matplotlib as mpl
mpl.use('Agg')

import matplotlib.pyplot as plt
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
            raise CommandError('Invalid arguments. Expected: <page_id> <action>, where action might be: extract, tfidf, webidf')

        page_id = args[0]

        self._log.info('GraphCommand initializing.')

        self._log.info('Page-Id: %s' % page_id)
        page = Page.objects.get(id=page_id)

        self.buildGraph(page)

        self._log.info("All done for now.")

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

        print "UserGraph Drawing graphviz"
        A = nx.to_agraph(usergraph)
        A.graph_attr.update(fontsize=8)
        A.layout()
        A.draw('/home/double/usergraph_viz.png')
        print "UserGraph dotfile"
        nx.write_dot(usergraph, '/home/double/usergraph_viz.dot')


        return
