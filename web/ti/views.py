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

def home(request):
    return render(request, 'intro', {}, content_type="text/html")

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

@login_required
def template(request):
    ctx = {'name': 'yourname','now':datetime.datetime.now()}
    #return renderTemplate(request, "hello", ctx)
    return render(request, 'home', ctx, content_type="text/html")

def overview_view(request):
    ctx = {}
    ctx['pages'] = Page.objects.all()
    return render(request, 'overview', ctx, content_type="text/html")

def renderTemplate(request, templateId, context):
    t = loader.get_template(templateId)
    c = Context(context)
    html = t.render(c)
    return HttpResponse(html)
