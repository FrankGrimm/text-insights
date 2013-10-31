# views

from django.http import HttpResponse
from django.template import Context, loader
from django.shortcuts import render, redirect
import collections
import datetime
import os
import ti
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.db.models import Max, Min, Count
from ti.models import *
import json

def home(request):
    ctx = {'pages': Page.objects.all}
    return render(request, 'pagelist', ctx, content_type="text/html")

def page_info(request, page_id=None):
    if page_id is None:
        raise Exception("Invalid page id")
    ctx = {}

    # add page meta-information
    page = ctx['page'] = Page.objects.get(id=page_id)

    # add general information on posts
    minmax = Post.objects.filter(page__exact=page).aggregate(dt_first=Min('createtime'), dt_last=Max('createtime'))
    ctx['firstpost_dt'], ctx['lastpost_dt'] = minmax['dt_first'], minmax['dt_last']
    ctx['postcount'] = Post.objects.filter(page__exact=page).exclude(posttype__exact='comment').count()
    ctx['commentcount'] = Post.objects.filter(page__exact=page, posttype__exact='comment').count()

    page_info_posttypecounts(page, ctx)
    page_info_posts(page, ctx)

    return render(request, 'pageoverview', ctx, content_type="text/html")

def page_info_posts(page, ctx):
    # all posts for this page
    posts = Post.objects.filter(page__exact=page).exclude(posttype__exact='comment').order_by('createtime').prefetch_related('createuser').all()

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
    for mid in sorted(months.iterkeys()):
        posts_by_month.append(months[mid])

    ctx['comments'] = comments
    ctx['posts_by_month'] = posts_by_month
    ctx['posts'] = posts

def page_info_posttypecounts(page, ctx):
    # add counts of different post types
    typecounts = Post.objects.filter(page__exact=page).values('posttype').annotate(Count('posttype'))
    posttypes = {}
    for typecount in typecounts:
        posttypes[typecount['posttype']] = typecount['posttype__count']
    ctx['posttypes'] = posttypes
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
    #return renderTemplate(request, "hello", ctx)
    return render(request, 'home', ctx, content_type="text/html")

def json_serve(request):
    page_id = request.GET['page']
    which_tags = request.GET['tags']
    response_data = [
   {'text': "Lorem", 'weight': 15},
   {'text': "Ipsum", 'weight': 9, 'link': "http://jquery.com/"},
   {'text': "Dolor", 'weight': 6},
   {'text': "Sit", 'weight': 7},
   {'text': "Amet", 'weight': 5}
    ]
    return HttpResponse(json.dumps(response_data), content_type="application/json")


def overview_view(request):
    ctx = {}
    ctx['pages'] = Page.objects.all()
    return render(request, 'overview', ctx, content_type="text/html")

def renderTemplate(request, templateId, context):
    t = loader.get_template(templateId)
    c = Context(context)
    html = t.render(c)
    return HttpResponse(html)

