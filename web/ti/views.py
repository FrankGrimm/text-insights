# views

from django.http import HttpResponse
from django.template import Context, loader
from django.shortcuts import render, redirect
import datetime
import os
import ti
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from ti.models import *
import json

def home(request):
    ctx = {'pages': Page.objects.all}
    return render(request, 'pagelist', ctx, content_type="text/html")

def page_info(request, page_id=None):
    if page_id is None:
        raise Exception("Invalid page id")
    return render(request, 'pageoverview', {}, content_type="text/html")

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
