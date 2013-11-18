# -*- coding: utf-8 -*-

# views

from django.conf import settings
from django.http import HttpResponse
from django.template import Context, loader
from django.shortcuts import render, redirect
import collections
import datetime
import os
import ti
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache

from django.utils.http import urlquote
from django.contrib.auth import authenticate, login, logout
from itertools import chain
from django.db.models import Max, Min, Count, F, Q
from ti.models import *
import urllib
import json
from random import random
import operator

@login_required
def home(request):
    ctx = {'pages': Page.objects.all}
    return render(request, 'pagelist', ctx, content_type="text/html")

@login_required
def user_info(request):
    return ""

@login_required
def page_info(request, page_id=None, single_post_id=None):
    if page_id is None:
        raise Exception("Invalid page id")
    ctx = {}

    # add page meta-information
    page = ctx['page'] = Page.objects.get(id=page_id)

    if single_post_id is None:
        # add general information on posts
        pdt_from = None
        pdt_to = None

        ctx['searchterm'] = ''
        if 'q' in request.GET:
            ctx['searchterm'] = urllib.unquote(request.GET['q'].strip())

        ctx['dt_from'] = ''
        ctx['dt_to'] = ''
        if 'from' in request.GET and 'to' in request.GET:
            ctx['dt_from'] = pdt_from
            ctx['dt_to'] = pdt_to
            pdt_from = request.GET['from']
            pdt_to = request.GET['to']

        if pdt_from is not None:
            minmax = Post.objects.filter(page__exact=page, createtime__gte=pdt_from, createtime__lte=pdt_to).aggregate(dt_first=Min('createtime'), dt_last=Max('createtime'))
            ctx['postcount'] = Post.objects.filter(page__exact=page, createtime__gte=pdt_from, createtime__lte=pdt_to).exclude(posttype__exact='comment').count()
            ctx['commentcount'] = Post.objects.filter(page__exact=page, posttype__exact='comment', createtime__gte=pdt_from, createtime__lte=pdt_to).count()
        else:
            minmax = Post.objects.filter(page__exact=page).aggregate(dt_first=Min('createtime'), dt_last=Max('createtime'))
            ctx['postcount'] = Post.objects.filter(page__exact=page).exclude(posttype__exact='comment').count()
            ctx['commentcount'] = Post.objects.filter(page__exact=page, posttype__exact='comment').count()

        ctx['firstpost_dt'], ctx['lastpost_dt'] = minmax['dt_first'], minmax['dt_last']

        page_info_posttypecounts(page, ctx, dt_from = pdt_from, dt_to = pdt_to)
        page_info_posts(page, ctx, dt_from = pdt_from, dt_to = pdt_to, q=ctx['searchterm'])
        ctx['singlepost'] = False

        return render(request, 'pageoverview', ctx, content_type="text/html")
    else:
        ctx['singlepost'] = True
        page_info_posts(page, ctx, single_post_id)
        ctx['post_id'] = single_post_id
        return render(request, 'singlepost', ctx, content_type="text/html")

def getKeyphrasePosts(page, q):
    matching_posts = PostKeyphraseAssoc.objects.filter(post__page__exact=page, keyphrase__term__exact=q).values('post__id')
    postlist = Post.objects.filter(Q(id__in=matching_posts) | Q(parent__in=matching_posts))
    return matching_posts

def getCommenters(page, q):
    posts = Post.objects.filter(id__in=PostKeyphraseAssoc.objects.filter(post__page__exact=page, keyphrase__term__exact=q).values('post__id')).prefetch_related('createuser').all()
    res = {}
    for post in posts:
        al = post.createuser.alias
        if 'page-' in al:
            continue
        if al in res:
            res[al] = res[al] + 1.0
        else:
            res[al] = 1.0 + random()*0.1

    commenter_data = []
    for alias in res:
        nres = {'text': alias, 'weight': res[alias]}
        commenter_data.append(nres)
    return [x for x in list(reversed(sorted(commenter_data, key=lambda cur: cur['weight'])))[:10]]

def page_info_posts(page, ctx, single_post_id=None, dt_from=None, dt_to=None, q=None):
    if q is not None and q == '':
        q = None

    # all posts for this page
    if single_post_id is None:
        if q is not None:
            keyword_postlist = getKeyphrasePosts(page, q)

            commenter_info = getCommenters(page, q)
            #commenter_info = [x for x in list(reversed( sorted(commenter_info, key=commenter_info.get) ))[:10]]
            ctx['commentercounts'] = json.dumps(commenter_info)


            if dt_from is not None and dt_to is not None:
              # time range restriction
                posts = Post.objects.filter(page__exact=page, id__in=keyword_postlist, createtime__gte=dt_from, createtime__lte=dt_to).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()
            else:
                # default to all posts
                posts = Post.objects.filter(page__exact=page, id__in=keyword_postlist).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()

        else:
            if dt_from is not None and dt_to is not None:
                # time range restriction
                posts = Post.objects.filter(page__exact=page, createtime__gte=dt_from, createtime__lte=dt_to).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()
            else:
                # default to all posts
                posts = Post.objects.filter(page__exact=page).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()

    else:
        # single post
        posts = Post.objects.filter(page__exact=page, id__exact=single_post_id).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()

    ctx['totalposts'] = len(posts)

    # add monthly statistics
    months = {}
    comments = {}

    prev_month = None
    for post in posts:
        post.monthchange = prev_month is None or prev_month != post.createtime.month
        curmonth = post.createtime.month
        if curmonth < 10:
            curmonth = "0%s" % curmonth
        monthid = "%s/%s" % (curmonth, post.createtime.year)
        if not monthid in months:
            months[monthid] = {'id': monthid, 'posts': [], 'comments': 0, 'month': post.createtime.month, 'year': post.createtime.year, 'commenters': [], 'likes': 0}
        months[monthid]['posts'].append(post)

        comments[post.id] = Post.objects.filter(page__exact=page, posttype__exact='comment', parent=post).prefetch_related('createuser').all()

        months[monthid]['comments'] = months[monthid]['comments'] + len(comments[post.id])
        months[monthid]['likes'] = months[monthid]['likes'] + post.likes

        prev_month = post.createtime.month

    for monthid in months:
        for post in months[monthid]['posts']:
            for comment in comments[post.id]:
                if not comment.createuser in months[monthid]['commenters']:
                    months[monthid]['commenters'].append(comment.createuser)

    posts_by_month = []
    # sort chronologically for view model
    for mid in sorted(months.iterkeys()):
        posts_by_month.append(months[mid])

    # add scroll helper references
    #for idx, key in enumerate(posts_by_month):
    #    if idx == 0:
    #        obj['l_next'] = "%s_%s" (posts_by_month[idx+1]['month'], posts_by_month[idx+1]['year'])
    #    elif idx == len(posts-by_month)-1:
    #        obj['l_prev'] = "%s_%s" (posts_by_month[idx-1]['month'], posts_by_month[idx-1]['year'])
    #    else:
    #       obj['l_prev'] = "%s_%s" (posts_by_month[idx-1]['month'], posts_by_month[idx-1]['year'])
    #        obj['l_next'] = "%s_%s" (posts_by_month[idx+1]['month'], posts_by_month[idx+1]['year'])

    ctx['comments'] = comments
    ctx['posts_by_month'] = posts_by_month
    ctx['posts'] = posts

def page_info_posttypecounts(page, ctx, dt_from = None, dt_to = None):
    # add counts of different post types
    if dt_from is not None:
        typecounts = Post.objects.filter(page__exact=page, createtime__gte=dt_from, createtime__lte=dt_to).values('posttype').annotate(Count('posttype'))
    else:
        typecounts = Post.objects.filter(page__exact=page).values('posttype').annotate(Count('posttype'))

    posttypes = {}
    for typecount in typecounts:
        posttypes[typecount['posttype']] = typecount['posttype__count']
    ctx['posttypes'] = posttypes
    if 'comment' in posttypes:
        del posttypes['comment']
    posttypes_json = {}
    for ptype in posttypes:
        posttypes_json["%s (%s)" % (ptype, posttypes[ptype])] = posttypes[ptype]
    ctx['posttypes_json'] = json.dumps(posttypes_json)


def login_view(request):
    if request.method == 'GET' or request.user.is_authenticated():
        return render(request, 'login', {}, content_type="text/html")
    else:
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('home')
            else:
                # error
                return redirect('home')
        else:
            # Return an 'invalid login' error message.
            return redirect('home')

def logout_view(request):
    logout(request)
    return redirect('home')

def base_css(request):
    return render(request, 'base.css', {}, content_type="text/css")

def base_js(request):
    return render(request, 'base.js', {}, content_type="text/javascript")

@login_required
def template(request):
    ctx = {'name': 'yourname','now':datetime.datetime.now()}
    return render(request, 'home', ctx, content_type="text/html")

stop_words = None

def read_stop_words():
    res = {}
    for word in open(os.path.join(settings.STATIC_ROOT, 'stop_words'), 'rt').read().split('\r\n'):
        if not word is None and word != '' and not word in res:
            res[word] = True
    return res

@login_required
@never_cache
def json_serve(request):

    # mandatory parameters: page, tags (type), level
    page_id = request.GET['page']
    which_tags = request.GET['tags']

    q = None
    if 'q' in request.GET:
        q = request.GET['q'].strip()
        if q == '':
            q = None

    currentpage = Page.objects.get(id=page_id)

    response_data = {
        'page': currentpage.id,
    }

    targetposts = None
    # switch which data range to query
    if 'post' in request.GET: # single post
        parentpost = Post.objects.get(page=currentpage, id=request.GET['post'])
        targetposts = []
        targetposts.append(parentpost)
        for comment in Post.objects.filter(page=currentpage, parent=parentpost):
            targetposts.append(comment)
        response_data['target'] = 'single_post'
    else:
        month = request.GET['month']
        year = request.GET['year']
        response_data['target'] = "M=%s;Y=%s" % (month, year)
        post_filters = {'page': currentpage}

        if year != '-1':
            post_filters['createtime__year'] = year
        if month != '-1':
            post_filters['createtime__month'] = month

        if 'from' in request.GET and 'to' in request.GET and request.GET['from'] != '' and request.GET['to'] != '' and request.GET['from'] != 'None':
            post_filters['createtime__gte'] = request.GET['from']
            post_filters['createtime__lte'] = request.GET['to']

        if q is not None:
            keyword_postlist = getKeyphrasePosts(currentpage, q)
            post_filters['id__in'] = keyword_postlist

        targetposts = Post.objects.filter(**post_filters)

    # load all comments to these posts
    targetposts = list(chain(targetposts, Post.objects.filter(parent__in=targetposts)))
    # TODO eval which_tags

    get_tags(currentpage, targetposts, response_data, excludeKeyphrase=q)#, lengthfactor = 1.2, idf_method='webidf_wiki')
    resp = HttpResponse(json.dumps(response_data), content_type="application/json")
    return resp

# targetcolumn = {'normalized', 'term'}
def get_tags(page, posts, jsonout, target_column = 'normalized', idf_method='idf-pos', lengthfactor=1.0, excludeKeyphrase=None):
    global stop_words
    if stop_words is None:
        stop_words = read_stop_words()


    # gather terms
    term_results = {}
    #for ngram_level in range(1, 3):
    #    kp_term_method = KeyphraseMethod.objects.get(name='ngram-%s' % ngram_level)
    #    kp_method_idf = KeyphraseMethod.objects.get(name="idf-%s" % ngram_level)
    #    term_results[kp_term_method.name] = get_tags_by_method(page, posts, kp_term_method, kp_method_idf, target_column)

    kp_term_method = KeyphraseMethod.objects.get(name='pos_sequence')
    kp_method_idf = KeyphraseMethod.objects.get(name=idf_method)
    term_results[kp_term_method.name] = get_tags_by_method(page, posts, kp_term_method, kp_method_idf, target_column, lengthfactor, exclude=excludeKeyphrase)

    totaltags = 0
    for method_name in term_results:
        res = term_results[method_name]
        jsonout['tags_%s' % method_name] = len(res)
        N = 50
        # only use the top 50 tags (max) per method
        term_results[method_name] = [x for x in list(reversed(sorted(res, key=lambda cur: cur['weight'])))[:N] if x['idf'] != 'NA']
        # get min/max
        minval = min(term_results[method_name], key=(lambda item: item['weight']))['weight']
        maxval = max(term_results[method_name], key=(lambda item: item['weight']))['weight']
        # normalize weights to [0:100]
        for item in term_results[method_name]:
           prev_w = item['weight']
           if (maxval - minval) > 0.0: # TODO check for single postings
               item['weight'] = (prev_w - minval) * 100.0 / (maxval - minval)

           # weight down unigrams
           if method_name == 'ngram-1':
               item['weight'] = item['weight'] * 0.9

    jsonout['postcount'] = len(posts)
    jsonout['tagsshown'] = len(res)

    jsonout['tags'] = []
    added_terms = []
    for method_name in term_results:
        for termdata in term_results[method_name]:
            # prevent duplicates from multiple methods and 1-char terms
            if len(termdata['text']) > 1 and not termdata['text'] in added_terms:
                added_terms.append(termdata['text'])
                termdata['link'] = '/page/%s?q=%s' % ( page.id, urlquote(termdata['text']) )
                jsonout['tags'].append(termdata)

    # sort resulting tag-set by weight
    N_total = 50
    jsonout['tags'] = [ x for x in list(reversed(sorted(jsonout['tags'], key=lambda cur: cur['weight'])))[:N_total] ]

    return


def get_tags_by_method(page, posts, kp_term_method, kp_method_idf, target_column, lengthfactor, exclude=None):

    # gather TF values (raw)
    if exclude is None:
        tfs = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = page, postkeyphraseassoc__post__in=posts, method = kp_term_method).values(target_column).distinct().annotate(dcount=Count(target_column))
    else:
        if target_column == 'normalized':
            tfs = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = page, postkeyphraseassoc__post__in=posts, method = kp_term_method).exclude(normalized__exact=exclude).values(target_column).distinct().annotate(dcount=Count(target_column))
        else:
            tfs = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = page, postkeyphraseassoc__post__in=posts, method = kp_term_method).exclude(term__exact=exclude).values(target_column).distinct().annotate(dcount=Count(target_column))
    res = []

    termlist = []
    for tf in tfs:
        has_stop_word = False
        for cur_part in tf[target_column].split(' '):
            if cur_part in stop_words:
                has_stop_word = True
                break

        if not has_stop_word:
            termlist.append(tf[target_column])

    # retrieve IDF values
    if target_column == 'normalized':
        idfs = Keyphrase.objects.filter(normalized__in=termlist, method = kp_method_idf).distinct()
    else:
        idfs = Keyphrase.objects.filter(term__in=termlist, method = kp_method_idf).distinct()

    idfmap = {}
    for idf in idfs:
        idfmap[idf.term] = float(idf.val) ** 2

    if target_column == 'normalized':
        # lookup data for most common form of some terms, per page
        real_terms = Keyphrase.objects.filter(postkeyphraseassoc__post__page__exact = page, method = kp_term_method, normalized__in=termlist).values('term', 'normalized').distinct().annotate(dcount=Count('term'))
        normalized_terms = {}
        for cur_term in real_terms:
            if not cur_term['normalized'] in normalized_terms:
                normalized_terms[ cur_term['normalized'] ] = {}
            if not cur_term['term'] in normalized_terms[ cur_term['normalized'] ]:
                normalized_terms[ cur_term['normalized'] ][ cur_term['term'] ] = cur_term['dcount']
            else:
                normalized_terms[ cur_term['normalized'] ][ cur_term['term'] ] = normalized_terms[ cur_term['normalized'] ][ cur_term['term'] ] + cur_term['dcount']

    for tf in tfs:
        curterm = unicode(tf[target_column])
        tf['tf'] = float(tf['dcount'])
        if curterm in idfmap:
            tf['idf'] = idfmap[curterm]
        else:
            tf['idf'] = 'NA'

    for tf in tfs:
        weight = 0.0
        if tf['idf'] != 'NA':
            if tf['idf'] == 0.0:
                weight = 'NA'
            else:
                if lengthfactor == 1.0:
                    weight = tf['tf'] * tf['idf']
                else:
                    weight = len(unicode(tf[target_column]).split(" ")) ** lengthfactor * tf['tf'] * tf['idf']

        if weight == 'NA' or tf[target_column] == exclude:
            continue

        nres = {'text': tf[target_column], 'weight': weight, 'tf': tf['dcount'], 'idf': tf['idf'], 'method': kp_term_method.name }
        if target_column == 'normalized':
            nres['text_normalized'] = nres['text']
            if nres['text_normalized'] in normalized_terms:
                max_count = 0
                max_item = ""
                for cur_term in normalized_terms[ nres['text_normalized'] ]:
                    cur_count = normalized_terms[ nres['text_normalized'] ][cur_term]
                    if cur_count > max_count:
                        max_count = cur_count
                        max_item = cur_term
                if max_item != "":
                    nres['found_unnormalized'] = max_count
                    nres['text'] = max_item

        res.append(nres)

    return res

def overview_view(request):
    ctx = {}
    ctx['pages'] = Page.objects.all()
    return render(request, 'overview', ctx, content_type="text/html")


