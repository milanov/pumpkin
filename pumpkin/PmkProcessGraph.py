__author__ = 'reggie'

import ujson as json
import networkx as nx
import time
import thread
import threading
import copy
import re

from networkx.readwrite import json_graph

from PmkShared import *


class ProcessGraph(object):

    MAX_TTL = 60 #seconds
    INT_TTL = 15 #seconds
    def __init__(self):

        self.registry = {}
        self.external_registry = {}
        self.__reg_update = False
        self.__display_graph = False
        self.rlock = threading.RLock()
        self.graph = nx.DiGraph()
        self.ep_graph = nx.DiGraph()
        self.func_graph = nx.DiGraph()
        self.tagroute = {}
        self.ttl = {}

        threading.Timer(self.INT_TTL, self.__update_registry_t).start()

    pass

    def __key(self,name, ep):
        return name+":|:"+ep

    def __reset_ep_ttl(self, name, ep):
        key = self.__key(name, ep)
        self.ttl[key] = self.MAX_TTL
        pass

    def __subtract_ep_ttl(self, name, ep, sub_count):
        key = self.__key(name,ep)
        if key in self.ttl.keys():
            self.ttl[key] -= sub_count
        pass
    def __split_key(self, key):
        spl = key.split(":|:")
        return (spl[0], spl[1])

    def __del_ep(self, key):

        name, ep = self.__split_key(key)
        if name in self.registry.keys():
            e = self.registry[name]
            c = -1
            for i in range(len(e["endpoints"])):
                if e["endpoints"][i]["ep"] == ep:
                    c = i
                    break
            if c > -1:
                logging.info("Removed stale entry for seed "+name+" at "+ep)
                del e["endpoints"][c]




    def __update_registry_t(self):
        self.rlock.acquire()
        keys_for_removal = []
        for key in self.ttl.keys():
            self.ttl[key] -= self.INT_TTL
            if self.ttl[key] <= 0:
                self.__del_ep(key)
                self.__reg_update = True
                keys_for_removal.append(key)


        for rk in keys_for_removal:
            del self.ttl[rk]

        if self.__reg_update == True:
            self.graph = self.buildGraph()

        self.rlock.release()

        threading.Timer(self.INT_TTL, self.__update_registry_t).start()

    def dumpRoutingTable(self):
        return json.dumps(self.tagroute)

    def updateRegistry(self, entry, loc="remote"):

        registry = self.registry

        e = entry
        a = []
        tep = []
        self.rlock.acquire()
        if e["name"] in registry.keys():
            logging.debug("Updating peer: "+e["name"])
            #d is local registry
            #e is entry to update
            d = registry[e["name"]]
            epb = False
            for eep in e["endpoints"]:
                found = False
                for dep in d["endpoints"]:
                    if dep["ep"] == eep["ep"]:
                        found = True
                        self.__reset_ep_ttl(e["name"], eep["ep"])

                if not found:
                    if loc == "remote":
                        eep["priority"] = 10
                        self.__reset_ep_ttl(e["name"], eep["ep"])
                    d["endpoints"].append(eep)
                    logging.info("Discovered remote seed: "+e["name"]+" at "+eep["ep"])
                    self.__reg_update = True
                    self.__display_graph = True
        else:
            logging.info("Discovered new seed: "+e["name"]+" at "+e["endpoints"][0]["ep"])
            if loc == "remote":
                for ep in e["endpoints"]:
                    ep["priority"] = 10
                    self.__reset_ep_ttl(e["name"], ep["ep"])

            registry[e["name"]] = e
            self.__reg_update = True
            self.__display_graph = True

        if self.__reg_update == True:
            self.graph = self.buildGraph()

        self.rlock.release()

    def displayGraph(self):
        return self.__display_graph

    def resetDisplay(self):
        self.__display_graph = False

    def getRoutes(self, tag):
        #logging.debug("Finding route for "+ tag)
        if tag in self.tagroute:
            return self.tagroute[tag]

    def getPriorityEndpoint(self, route):
        bep = None
        prt = 1000
        for ep in route['endpoints']:
            p = int(ep["priority"])
            if p < prt:
                bep = ep
                prt = p

        return bep

    def stopSeed(self, seed):
        self.rlock.acquire()
        if seed in self.registry.keys():
            entry = self.registry[seed]
            entry["enabled"] = "False"
            self.__reg_update = True
            self.__display_graph = True

        if self.__reg_update == True:
            self.graph = self.buildGraph()
        self.rlock.release()
        return True

    def startSeed(self, seed):
        self.rlock.acquire()
        if seed in self.registry.keys():
            entry = self.registry[seed]
            entry["enabled"] = "True"
            self.__reg_update = True
            self.__display_graph = True

        if self.__reg_update == True:
            self.graph = self.buildGraph()
        self.rlock.release()
        return True

    def getExternalEndpoints(self, route):
        eps = []
        bep = None
        prt = 10
        pep = self.getPriorityEndpoint(route)
        for ep in route['endpoints']:
            p = int(ep["priority"])
            if p >= prt:
                if not ep["ep"] == pep["ep"]:
                    eps.append(ep)

        return eps

    def get_ep_with_priority(self, eps, priority):
        p = priority
        lep = None
        for ep in eps:
            if int(ep["priority"]) >= p:

                lep = ep
                return lep

        return lep


    def buildGraph(self):
        self.tagroute = {}
        self.graph = nx.DiGraph()
        self.ep_graph = nx.DiGraph()
        self.func_graph = nx.DiGraph()
        G = self.graph
        E = self.ep_graph
        F = self.func_graph


        for xo in self.registry.keys():
            eo = self.registry[xo]
            if (eo["enabled"] == "True") and (len(eo["endpoints"]) > 0):
                #for isp in eo["istate"].split('|'):
                #    for osp in eo["ostate"].split('|'):
                for isp in re.split('\||\&', eo["istate"]):
                    for osp in re.split('\||\&', eo["ostate"]):

                        istype = eo["itype"]+":"+isp
                        if istype == "NONE:NONE":
                               istype = "INJECTION"
                        istype = eo["group"] +":"+ istype
                        ostype = eo["otype"]+":"+osp
                        if ostype == "NONE:NONE":
                            ostype = "EXTRACTION"
                        ostype = eo["group"] +":"+ ostype
                        lep = self.get_ep_with_priority(eo["endpoints"], 0)
                        if lep:
                            G.add_edge(istype, ostype, function=eo["name"], ep=lep["ep"])
                        else:
                            G.add_edge(istype, ostype, function=eo["name"])

                    if istype in self.tagroute.keys():
                        self.tagroute[istype].append(eo)
                    else:
                        self.tagroute[istype] = []
                        self.tagroute[istype].append(eo)

        for edge in G.edges(data=True):
            n1 = edge[0]
            n2 = edge[1]

            n1_routes = []
            n2_routes = []
            n2_name = None
            n1_name = None
            if n1 in self.tagroute.keys() and "TRACE" not in n1:
                n1_routes = self.tagroute[n1][0]["endpoints"]
                n1_name = self.tagroute[n1][0]["name"].split(":")[1]+"()"
            if n2 in self.tagroute.keys() and "TRACE" not in n2:
                n2_routes = self.tagroute[n2][0]["endpoints"]
                n2_name = self.tagroute[n2][0]["name"].split(":")[1]+"()"


            #if len(n2_name.split(":")) > 1:
            #    n2_name = n2_name.split(":")[1]

            #if len(n2_name.split(":")) > 1:
            #    n2_name = n2_name.split(":")[1]


            for n1s in n1_routes:
                for n2s in n2_routes:
                    E.add_node(n1s["ep"], ip= n1s["ip"])
                    E.add_node(n2s["ep"], ip= n2s["ip"])

                    E.add_edge(n1s["ep"],n2s["ep"])
                    #F.add_edge(n1s["cuid"], n2s["cuid"])
                    F.add_edge(n1_name, n2_name)
            #girien = G.neighbors(edge[1])

            #n1 = edge[2]["ep"]
            #n_name = edge[2]["function"]
            #n2 = None

            #for g in girien:
            #    for e in G.edges(g, data=True):
            #        n2 = e[2]["ep"]
            #        print n1+"->"+n2+" "+n_name

            #if len(gara) > 0:
            #    gara_edge = G.out_edges(gara[0], data=True)
            #    if len(gara_edge) > 0:
            #        n2 = gara_edge[0][2]["ep"]

            #if n2:
            #    print n1+"->"+n2+" "+n_name



        return G

    def showGraph(self):
        #import matplotlib.pyplot as plt
        #nx.draw(self.graph)
        #plt.show()
        pass


    def isRegistryModified(self):
        return self.__reg_update

    def ackRegistryUpdate(self):
        self.rlock.acquire()
        self.__reg_update = False
        self.rlock.release()
        pass

    def dumpGraph(self):
        d = json_graph.node_link_data(self.graph)
        return json.dumps(d)
        #return str(nx.generate_graphml(self.graph))

    def dump_ep_graph(self):
        d = json_graph.node_link_data(self.ep_graph)
        return json.dumps(d)

    def dump_func_graph(self):
        d = json_graph.node_link_data(self.func_graph)
        return json.dumps(d)

    def dumpGraphToFile(self, filename):
        d = json_graph.node_link_data(self.graph)
        json.dump(d, open(filename,'w'))

        pass

    def dump_ep_graph_to_file(self, filename):
        d = json_graph.node_link_data(self.ep_graph)
        json.dump(d, open(filename,'w'))

        pass

    def dump_func_graph_to_file(self, filename):
        d = json_graph.node_link_data(self.func_graph)
        json.dump(d, open(filename,'w'))

        pass


    def dumpRegistry(self):
        self.rlock.acquire()
        d = json.dumps(self.registry)
        self.rlock.release()
        return d

    def dumpExternalRegistry(self):

        self.rlock.acquire()
        ne = copy.deepcopy(self.registry)
        self.rlock.release()
        tmp_keys = []
        for k in ne.keys():
            f = ne[k]
            #Filter out endpoints with less than priority 15. Any priority less than 5
            #is reserved for local communication such as IPC, INPROC, FILES and remote TCP
            f["endpoints"][:] = [x for x in f["endpoints"] if self.__determine(x)]
            if len(f["endpoints"]) == 0 or (f["enabled"] == "False"):
                tmp_keys.append(k)

        for rk in tmp_keys:
            del ne[rk]


        d = json.dumps(ne)
        return d

    def __determine(self, ep):
        if int(ep["priority"]) < 15:
            return False
        else:
            return True

    def printRegistry(self):
        for x in self.registry.keys():
            e = self.registry[x]
            logging.info("Name: " + e["name"])
            for p in e["zmq_endpoint"]:
                logging.info("Endpoint: "+p)
            logging.info("Itype: " + e["itype"])
            logging.info("Istate: "+e["istate"])
            logging.info("Otype: " + e["itype"])
            logging.info("Ostate: "+e["istate"])
