__author__ = 'reggie'


###START-CONF
##{
##"object_name": "collectorall",
##"object_poi": "qpwo-2345",
##"parameters": [
##                 {
##                      "name": "tweet",
##                      "description": "english haiku tweets",
##                      "required": true,
##                      "type": "TweetString",
##                      "format": "",
##                      "state" : "ISA|HASA|HAIKU|NONENGLISH|ENGLISH"
##                  }
##              ],
##"return": [
##
##          ] }
##END-CONF



import re


from pumpkin import PmkSeed

import json
import re
import networkx as nx
from networkx.readwrite import json_graph



class collectorall(PmkSeed.Seed):

    def __init__(self, context, poi=None):
        PmkSeed.Seed.__init__(self, context,poi)

        pass

    def on_load(self):
        print "Loading: " + self.__class__.__name__
        pass


    def run(self, pkt, tweet):
        pass

