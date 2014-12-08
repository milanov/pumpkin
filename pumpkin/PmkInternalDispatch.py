__author__ = 'reggie'

import ujson as json
import Queue
import zmq
import time
import pika
import zlib
import base64
import PmkSeed
import PmkBroadcast
import PmkShared
#import PmkContexts
from PmkShared import *
from PmkPacket import *
#from PmkContexts import *
from Queue import *


class rx(Queue):
    def __init__(self, maxsize=0, context=None):
        Queue.__init__(self, maxsize)
        self.__state_switch = False
        self.__green = True
        self.context = context

        pass

    def __load(self, pkt):
        header = pkt[0]

        if header["aux"] & Packet.NACK_BIT:
            if header["aux"] & Packet.TRACER_BIT:
                host = header["last_host"]
                c_tag = header["c_tag"]
                pred = header["c_pred"]
                c_wtime = header["c_wtime"]
                logging.debug("TRACER ACK: "+json.dumps(pkt))

                self.context.getProcGraph().update_ep_prediction(pred, host,c_tag)

        if self.dig(pkt):
            # if not p_dig:
            #     #release backpressure
            #     p_dig = True
            #     last_contact = header["last_contact"]
            #     header["aux"] = header["aux"] | Packet.BCKPRESSURE_BIT
            #     #header["aux"] = header["aux"] | Packet.PRESSURETOGGLE_BIT
            #     header["last_host"] = self.context.get_uuid()
            #     self.context.get_tx(2).put((None,None,None,pkt))

            self.put(pkt)

        else:
            p_dig = False
            #back pressure

            last_contact = header["last_contact"]
            header["aux"] = header["aux"] | Packet.BCKPRESSURE_BIT
            header["aux"] = header["aux"] | Packet.PRESSURETOGGLE_BIT
            header["last_host"] = self.context.get_uuid()
            self.context.get_tx(2).put((None,None,None,pkt))

            #print last_contact
            pass

    def parse_n_load(self, pkt):
        header = pkt[0]
        if header["aux"] & Packet.MULTIPACKET_BIT:
            pkt_list = pkt[2:]
            for apkt in pkt_list:
                self.__load(apkt)
        else:
            self.__load(pkt)


    def dig(self, pkt):
        ret = True
        #print "DIG: "+json.dumps(pkt)
        header = pkt[0]
        if header["aux"] & Packet.CODE_BIT:
            # accept or forward
            pass
        if (header["aux"] & Packet.LOAD_BIT) or (header["aux"] & Packet.TIMING_BIT) :

            if (pkt[0]["state"] == "TRANSIT") or (pkt[0]["state"] == "NEW"):
                iplugins = PmkSeed.iplugins
                keys = PmkSeed.iplugins.keys
                l = len(pkt)
                func = pkt[l-1]["func"]
                #data = pkt[l-2]["data"]

                if ":" in func:
                    func = func.split(":")[1]

                if func in keys():
                    klass = iplugins[func]
                    ret = klass.look_ahead(pkt)
                    #if not ret == self.__green:
                    #    self.__

        return ret

class InternalDispatch(SThread):
    _packed_pkts = 0
    def __init__(self, context):
        SThread.__init__(self)
        self.context = context
        pass


    def _dispatch(self, pkt):
        pktdj = pkt
        pkt_len = len(pktdj)

        stag_p = pktdj[pkt_len - 1]["stag"].split(":")


        if len(stag_p) < 3:
            group = "public"
            type = stag_p[0]
            tag = stag_p[1]
        else:
            group = stag_p[0]
            type = stag_p[1]
            tag = stag_p[2]

        self.context.getTx().put((group, tag,type,pktdj))


    def run(self):
        rx = self.context.getRx()
        #loads = json.loads
        keys = PmkSeed.iplugins.keys
        iplugins = PmkSeed.iplugins
        speedy = self.context.is_speedy()

        x = 0
        while 1:
            #already in json format
            pkt = rx.get(True)
            aux = 0
            header = pkt[0]
            gonzales = False
            if "aux" in header.keys():
                aux = header["aux"]

            if aux & Packet.TRACER_BIT:
                #stat = self.context.get_stat()
                #print stat
                #continue
                pass

            if aux & Packet.GONZALES_BIT:
                gonzales  = True

            if aux & Packet.CODE_BIT:
                #if x == 0:
                #   x = 1
                #   self._dispatch(pkt)
                #   continue
                logging.debug("Received CODE packet...")
                seeds = header["seeds"]
                forward = False
                deployed = False
                for seed_key in seeds.keys():
                    seed = seeds[seed_key]
                    seed_code = base64.decodestring(seed["code"])
                    seed_count = seed["count"]
                    if deployed and seed_count > 0:
                        forward = True
                        break
                    if seed_count > 0:
                        logging.debug("Loading seed "+seed_key+" from CODE packet.")
                        self.context.load_seed_from_string(seed_code)
                        seed["count"] -= 1
                        deployed = True
                        #if seed["count"] > 0:
                        #    forward = True

                if forward:

                    header["traces"].append(self.context.getUuid())
                    self.context.get_tx(2).put((None,None,None,pkt))
                    #exdisp = self.context.getExternalDispatch()
                    #exdisp.send_to_random_one(pkt)

                #only load code
                continue

                # l = len(pkt)
                # if "tracer" in pkt[l-1]["func"]:
                #     pkt.pop()
                #
                # del pkt[0]["seeds"]

            #logging.debug("Packet received: \n"+pkts)
            #pkt = json.loads(pkts)
            #pkt = loads(pkts)
            if aux & Packet.NACK_BIT and header["state"] == Packet.PKT_STATE_PACK_OK:


                seed = header["last_func"]
                if seed in PmkSeed.iplugins.keys():
                    klass = PmkSeed.iplugins[seed]
                    klass.pack_ok(pkt)
                    self._packed_pkts += 1
                    #logging.debug("PACKED pkts: "+str(self._packed_pkts))
                    continue

            # if pkt[0]["state"] == "MERGE":
            #     seed = pkt[0]["last_func"]
            #
            #     if seed in PmkSeed.iplugins.keys():
            #         klass = PmkSeed.iplugins[seed]
            #         klass.merge(pkt)
            #         #klass.pack_ok(pkt)
            #         #self._packed_pkts += 1
            #         #logging.debug("PACKED pkts: "+str(self._packed_pkts))
            #         continue

            if header["state"] == "ARP_OK":
                logging.debug("Received ARP_OK: "+json.dumps(pkt))
                self.context.put_pkt_in_shelve2(pkt)
                continue

            #print json.dumps(pkt)
            l = len(pkt)
            func = pkt[l-1]["func"]
            if "data" in pkt[l-2]:
                data = pkt[l-2]["data"]
            else:
                self._dispatch(pkt)
                continue


            if ":" in func:
                func = func.split(":")[1]


            #if func in PmkSeed.iplugins.keys():
            #    klass = PmkSeed.iplugins[func]
            #    rt = klass._stage_run(pkt, data)



            if func in keys():
                klass = iplugins[func]
                if gonzales:
                    rt = klass._stage_run_express(pkt, data)
                else:
                    rt = klass._stage_run(pkt, data)
            else:
                #put on TX
                self._dispatch(pkt)
                continue





class Injector(SThread):
    def __init__(self, context):
        SThread.__init__(self)
        self.context = context

    def run(self):
        for x in PmkSeed.iplugins.keys():
            klass = PmkSeed.iplugins[x]
            if not klass.hasInputs():
                #klass.run(klass.__rawpacket())
                klass.rawrun()

            if self.stopped():
                logging.debug("Exiting thread "+self.__class__.__name__)
                break
            else:
                continue

class RabbitMQMonitor():
    class MonitorThread(SThread):
        def __init__(self, parent, context, connection, queue, exchange=''):
            SThread.__init__ (self)
            self.context = context

            host, port, username, password, vhost = self.context.get_rabbitmq_cred()
            credentials = pika.PlainCredentials(username, password)
            if connection == None:
                self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=host,  credentials=credentials, virtual_host=vhost))
            else:
                self.connection = connection

            self.parent = parent
            self.tag_map = self.parent.tag_map
            self.channel = self.connection.channel()
            #self.channel.basic_qos(prefetch_count=1000, all_channels=True)
            self.queue = queue
            self.exchange = exchange
            self.cnt = 0
            #self.channel.basic_qos(prefetch_count=1000, all_channels=True)
            #self.channel.exchange_declare(exchange=str(exchange), type='fanout')
            #self.channel.queue_declare(queue=str(queue))
            #self.channel.queue_bind(exchange=str(exchange),
            #       queue=str(queue))
            #args = {"x-max-length":2}
            args = {}

            self.channel.queue_declare(queue=str(queue), durable=False, exclusive=True, arguments=args)
            self.channel.basic_qos(prefetch_count=1000)
            #self.channel.basic_consume(self.callback,
            #          queue=queue,
            #          no_ack=True)




        def loop(self):
            rx = self.context.getRx()
            while self.connection.is_open:

                try:
                    #FIX: bug trap empty queue
                    method, properties, bodyz = self.channel.basic_get(queue=self.queue, no_ack=False)
                    if method:
                        if (method.NAME == 'Basic.GetEmpty'):
                            time.sleep(1)
                        else:
                            self.cnt += 1
                            body = zlib.decompress(bodyz)
                            logging.debug("RabbitMQ received from "+self.queue+": "+ str(body))

                            pkt = json.loads(body)


                            rx.parse_n_load(pkt)

                            self.channel.basic_ack(delivery_tag=0, multiple=True)

                    else:
                        time.sleep(1)
                except pika.exceptions.ConnectionClosed as e:
                    logging.warning("Pika connection to "+self.queue+" closed.")



        # def callback(self, ch, method, properties, body):
        #     self.cnt += 1
        #     logging.debug("RabbitMQ received: "+ str(self.cnt))
        #     pkt = json.loads(body)
        #     l = len(pkt)
        #     func = None
        #     if method.routing_key in self.tag_map:
        #         func = self.tag_map[method.routing_key]
        #         data = pkt[l-1]["data"]
        #
        #     if func in PmkSeed.iplugins.keys():
        #         klass = PmkSeed.iplugins[func]
        #         rt = klass._stage_run(pkt, data)

        def run(self):
            #self.channel.start_consuming()


            self.loop()

    def __init__(self, context, connection):
        self.connection = connection
        self.channel = connection.channel()
        self.context = context
        self.tag_map = {}

    def add_monitor_queue(self, queue, func=None):
        self.tag_map[queue] = func
        #fqueue = queue+":"+self.context.getUuid()+":"+func
        fqueue = queue
        qthread = RabbitMQMonitor.MonitorThread(self, self.context, None, fqueue, exchange='')
        qthread.start()

        #TODO:fix default queue
        # aqueue = queue.split(":")
        # if len(aqueue) > 2:
        #     queue2 = "T:"+aqueue[1]+":"+aqueue[2]
        #     self.tag_map[queue2] = func
        #
        #     # qthread = RabbitMQMonitor.MonitorThread(self, self.context, None, queue)
        #     # qthread.start()
        #
        #     try:
        #         self.channel = self.connection.channel()
        #         self.channel.queue_declare(queue=str(queue2), passive=True,durable=True)
        #         logging.info("Using default rabbitmq queue: "+queue2)
        #         qthread = RabbitMQMonitor.MonitorThread(self, self.context, None, queue2)
        #         qthread.start()
        #     except Exception as e:
        #         qthread = RabbitMQMonitor.MonitorThread(self, self.context, None, queue)
        #         qthread.start()



        #self.channel.queue_declare(queue=queue)
        #self.channel.basic_consume(self.callback,
        #              queue=queue,
        #              no_ack=True)
        #self.channel.basic_qos(prefetch_count=10)

        #threading.Thread(target=self.channel.start_consuming)
        #self.channel.start_consuming()






class ZMQPacketMonitor(SThread):
    def __init__(self, context, zmqcontext, bind_to):
        SThread.__init__ (self)
        self.context = context
        self.bind_to = bind_to
        if (zmqcontext == None):
            self.zmq_cntx = zmq.Context()
            pass
        else:
            self.zmq_cntx = zmqcontext

        #self.zmq_cntx = zmq.Context()


        self.rx = self.context.getRx()

        pass

    # def proccess_pkt(self, pkts):
    #     pkt = json.loads(pkts)
    #     logging.debug("PACKET RECEIVED: "+pkts)
    #     #Check for PACK
    #     if pkt[0]["state"] == "PACK_OK":
    #
    #         seed = pkt[0]["last_func"]
    #
    #         if seed in PmkSeed.iplugins.keys():
    #             klass = PmkSeed.iplugins[seed]
    #             klass.pack_ok(pkt)
    #             self._packed_pkts += 1
    #             #logging.debug("PACKED pkts: "+str(self._packed_pkts))
    #             return True
    #     # if pkt[0]["state"] == "MERGE":
    #     #     seed = pkt[0]["last_func"]
    #     #
    #     #     if seed in PmkSeed.iplugins.keys():
    #     #         klass = PmkSeed.iplugins[seed]
    #     #         klass.merge(pkt)
    #     #         #klass.pack_ok(pkt)
    #     #         #self._packed_pkts += 1
    #     #         #logging.debug("PACKED pkts: "+str(self._packed_pkts))
    #     #         continue
    #     if pkt[0]["state"] == "ARP_OK":
    #         logging.debug("Received ARP_OK: "+json.dumps(pkt))
    #         self.context.put_pkt_in_shelve2(pkt)
    #         return True
    #
    #     l = len(pkt)
    #     func = pkt[l-1]["func"]
    #     data = pkt[l-2]["data"]
    #
    #     if ":" in func:
    #             func = func.split(":")[1]
    #
    #     if func in PmkSeed.iplugins.keys():
    #         klass = PmkSeed.iplugins[func]
    #         rt = klass._stage_run(pkt, data)


    def run(self):
        #context = zmq.Context()
        soc = self.zmq_cntx.socket(zmq.PULL)
        soc.setsockopt(zmq.RCVBUF, 2000)
        #soc.setsockopt(zmq.HWM, 100)
        try:
            bind_to = "tcp://*:"+str(PmkShared.ZMQ_ENDPOINT_PORT)
            soc.bind(bind_to)
        except zmq.ZMQError as e:
            nip = PmkBroadcast.get_llan_ip()
            self.bind_to = "tcp://"+str(nip)+":"+str(PmkShared.ZMQ_ENDPOINT_PORT)
            logging.warning("Rebinding to: "+self.bind_to)
            soc.bind(self.bind_to)


        #soc.setsockopt(zmq.HWM, 1000)
        #soc.setsockopt(zmq.SUBSCRIBE,self.topic)
        #soc.setsockopt(zmq.RCVTIMEO, 10000)

        queue_put = self.context.getRx().put
        dig = self.context.getRx().dig
        rx = self.context.getRx()
        p_dig = True
        while True:
            try:
                msg = soc.recv()
                #self.context.getRx().put(msg)
                d_msg = zlib.decompress(msg)
                pkt = json.loads(d_msg)
                rx.parse_n_load(pkt)
            except Exception as e:
                 logging.error(str(e))

            #     header = pkt[0]
            #     #check for back ppressure packets
            #     # if header["aux"] & Packet.BCKPRESSURE_BIT:
            #     #     if header["aux"] & Packet.PRESSURETOGGLE_BIT:
            #     #         last_host = header["last_host"]
            #     #         self.context.getProcGraph().disable_host_eps(last_host)
            #     #         logging.debug("Requeueing packet")
            #     #         pkt = Packet.clear_pkt_bit(pkt,Packet.BCKPRESSURE_BIT )
            #     #         pkt = Packet.clear_pkt_bit(pkt, Packet.PRESSURETOGGLE_BIT)
            #     #         self.context.get_tx(1).put_pkt(pkt)
            #     #     else:
            #     #         last_host = header["last_host"]
            #     #         logging.debug("Enabling Packet")
            #     #         self.context.getProcGraph().enable_host_eps(last_host)
            #
            #     if header["aux"] & Packet.NACK_BIT:
            #         if header["aux"] & Packet.TRACER_BIT:
            #             host = header["last_host"]
            #             c_tag = header["c_tag"]
            #             pred = header["c_pred"]
            #             c_wtime = header["c_wtime"]
            #             #print json.dumps(pkt)
            #
            #             self.context.getProcGraph().update_ep_prediction(pred, host,c_tag)
            #
            #     if dig(pkt):
            #         # if not p_dig:
            #         #     #release backpressure
            #         #     p_dig = True
            #         #     last_contact = header["last_contact"]
            #         #     header["aux"] = header["aux"] | Packet.BCKPRESSURE_BIT
            #         #     #header["aux"] = header["aux"] | Packet.PRESSURETOGGLE_BIT
            #         #     header["last_host"] = self.context.get_uuid()
            #         #     self.context.get_tx(2).put((None,None,None,pkt))
            #
            #         queue_put(pkt)
            #
            #     else:
            #         p_dig = False
            #         #back pressure
            #
            #         last_contact = header["last_contact"]
            #         header["aux"] = header["aux"] | Packet.BCKPRESSURE_BIT
            #         header["aux"] = header["aux"] | Packet.PRESSURETOGGLE_BIT
            #         header["last_host"] = self.context.get_uuid()
            #         self.context.get_tx(2).put((None,None,None,pkt))
            #
            #         #print last_contact
            #         pass
            #     #self.proccess_pkt(msg)
            #     #del msg
            #
            #     # if "REVERSE" in msg:
            #     #     logging.debug(msg)
            #     #     ep = msg.split("::")[1]
            #     #     logging.debug("Reverse connecting to: "+ep)
            #     #     rec = self.zmq_cntx.socket(zmq.PULL)
            #     #     rec.connect(ep)
            #     #     msg = rec.recv()
            #     #     logging.debug("Received msg: "+msg)
            #     #     #continue
            #     #self.rx.put(msg)
            #     #logging.debug("Message: "+str(msg))
            # # except zmq.ZMQError as e:
            # #     if self.stopped():
            # #         logging.debug("Exiting thread "+  self.__class__.__name__)
            # #         soc.close()
            # #         #zmq_cntx.destroy()
            # #         #zmq_cntx.term()
            # #         break
            # #     else:
            # #         continue
            # except Exception as e:
            #      logging.error(str(e))
            #
            # #except MemoryError as e:
            # #    logging.error(str(e))
            # #    sys.exit(1)




