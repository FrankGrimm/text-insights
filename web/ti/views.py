# -*- coding: utf-8 -*-

# views

from django.conf import settings
from django.http import HttpResponse
from django.template import Context, loader
from django.shortcuts import render, redirect
import collections
import datetime
from dateutil.relativedelta import relativedelta
import os
import ti
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache, cache_page

import pycountry

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
@never_cache
def page_cluster(request, page_id=None):
    if page_id is None:
        raise Exception("Invalid page id")

    ctx = {}
    # page object
    page = ctx['page'] = Page.objects.get(id=page_id)

    # all clusters for this page
    pageclusters = UserCluster.objects.filter(page__exact=page)
    pagecluster_terms = {}
    pagecluster_users = {}

    ctx['clusterterm_json'] = {}
    for currentcluster in pageclusters:
        pagecluster_users[currentcluster.id] = UserClusterAssoc.objects.filter(cluster__exact = currentcluster)
        pagecluster_terms[currentcluster.id] = list( reversed(sorted(UserClusterTerm.objects.filter(cluster__exact = currentcluster), key=lambda k: k.termweight)))[:100]
        ctx['clusterterm_json'][currentcluster.id] = []
        weight_bounds = [None, None] # min, max
        for termassoc in pagecluster_terms[currentcluster.id]:
            termobj = {}
            termobj['link'] = "#"
            termobj['text'] = termassoc.clusterterm
            termobj['weight'] = termassoc.termweight
            if weight_bounds[0] is None:
                #initialize
                weight_bounds[0] = termassoc.termweight
                weight_bounds[1] = termassoc.termweight
            else:
                if termassoc.termweight < weight_bounds[0]:
                    weight_bounds[0] = termassoc.termweight
                if termassoc.termweight > weight_bounds[1]:
                    weight_bounds[1] = termassoc.termweight

            ctx['clusterterm_json'][currentcluster.id].append(termobj)


        for termobj in ctx['clusterterm_json'][currentcluster.id]:
            if (weight_bounds[1] - weight_bounds[0]) > 0.0:
                termobj['weight'] = (termobj['weight'] - weight_bounds[0]) / (weight_bounds[1] - weight_bounds[0]) * 100.0
            termobj['weight'] = int(termobj['weight'])
        ctx['clusterterm_json'][currentcluster.id] = json.dumps(ctx['clusterterm_json'][currentcluster.id])

    ctx['clusterusers'] = pagecluster_users
    ctx['clusterterms'] = pagecluster_terms


    ctx['clustercount'] = len(pageclusters)
    ctx['clusters'] = list( reversed(sorted(pageclusters, key=lambda k: len(pagecluster_users[ k.id ]) )) )
    #ctx['clusters'] = [for c in ctx['clusters'] if len(pagecluster_users[c.id]) > 1]
    return render(request, 'pagecluster', ctx, content_type="text/html")

@login_required
@cache_page(60 * 15)
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
            pdt_from = request.GET['from']
            pdt_to = request.GET['to']
            ctx['dt_from'] = pdt_from
            ctx['dt_to'] = pdt_to

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
    matching_posts = PostKeyphraseAssoc.objects.filter(post__page__exact=page).filter(Q(keyphrase__term__exact=q) | Q(keyphrase__normalized__exact=q)).values('post__id')
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

    ctx['commentercounts'] = "{}"
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
@cache_page(60*30)
#@never_cache
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
    pageowner = currentpage.owner

    response_data = {
        'page': currentpage.id,
    }

    targetposts = None
    commenterposts = None

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

        # search filter
        if q is not None:
            keyword_postlist = getKeyphrasePosts(currentpage, q)
            post_filters['id__in'] = keyword_postlist

        isSpecificMonth = False
        isDateRange = False
        if year != '-1':
            post_filters['createtime__year'] = year
        if month != '-1':
            post_filters['createtime__month'] = month
            isSpecificMonth = True

        if 'from' in request.GET and 'to' in request.GET and request.GET['from'] != '' and request.GET['to'] != '' and request.GET['from'] != 'None':
            post_filters['createtime__gte'] = request.GET['from']
            post_filters['createtime__lte'] = request.GET['to']
            isDateRange = True

        targetposts = Post.objects.filter(**post_filters)

    # load all comments to these posts
    response_data['postcount_targets'] = len(targetposts)
    commenterposts = list(chain(targetposts, Post.objects.filter(parent__in=targetposts)))
    pageonlyposts = list(chain( targetposts.filter(createuser__exact=pageowner), Post.objects.filter(parent__in=targetposts).filter(createuser__exact=pageowner)))
    targetposts = list(chain( targetposts.exclude(createuser__exact=pageowner), Post.objects.filter(parent__in=targetposts).exclude(createuser__exact=pageowner) ))
    response_data['postcount_nopage'] = len(targetposts)
    response_data['postcount_comm'] = len(commenterposts)

    term_lengthfactor = 1.005

    get_tags(currentpage, targetposts, response_data, excludeKeyphrase=q, lengthfactor=term_lengthfactor, tagcategories=True)#, lengthfactor = 1.2, idf_method='webidf_wiki')

    # commenter info
    response_data['genderinfo'] = {}
    response_data['localeinfo'] = {}
    response_data['lengthfactor'] = term_lengthfactor
    get_commenter_info(currentpage, targetposts, response_data['genderinfo'], response_data['localeinfo'])
    get_locale_metadata(response_data['localeinfo'])

    if commenterposts is not None:
        commenter_data = {}
        get_tags(currentpage, commenterposts, commenter_data, excludeKeyphrase=q, lengthfactor = term_lengthfactor, tagcategories=True)
        #return HttpResponse("%s %s" % (len(commenterposts), commenter_tags), content_type = 'text/plain')
        if 'tags' in commenter_data and 'tags' in response_data:
            page_tags = {}
            commenter_tags = {}
            for cur in response_data['tags']:
                page_tags[cur['text']] = cur
                page_tags[cur['text']]['isnew'] = True
            for cur in commenter_data['tags']:
                commenter_tags[cur['text']] = cur
                commenter_tags[cur['text']]['isnew'] = False

            tag_result = []
            response_data['tags_commenters'] = len(response_data['tags'])
            response_data['tags_all'] = len(commenter_data['tags'])

            for cur_text in page_tags:
                cur = page_tags[cur_text]
                tag_result.append(cur)
            for cur_text in commenter_tags:
                cur = commenter_tags[cur_text]
                if not cur_text in page_tags:
                    tag_result.append(cur)

            response_data['tags'] = tag_result

    if pageonlyposts is not None:
        pageonly_data = {}
        get_tags(currentpage, pageonlyposts, pageonly_data, excludeKeyphrase=q, lengthfactor=term_lengthfactor, tagcategories=True)
        #return HttpResponse("%s %s" % (len(pageonlyposts), pageonly_tags), content_type = 'text/plain')
        if 'tags' in pageonly_data and 'tags' in response_data:
            page_tags = {}
            pageonly_tags = {}
            for cur in response_data['tags']:
                page_tags[cur['text']] = cur
                page_tags[cur['text']]['ispageonly'] = True
            for cur in pageonly_data['tags']:
                pageonly_tags[cur['text']] = cur
                pageonly_tags[cur['text']]['ispageonly'] = False

            tag_result = []
            response_data['tags_pageonly'] = len(pageonly_data['tags'])

            for cur_text in page_tags:
                cur = page_tags[cur_text]
                tag_result.append(cur)
            for cur_text in pageonly_tags:
                cur = pageonly_tags[cur_text]
                if not cur_text in page_tags:
                    tag_result.append(cur)

            response_data['tags'] = tag_result

    response_data['tags_prefilter'] = len(response_data['tags'])
    if q is None:
        alltags = []
        allweights = []
        removetags = []
        for cur in response_data['tags']:
            if not cur['text'] in alltags:
                alltags.append(cur['text'])
                allweights.append(cur['weight'])

        for idx1 in range(len(alltags)):
            for idx2 in range(len(alltags)):
                if idx1 == idx2:
                    continue
                t1 = alltags[idx1]
                t2 = alltags[idx2]
                if t2 in t1:
                    if allweights[idx1] < allweights[idx2]:
                        removetags.append(t1)
                    else:
                        removetags.append(t2)

        tagdata = response_data['tags']
        response_data['tags'] = []
        for cur in tagdata:
            if not cur['text'] in removetags:
                response_data['tags'].append(cur)

        response_data['tags_postfilter'] = len(response_data['tags'])
        response_data['tags_removed'] = removetags


    resp = HttpResponse(json.dumps(response_data), content_type="application/json")
    return resp

def get_locale_metadata(localeinfo):
    clonelocale = localeinfo.copy()
    for countrycode in clonelocale:
        res = {'ccode': countrycode, 'count': clonelocale[countrycode]}
        if countrycode != 'N/A':
            res['cname'] = pycountry.countries.get(alpha2=countrycode).name
            cinfo = CountryLocales.objects.filter(ccode=countrycode)
            if cinfo is not None and len(cinfo) > 0:
                res['lati'] = cinfo[0].lati
                res['longi'] = cinfo[0].longi
        localeinfo[countrycode] = res

def get_commenter_info(cpage, postlist, genderinfo, localeinfo):
    # TODO filter unique users
    for cpost in postlist:
        user_gender = cpost.createuser.gender
        user_locale = cpost.createuser.locale
        if user_locale != '':
            try:
                #user_locale = pycountry.countries.get(alpha2=user_locale[-2:]).name
                user_locale = user_locale[-2:]
            except Exception, e:
                user_locale = 'N/A'
        else:
            user_locale = 'N/A'

        if not user_gender in genderinfo:
            genderinfo[user_gender] = 1
        else:
            genderinfo[user_gender] = genderinfo[user_gender] + 1
        if not user_locale in localeinfo:
            localeinfo[user_locale] = 1
        else:
            localeinfo[user_locale] = localeinfo[user_locale] + 1
    if 'unknown' in genderinfo:
        del genderinfo['unknown']

def mark_new_tags(existing_tags, current):
    for cur in current:
        if cur['text'] in existing_tags:
            cur['isnew'] = False
        else:
            cur['isnew'] = True

# targetcolumn = {'normalized', 'term'}
def get_tags(page, posts, jsonout, target_column = 'normalized', idf_method='idf-pos', lengthfactor=1.0, excludeKeyphrase=None, allTags=None, tagcategories=False):
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
        N = 100
        # only use the top 50 tags (max) per method

        term_results[method_name] = [x for x in list(reversed(sorted(res, key=lambda cur: cur['weight'])))[:N] ] #if x['idf'] != 'NA']
        for cur in term_results[method_name]:
            if cur['idf'] == 'NA':
                cur['idf'] = 1.0
                cur['idfna'] = True
        jsonout['tags_%s_filtered' % method_name] = len(term_results[method_name])

        # get min/max
        try:
            minval = min(term_results[method_name], key=(lambda item: item['weight']))['weight']
            maxval = max(term_results[method_name], key=(lambda item: item['weight']))['weight']
        except:
            minval = 0.0
            maxval = 1.0

        if maxval == 0.0:
            maxval = 1.0
        # normalize weights to [0:100]
        for item in term_results[method_name]:
           if allTags is not None:
                allTags[item['text']] = True
           prev_w = item['weight']
           if (maxval - minval) > 0.0: # TODO check for single postings
               item['weight'] = (prev_w - minval) * 100.0 / (maxval - minval)

           # weight down unigrams
           if method_name == 'ngram-1':
               item['weight'] = item['weight'] * 0.9

        if not tagcategories:
            continue
        # categorize tag sources (pageonly, commenteronly, both)
        for item in term_results[method_name]:
            process_tags(item, kp_term_method, page.owner, posts, target_column)


    jsonout['postcount'] = len(posts)
    jsonout['tagsfound'] = len(res)

    jsonout['tags'] = []
    jsonout['tags_methods'] = []
    added_terms = []
    for method_name in term_results:
        jsonout['tags_methods'].append([method_name, len(term_results[method_name])])
        for termdata in term_results[method_name]:
            # prevent duplicates from multiple methods and 1-char terms
            if len(termdata['text']) > 1 and not termdata['text'] in added_terms and termdata['tf'] > 1:
                added_terms.append(termdata['text'])
                termdata['link'] = '/page/%s?q=%s' % ( page.id, urlquote(termdata['text']) )
                jsonout['tags'].append(termdata)
    # sort resulting tag-set by weight
    N_total = 50
    jsonout['tags'] = [ x for x in list(reversed(sorted(jsonout['tags'], key=lambda cur: cur['weight'])))[:N_total] ]

    return

def process_tags(item, kp_term_method, page_owner, posts, target_column):
    if not 'kp_count_page' in item:
        assocs = PostKeyphraseAssoc.objects.filter(keyphrase__method__exact = kp_term_method)
        assocs = assocs.filter( Q(keyphrase__normalized__exact = item['text']) | Q(keyphrase__term__exact = item['text']) )

        item['kp_count_all'] = len( Post.objects.filter(id__in=assocs.values('post__id')).distinct() )
        item['kp_count_page'] = len( Post.objects.filter(id__in=assocs.filter(post__createuser__exact = page_owner).values('post__id')).distinct() )
        item['kp_count_nonpage'] = len( Post.objects.filter(id__in=assocs.exclude(post__createuser__exact = page_owner).values('post__id')).distinct() )

        item['kp_ispageonly'] = False
        item['kp_isboth'] = False
        item['kp_iscommenteronly'] = False
        if item['kp_count_all'] > 0 and item['kp_count_page'] > 0 and item['kp_count_nonpage'] == 0:
            item['kp_ispageonly'] = True
        if item['kp_count_all'] > 0 and item['kp_count_page'] == 0 and item['kp_count_nonpage'] > 0:
            item['kp_iscommenteronly'] = True
        if item['kp_count_all'] > 0 and item['kp_count_page'] > 0 and item['kp_count_nonpage'] > 0:
            item['kp_isboth'] = True

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
        idfmap[idf.term] = float(idf.val) ** 3

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


