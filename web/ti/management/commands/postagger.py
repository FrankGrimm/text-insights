# -*- coding: utf-8 -*-
''' Wrapper for ark-tweet-nlp '''

import subprocess
import shlex
import os
from django.conf import settings
import logging

class POSTagger(object):
    def __init__(self, callback):
        self._log = logging.getLogger("POSTagger")
        self.tagger_command = os.path.expanduser(settings.POS_TAGGER['command'])
        self.queue = []
        self.queue_max_size = settings.POS_TAGGER['max_queue']
        self._log.info("Command: %s" % self.tagger_command)
        self._log.info("Max queue size: %s" % self.queue_max_size)
        self._cb = callback

    def enqueue(self, post=None, text=None, forceProcessing=False):
        if post is not None and text is not None:
            self.queue.append([post, text])

        if forceProcessing or len(self.queue) >= self.queue_max_size:
            tmpqueue = self.queue
            self.queue = []
            self.processTexts(tmpqueue)
        pass

    def processTexts(self, texts):
        self._log.info("Processing %s texts" % len(texts))
        raw = self.getRawTexts(texts)
        self.runCommand(texts, raw)

    def runCommand(self, texts, raw):
        proc_args = shlex.split(self.tagger_command)
        proc = subprocess.Popen(proc_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p_stdout, p_stderr = proc.communicate(raw)

        if p_stderr is not None:
            self._log.info(p_stderr.strip().split('\n')[1])

        self.parseResult(texts, p_stdout)

    def parseResult(self, texts, taggerResult):
        all_results = []
        cur_result = []

        for line in taggerResult.split('\n'):
            if line == '':
                if len(cur_result) > 0:
                    all_results.append(cur_result)
                    cur_result = []
                continue
            token, tag, confidence = line.split('\t')
            confidence = float(confidence)
            cur_result.append([token, tag, confidence])


        self._log.info("Received tag-information for %s documents. Expected: %s" % (len(all_results), len(texts)))
        if (len(all_results) != len(texts)):
            self._log.warn("Assertion failed.")
            return
            #exit()

        for idx in range(len(all_results)):
            texts[idx].append(all_results[idx])

        self.reportBack(texts)

    def reportBack(self, texts):
        for post, text, tags in texts:
            self._cb(post, text, tags)

    def getRawTexts(self, texts):
        raw_texts = []
        for post, text in texts:
            raw_text = ' '.join(text).replace('\r', ' ').replace('\n', ' ').strip()
            if raw_text == "":
                raw_text = "EMPTY_TEXT"
            raw_texts.append(raw_text)

        return "\n".join(raw_texts)
