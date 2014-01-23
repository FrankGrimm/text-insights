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

from fbutils import PageCrawler, Post, AnonymizeUsers

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

