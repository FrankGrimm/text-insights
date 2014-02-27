from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import *
from ti import models

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
import csv

# hide facebook deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# global logging setup
logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    args = '<filename>'
    help = 'Import geo data for locations'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self._log = logging.getLogger('cmd')

    def handle(self, *args, **options):
        if args is None or len(args) < 1:
            raise CommandError('Invalid arguments. Expected: <filename>')

        fname = args[0]
        self._log.info('ImportCountryData initializing.')
        self._log.info('Filename: %s' % fname)
        self.importData(fname)

    def importData(self, filename):
        with open(filename) as f:
            reader = csv.reader(f, delimiter=';', quoting=csv.QUOTE_NONE)
            next(reader, None) # skip header line
            for row in reader:
                self.importRow(row)

    def importRow(self, row):
        print row
        _, created = models.CountryLocales.objects.get_or_create(ccode=row[1], defaults={'continent': row[0], 'cname': row[2], 'lati': row[3], 'longi': row[4]})
        if created:
            self._log.info('Country created: %s' % row[2]) #Continent;Code;Name;Latitude;Longitude
