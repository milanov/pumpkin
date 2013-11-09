__author__ = 'reggie'

import threading
import socket, os
import time
import tftpy
import json
import hashlib
import struct
import fcntl
import zmq

from select import select
from socket import *
from threading import *


from PmkShared import *

def get_interface_ip(ifname):
        s = socket(AF_INET, SOCK_DGRAM)
        return inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s',
                                ifname[:15]))[20:24])

def get_lan_ip():
    ip = gethostbyname(gethostname())
    if ip.startswith("127.") and os.name != "nt":
        interfaces = [
            "eth0",
            "eth1",
            "eth2",
            "wlan0",
            "wlan1",
            "wifi0",
            "ath0",
            "ath1",
            "ppp0",
            ]
        for ifname in interfaces:
            try:
                ip = get_interface_ip(ifname)
                break
            except IOError:
                pass
    return ip

def get_zmq_supernodes(node_list):
    ret = []
    for sn in node_list:
        s = "tcp://"+sn+":"+str(ZMQ_PUB_PORT)
        ret.append(s)
    return ret

class ZMQBroadcaster(SThread):
    def __init__(self, context, zmq_context,  port):
        SThread.__init__(self)
        self.context = context
        self.port = port
        self.zmq_cntx = zmq_context

    def run(self):
        log.info("Starting thread: "+self.__class__.__name__)
        sock = self.zmq_cntx.socket(zmq.PUB)
        sock.bind("tcp://*:"+str(self.port))

        while True:
            if not self.context.getProcGraph().isRegistryModified():
                time.sleep(30)
                data = self.context.getProcGraph().dumpRegistry()
                sock.send(data)
                if self.stopped():
                    log.debug("Exiting thread: "+self.__class__.__name__)
                    break
                else:
                    continue

            if self.context.getProcGraph().isRegistryModified():
                data = self.context.getProcGraph().dumpRegistry()
                self.context.getProcGraph().ackRegistryUpdate()
                log.debug("Publishing new registry data")
                sock.send(data)
                if self.stopped():
                    log.debug("Exiting thread: "+self.__class__.__name__)
                    break
                else:
                    continue

class ZMQBroadcastSubscriber(SThread):
    def __init__(self, context, zmq_context, zmq_endpoint):
        SThread.__init__(self)
        self.context =  context
        self.zmq_endpoint = zmq_endpoint
        self.zmq_cntx = zmq_context


    def run(self):


        sock = self.zmq_cntx.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, '')
        sock.connect(self.zmq_endpoint)
        while True:
            data = sock.recv()
            #log.debug("Incomming data: "+data)
            d = json.loads(data)
            for k in d.keys():
                self.context.getProcGraph().updateRegistry(d[k])




class BroadcastListener(Thread):

    def __init__(self, context, port):
        Thread.__init__(self)
        self.__stop = Event()
        self.__port = port
        self.context = context
        self.bclist = {}
        pass

    def run(self):
        log.info("Starting broadcast listener on port "+str(self.__port))
        sok = socket(AF_INET, SOCK_DGRAM)
        sok.bind(('', self.__port))
        sok.settimeout(5)
        while 1:
            try:
                data, wherefrom = sok.recvfrom(1500, 0)

            except(timeout):
                #log.debug("Timeout")
                if self.stopped():
                    log.debug("Exiting thread")
                    break
                else:
                    continue
            log.debug("Broadcast received from: "+repr(wherefrom))
            #log.debug("Broadcast data: "+data)
            #datam = hashlib.md5(data).hexdigest()
            #log.debug("MD5 data: "+datam)
            self.handle(data,wherefrom)

            #reply = self.__context.dumpRegistry()
            #sok.sendto(reply, wherefrom)
            #if not ( wherefrom[0] in self.tested):
            #    self.handle(data,wherefrom)

    def handle(self, data, wherefrom):
        #try:
            #pass
            #self.tested[wherefrom[0]] = True
            d = json.loads(data)
            for k in d.keys():
                self.context.getProcGraph().updateRegistry(d[k])

            #uid = d["uid"]
            #if not uid in self.bclist:
            #    log.info("Discovered new peer: "+uid)
            #    log.debug("New peer data: "+data)

            #self.bclist[uid] = d
            #port = int(d["comms"][0]["port"])
            #client = tftpy.TftpClient(wherefrom[0], port)
            #filename = "sample_"+wherefrom[0]+".jpg"
            #client.download('sample.jpg', filename)
            #self.tested[wherefrom[0]] = True

        #except:
        #    log.error("Some error")



    def stop(self):
        self.__stop.set()

    def stopped(self):
        return self.__stop.isSet()


class Broadcaster(SThread):
    def __init__(self, context, port=UDP_BROADCAST_PORT, rate=30):
        SThread.__init__(self)
        self.__port = port
        self.__rate = rate
        self.context = context
        pass

    def run(self):
        log.info("Shouting presence to port "+str(self.__port)+" at rate "+str(self.__rate))
        #sok = socket(AF_INET, SOCK_DGRAM)
        #sok.bind(('', 0))
        #sok.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        #data = self.__context.getUuid() + '\n'
        #data = self.__context.getPeer().getJSON()


        while 1:
            #sok.sendto(data, ('<broadcast>', UDP_BROADCAST_PORT))
            #time.sleep(self.__rate)

            data = self.context.getProcGraph().dumpRegistry()
            if self.context.getProcGraph().isRegistryModified():
                self.context.getProcGraph().ackRegistryUpdate()
                self.announce(data)
                time.sleep(2)
            else:
                time.sleep(self.__rate)


            if self.stopped():
                break
            else:
                continue

    def announce(self, msg, port=UDP_BROADCAST_PORT):
        sok = socket(AF_INET, SOCK_DGRAM)
        sok.bind(('', 0))
        sok.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)


        for sn in self.context.getSupernodeList():
            sok.sendto(msg, (sn, port) )
            time.sleep(1)
        pass




class FileServer(Thread):
    def __init__(self, context, port, root="./rx/"):
        Thread.__init__(self)
        self.__stop = Event()
        self.__port = port
        self.__root = root
        self.__context = context

        self.__ensure_dir(self.__root)
        pass

    def run(self):
        log.info("Starting file server on port "+str(self.__port)+" at root "+str(self.__root))

        self.__server = tftpy.TftpServer(self.__root)
        self.__server.listen("0.0.0.0", TFTP_FILE_SERVER_PORT, 10)

    def __ensure_dir(self, f):
        d = os.path.dirname(f)
        if not os.path.exists(d):
            os.makedirs(d)

    def stop(self):
        self.__stop.set()
        self.__server.stop()

    def stopped(self):
        return self.__stop.isSet()



#class RendezvousServer(Thread):
#
#
#    def __init__(self, context, port):
#        Thread.__init__(self)
#        self.__stop = Event()
#        self.__port = port
#        self.__context = context
#        self.poolqueue = {}
#
#    def run(self):
#        log.info("Starting Rendezvous server on port "+str(self.__port))
#        sok = socket(AF_INET, SOCK_DGRAM)
#        sok.bind(('', self.__port))
#        sok.settimeout(5)
#        while 1:
#            try:
#                data, addr = sok.recvfrom(32)
#            except timeout:
#                log.debug("RendezvousServer Timeout")
#                if self.stopped():
#                    log.debug("Exiting RendezvousServer thread")
#                    break
#                else:
#                    continue
#
#            log.info("Connection from %s:%d" % addr)
#            pool = data.strip()
#            sok.sendto( "ok "+pool, addr )
#            data, addr = sok.recvfrom(2)
#            if data != "ok":
#                continue
#            log.info("Request received for pool: ", pool)
#            try:
#                a, b = self.poolqueue[pool], addr
#                sok.sendto( self.addr2bytes(a), b )
#                sok.sendto( self.addr2bytes(b), a )
#                log.info("Linked", pool)
#                del self.poolqueue[pool]
#            except KeyError:
#                self.poolqueue[pool] = addr
#
#    def addr2bytes( self, addr ):
#
#        """Convert an address pair to a hash."""
#        host, port = addr
#        try:
#            host = socket.gethostbyname( host )
#        except (socket.gaierror, socket.error):
#            raise ValueError, "Invalid host"
#        try:
#            port = int(port)
#        except ValueError:
#            raise ValueError, "Invalid port"
#        bytes  = socket.inet_aton( host )
#        bytes += struct.pack( "H", port )
#        return bytes
#
#    def stop(self):
#        self.__stop.set()
#
#    def stopped(self):
#        return self.__stop.isSet()
#
#
#class HoleComm(Thread):
#
#    def __init__(self, context, server, port, link):
#        Thread.__init__(self)
#        self.__stop = Event()
#        self.__port = port
#        self.__context = context
#        self.__server = server
#        self.__link = link
#
#    def run(self):
#
#        master = (self.__server, int(self.__port))
#
#        sockfd = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
#        sockfd.sendto( self.__link, master )
#        data, addr = sockfd.recvfrom( len(self.__link)+3 )
#        if data != "ok "+self.__link:
#            print >>sys.stderr, "unable to request!"
#            sys.exit(1)
#        sockfd.sendto( "ok", master )
#        print >>sys.stderr, "request sent, waiting for parkner in pool '%s'..." % self.__link
#        data, addr = sockfd.recvfrom( 6 )
#
#        target = self.bytes2addr(data)
#        print >>sys.stderr, "connected to %s:%d" % target
#
#        while True:
#            rfds,_,_ = select( [0, sockfd], [], [] )
#            if 0 in rfds:
#                data = sys.stdin.readline()
#                if not data:
#                    break
#                sockfd.sendto( data, target )
#            elif sockfd in rfds:
#                data, addr = sockfd.recvfrom( 1024 )
#                sys.stdout.write( data )
#
#        sockfd.close()
#
#    def bytes2addr(self, bytes ):
#        """Convert a hash to an address pair."""
#        if len(bytes) != 6:
#            raise ValueError, "invalid bytes"
#        host = socket.inet_ntoa( bytes[:4] )
#        port, = struct.unpack( "H", bytes[-2:] )
#        return host, port