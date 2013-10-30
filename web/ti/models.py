from __future__ import unicode_literals

from django.db import models

class Keyphrase(models.Model):
    id = models.AutoField(primary_key=True)
    method = models.ForeignKey('KeyphraseMethod')
    text = models.TextField()
    val = models.DecimalField(max_digits=20, decimal_places=10)
    class Meta:
        db_table = 'keyphrase'

class KeyphraseMethod(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50L)
    description = models.TextField()
    class Meta:
        db_table = 'keyphrase_method'

class Post(models.Model):
    id = models.AutoField(primary_key=True)
    fb_post_id = models.CharField(max_length=255L)
    posttype = models.CharField(max_length=25L, db_column='type')
    text = models.TextField()
    createtime = models.DateTimeField()
    likes = models.IntegerField()
    parent = models.ForeignKey('self', null=True, db_column='parent', blank=True)
    page = models.ForeignKey('Page', db_column='page')
    createuser = models.ForeignKey('User', db_column='createuser')
    class Meta:
        db_table = 'post'

class PostKeyphraseAssoc(models.Model):
    post = models.ForeignKey(Post)
    keyphrase = models.ForeignKey(Keyphrase)
    offset = models.IntegerField()
    length = models.IntegerField()
    class Meta:
        db_table = 'post_keyphrase_assoc'
        unique_together = ('post', 'keyphrase')

class User(models.Model):
    id = models.BigIntegerField(primary_key=True)
    fullname = models.CharField(max_length=500L)
    alias = models.CharField(max_length=50L)
    class Meta:
        db_table = 'user'

class Page(models.Model):
    id = models.AutoField(primary_key=True)
    fb_page_id = models.CharField(max_length=100L)
    fb_page_name = models.CharField(max_length=2048L)
    last_updated = models.DateTimeField()
    owner = models.ForeignKey('User', db_column='owner')
    class Meta:
        db_table = 'page'

