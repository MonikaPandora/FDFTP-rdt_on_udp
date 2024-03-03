import queue
import select
import socket

from config import *
from utils import packer


ORDER = 0
DISORDER = 1


class Receiver:
    def __init__(self, file_path, s, sender_address):
        self.sender_address = sender_address
        self.buffer = queue.PriorityQueue()
        self.buffered = []
        self.rcv_base = 0
        self.socket = s
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUF_SIZE)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUF_SIZE)
        if DEBUG:
            print('receiver socket sock name', self.socket.getsockname())
        self.file = None
        self.file_path = file_path
        self.over = False
        self.exit = False
        self.exit_message = None

    def wait_for_new(self):
        interval = START_INTERVAL
        count = 0
        while count < MAX_TRY_COUNTS:
            try:
                self.socket.settimeout(interval)
                pkt, _ = self.socket.recvfrom(MSS)
            except Exception as e:
                if isinstance(e, socket.timeout):
                    count += 1
                    interval *= 2
                    if count == MAX_TRY_COUNTS:
                        self.exit = True
                        self.exit_message = 'sender seems to be offline, connection closed'
                        return None
                else:
                    print(e)
                    exit(1)
            else:
                if packer.is_seg_pkt(pkt):
                    seq, seg = packer.unpack_seg(pkt)
                    if seq >= self.rcv_base and seq not in self.buffered:
                        self.buffer.put((seq, seg))
                        self.buffered.append(seq)
                        if DEBUG:
                            print('rcv seq:', seq)
                        return seq
                elif packer.is_sig_pkt(pkt):
                    sig = packer.unpack_sig(pkt)
                    if sig == 'eof':
                        self.exit = True
                        self.exit_message = 'successfully received file'
                        return None

    def send_ack(self, real_seq):
        _, writable, _ = select.select([], [self.socket], [])
        ack_pkt = packer.pack_ack(self.rcv_base, real_seq)
        if self.rcv_base == real_seq:
            self.exit = True
            exit(1)
        self.socket.sendto(ack_pkt, self.sender_address)

    def recv(self):
        seq = self.wait_for_new()
        if seq is None:
            return
        if seq == self.rcv_base:
            self.slide()
        self.send_ack(seq)

    def inform_exit(self):
        interval = START_INTERVAL
        recv_try_count = 0
        resp_eof_pkt = packer.pack_sig('eof')
        while recv_try_count < MAX_TRY_COUNTS:
            try:
                self.socket.settimeout(interval)
                self.socket.sendto(resp_eof_pkt, self.sender_address)
                exit_pkt, _ = self.socket.recvfrom(MSS)
                if packer.is_sig_pkt(exit_pkt):
                    ex = packer.unpack_sig(exit_pkt)
                    if ex == 'exit':
                        break
            except Exception as e:
                if isinstance(e, socket.timeout):
                    recv_try_count += 1
                    if recv_try_count < MAX_TRY_COUNTS:
                        interval *= 2
                        if DEBUG:
                            print('did not receive exit packet after', recv_try_count, 'retries')
                else:
                    pass

    def run(self):
        print('start receiving')
        while not self.exit:
            self.recv()
        print(self.exit_message)
        self.inform_exit()

    def slide(self):
        while not self.buffer.empty():
            seq, seg = self.buffer.get()
            if seq == self.rcv_base:
                self.buffered.remove(seq)
                self.file.write(seg)
                self.rcv_base += 1
            else:
                self.buffer.put((seq, seg))
                break

    def start(self):
        try:
            self.file = open(self.file_path, 'wb')
        except Exception as e:
            print(e)
            return
        blocking = self.socket.getblocking()
        self.socket.setblocking(True)
        self.run()
        self.file.close()
        self.socket.setblocking(blocking)
