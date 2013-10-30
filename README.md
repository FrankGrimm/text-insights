text-insights
=============

Note on the required python-facebook-sdk module: All urllib.urlencode calls in the facebook-sdk dependency have to be changed to add True as the second parameter (in order to support unicode dicts)
