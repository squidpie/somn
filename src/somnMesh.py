#!/usr/bin/env python3.3

import somnTCP
import somnUDP
import somnPkt
import somnConst
import struct
import queue
import threading
import socket
import time

class somnMesh(threading.Thread):
  TCPTxQ = queue.Queue()
  TCPRxQ = queue.Queue()
  UDPRxQ = queue.Queue()
  UDPAlive = threading.Event()
  networkAlive = threading.Event()
  routeTable = [(0,0,0),(0,0,0),(0,0,0),(0,0,0),(0,0,0)]
  cacheId = [0,0,0,0]
  cacheRoute = [0,0,0,0]
  _mainLoopRunning = 0
  enrolled = False
  nodeID = 0
  nodeIP = "127.0.0.1"
  nodePort = 0
  lastEnrollReq = 0
  availRouteCount = 5
  
  def IP2Int(self, IP):
    o = list(map(int, IP.split('.')))
    res = (16777216 * o[0]) + (65536 * o[1]) + (256 * o[2]) + o[3]
    return res

  def Int2IP(self,Int ):
    o1 = int(Int / 16777216) % 256
    o2 = int(Int / 65536) % 256
    o3 = int(Int / 256) % 256
    o4 = int(Int) % 256
    return '%(o1)s.%(o2)s.%(o3)s.%(o4)s' % locals()

  def __init__(self, TxDataQ, RxDataQ):
    threading.Thread.__init__(self)
    self.CommTxQ = TxDataQ
    self.CommRxQ = RxDataQ
    self.nodeID = 1
    
     
  def enroll(self):
    print("enrolling")
    tcpRespTimeout = False
    routeIndex = 0
    ACK = 56
    enrollPkt = somnPkt.SomnPacket()
    enrollPkt.InitEmpty("NodeEnrollment")
    enrollPkt.PacketFields['ReqNodeID'] = self.nodeID
    enrollPkt.PacketFields['ReqNodeIP'] = self.IP2Int(self.nodeIP)
    enrollPkt.PacketFields['ReqNodePort'] = self.nodePort
    enrollPkt.PacketFields['ACKSeq'] = ACK

    udp = somnUDP.somnUDPThread(enrollPkt, self.UDPRxQ, self.networkAlive, self.UDPAlive)
    udp.start()
    while routeIndex < 3 or not tcpRespTimeout:
      print("Enroll Attempt Loop")
      try:
        enrollPkt = self.TCPRxQ.get(timeout = 5)
      except queue.Empty:
        tcpRespTimeout = True
        print("Enroll failed")
        break 
      else:
        enrollResponse = somnPkt.SomnPacket(enrollPkt)
        if enrollResponse.PacketType == somnPkt.SomnPacketType.NodeEnrollment and enrollResponse.PacketFields['ACKSeq'] == ACK:
          routeTable[routeIndex] = (enrollResponse.PacketFields['RespNodeID'], enrollResponse.PacketFields['RespNodeIP'], enrollResponse.PacketFields['RespNodePort'])
          routeIndex = routeIndex + 1
          packedEnrollResponse = somnPkt.SomnPacketTxWrapper(enrollResponse, enrollResponse.PacketFields['RespNodeIP'], enrollResponse.Packetfields['RespNodePort']) 
          self.TCPTxQ.put(packedEnrollResponse)
          enrolled = True
          availRouteCount = availRouteCount - 1
          print("Enrolled complete")
    return udp  
  
    
  def run(self):
    socket.setdefaulttimeout(5)
    self.networkAlive.set()
    Rx = somnTCP.startSomnRx(self.networkAlive, self.TCPRxQ)
    Tx = somnTCP.startSomnTx(self.networkAlive, self.TCPTxQ)
    enrollAttempts = 0
    while not self.enrolled and enrollAttempts < 3:
      self.UDPAlive.set()
      UDP = self.enroll()
      if not self.enrolled and enrollAttempts < 2:
        self.UDPAlive.clear()
        UDP.join()
        enrollAttempts = enrollAttempts + 1
      elif not self.enrolled:
        self.enrolled = True
        print("Setting up single node network")
      else:
        break

    #start main loop to handle incoming queueus
    self._mainLoopRunning = 1
    testCount = 0
    while self._mainLoopRunning:
      self._handleTcpRx()
      self._handleUdpRx()
      self._handleTx()
      #time.sleep(5)
      #testCount = testCount + 1

    # Do a bunch of stuff
    self.networkAlive.clear()
    UDP.join()
    Rx.join()
    Tx.join()

  def _handleTx(self):
    print("Handle TX")
    
    try:
      TxPkt = self.TxQ.get(False)
    except:
      return


    route = 0
    destId = TxPkt.PacketFields['DestID']
    #check cache for route to dest ID
    if destId in cacheId:
      route = cacheRoute[cacheId.index(destId)]
    else:
      route = self._getRoute(destId)
    
    #pop first step in route from route string

    #set route string in packet
    TxPkt.PacketFields['Route'] = route

    
 
  def _handleTcpRx(self):
    print("Handle RX")
    try:
      RxPkt = self.TCPRxQ.get(False)
    except:
      pass
    
  def _handleUdpRx(self):
    print("handleUDP")
    try:
      enrollPkt = self.UDPRxQ.get(False)
    except:
      return
    enrollRequest = somnPkt.SomnPacket(enrollPkt)
    if self.availRouteCount > 1 or (self.lastEnrollRequest == enrollRequest.PacketFields['ReqNodeID'] and self.availRouteCount > 0):
      print(enrollRequest)
      enrollRequest.PacketFields['RespNodeID'] = self.nodeID
      enrollRequest.PacketFields['RespNodeIP'] = self.nodeIP
      enrollRequest.PacketFields['RespNodePort'] = self.nodePort
      packedEnrollResponse = somnPkt.SomnPacketTxWrapper(enrollRequest, enrollRequest.PacketFields['ReqNodeIP'], enrollRequest.PacketFields['ReqNodePort']) 
      self.lastEnrollRequest = enrollRequest.PacketFields['ReqNodeID']
      self.TCPTxQ.put(packedEnrollResponse) 
    else:
      self.lastEnrollRequest = enrollRequest.PacketFields['ReqNodeID']


  def _getRoute(self, destId):
    pass

  def _popRoute(self, route):
    firstStep = route & 0x7
    newRoute = route >> 3
    return (firstStep, newRoute)

  def _pushRoute(self, route, nextStep):
    newRoute = (route << 3) | (nextStep & 0x7)
    return newRoute

if __name__ == "__main__":
  rxdq = queue.Queue()
  txdq = queue.Queue()
  mesh = somnMesh(txdq, rxdq)
  mesh.start()

