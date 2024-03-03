import queue
import socket
import threading
import time
import select

from FDFTPsocket import Task
from config import *
from utils import packer


# machine state
SEND_DATA = 0x00
ACK_RCV = 0x01

# congestion state
SS = 0x02
CA = 0x04


class Sender:
    def __init__(self, file_path, rcvr_addr, caller_socket, task=None):
        # socket
        self.socket = caller_socket
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUF_SIZE)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUF_SIZE)
        self.rcvr_addr = rcvr_addr
        self.task = task

        # file datas and some marks
        self.file_path = file_path
        self.__segments = []
        self.__counters = []
        self.__marks = []
        self.__last_send_time = []
        self.__last_send_time_pri = queue.PriorityQueue()
        self.__last_rcv_ack_time = time.time()

        # FSM concerned menbers
        self.state = SEND_DATA
        self.func_tabel = {SEND_DATA: self.__send_data, ACK_RCV: self.__ack_rcv}
        self.congestion_state = SS
        self.congestion_suc_ack_table = {SS: self.__ss_suc_ack, CA: self.__ca_suc_ack}

        # congestion control
        self.__last_rtt_arrive_time = None
        self.rtt = 0.1
        self.base = 0
        self.next_seq = 0
        self.cwnd = 2
        self.ssthresh = 64
        self.timeout = 4 * self.rtt
        self.change_state = False

        # for basic logics, not important
        self.__offline_checker_count = 0
        self.__offline_checker_interval = START_INTERVAL

        self.exit = False
        self.exit_message = None
        self.eof_informed = False

        # for debug
        self.timeout_count = 0
        self.fast_retr_count = 0

    def __ss_suc_ack(self, num):
        self.cwnd += num
        if self.cwnd > self.ssthresh and self.change_state:
            self.congestion_state = CA

    def __ca_suc_ack(self, num):
        self.cwnd += num * 1 / self.cwnd

    def __rtt_estimate(self, seq):
        ti = time.time()
        self.rtt = 0.875 * self.rtt + 0.125 * (ti - self.__last_send_time[seq])
        self.timeout = 4 * self.rtt

    def __send_data(self):
        # send one data if available, and change state into ACK_RCV
        _, writable, _ = select.select([], [self.socket], [], 0)
        if len(writable) != 0 and self.next_seq - self.base < self.cwnd and self.next_seq < len(self.__segments):
            seg_pkt = packer.pack_seg(self.next_seq, self.__segments[self.next_seq])
            t = time.time()
            self.__last_send_time[self.next_seq] = t
            self.__last_send_time_pri.put((t, self.next_seq))
            self.next_seq += 1
            self.task.sendto(self.socket, seg_pkt, self.rcvr_addr)

        self.state = ACK_RCV

    def retransmit(self, seq):
        seg_pkt = packer.pack_seg(seq, self.__segments[seq])
        # _, writable, _ = select.select([], [self.socket], [])
        self.task.sendto(self.socket, seg_pkt, self.rcvr_addr)

    def timeout_retransmit(self, seq):
        if DEBUG:
            self.timeout_count += 1
        self.ssthresh = max(self.cwnd // 2, 1024)
        self.cwnd = 1
        self.retransmit(seq)
        ti = time.time()
        self.__last_send_time[seq] = ti
        self.__last_send_time_pri.put((ti, seq))
        self.congestion_state = SS

    def fast_retransmit(self, seq):
        if DEBUG:
            self.fast_retr_count += 1
        self.ssthresh = max(self.cwnd // 2, 1024)
        self.cwnd = self.ssthresh + 3
        self.retransmit(seq)
        self.__last_send_time[seq] = time.time()
        self.congestion_state = CA

    def __ack_rcv(self):
        # attempt to receive ack
        ack_pkt = None
        readable, _, _ = select.select([self.socket], [], [], 0)
        if len(readable):
            ack_pkt, addr = self.socket.recvfrom(MSS)
        if ack_pkt is not None and ack_pkt != b'' and packer.is_ack_pkt(ack_pkt):
            if DEBUG:
                print('recv ack from', addr)
            # ack received this try
            self.__last_rcv_ack_time = time.time()
            self.__offline_checker_count = 0
            self.__offline_checker_interval = START_INTERVAL
            ack, real_seq = packer.unpack_ack(ack_pkt)
            if ack < self.base:
                self.__marks[:ack] = [1] * ack
                pass
            elif ack > real_seq:
                # receiver slided (ack - real_seq) when generate this pkt
                if ack == len(self.__segments):
                    self.exit = True
                    self.exit_message = 'successfully send file ' + self.file_path
                    return
                self.__marks[:ack] = [1] * ack
                self.base = ack
                self.congestion_suc_ack_table[self.congestion_state](ack - real_seq)
                if self.__counters[real_seq] == 0:
                    self.__rtt_estimate(real_seq)
            else:
                # ack will never be real_seq
                # so ack must be less than real_seq
                # this indicates that the segments numbered as ack may be lost
                # the loss counter add 1 for that pkt
                # if the loss counter of segments numbered as ack is about to be 3, do fast retransmit
                self.__marks[:ack] = [1] * ack
                self.__marks[real_seq] = 1
                self.__counters[ack] += 1
                if self.__counters[ack] == 3 and self.__marks[ack] == 0:
                    self.fast_retransmit(ack)
                    self.__counters[ack] = 0
                    pass
        else:
            # not received ack, check if the receiver offline
            ti = time.time()
            if ti - self.__last_rcv_ack_time >= self.__offline_checker_interval:
                self.__offline_checker_count += 1
                self.__offline_checker_interval *= 2
            if self.__offline_checker_count >= MAX_TRY_COUNTS:
                self.exit = True
                self.exit_message = 'receiver seems to be offline, exited'
                return

        # check if timeout
        t = None
        while not self.__last_send_time_pri.empty():
            # loop to find the oldest pkt
            # update some retransmitted pkt last_send_time
            # ignore pkt that has been acked
            t, seq = self.__last_send_time_pri.get()
            if t < self.__last_send_time[seq]:
                t = self.__last_send_time[seq]
                self.__last_send_time_pri.put((t, seq))
            elif self.__marks[seq] == 1:
                t = None
                continue
            else:
                break
        if t is not None:
            if time.time() - t < self.timeout:
                # no timeout
                self.__last_send_time_pri.put((t, seq))
            else:
                self.timeout_retransmit(seq)

        # don't forget to change state
        self.state = SEND_DATA

    def inform_eof(self):
        # try to inform eof
        interval = START_INTERVAL
        recv_delay_count = 0
        while recv_delay_count < MAX_TRY_COUNTS:
            try:
                self.socket.settimeout(interval)
                eof_pkt = packer.pack_sig('eof')
                self.task.sendto(self.socket, eof_pkt, self.rcvr_addr)
                pkt, _ = self.socket.recvfrom(MSS)
                if packer.is_sig_pkt(pkt):
                    sig = packer.unpack_sig(pkt)
                    if sig == 'eof':
                        self.eof_informed = True
                        break
            except Exception as e:
                if isinstance(e, socket.timeout):
                    recv_delay_count += 1
                    if recv_delay_count < START_INTERVAL:
                        interval *= 2
                        if DEBUG:
                            print('informing receiver end of file timeout after', recv_delay_count, 'retries')
                    else:
                        if DEBUG:
                            print('file bytes all acked, but the receiver may stuck in thread')
                else:
                    print(e)
                    pass

        # send three exit packet and exit
        if self.exit and self.eof_informed:
            exit_pkt = packer.pack_sig('exit')
            for i in range(3):
                self.task.sendto(self.socket, exit_pkt, self.rcvr_addr)

    def __preprocess(self):
        try:
            with open(self.file_path, 'rb') as f:
                size = 0
                while True:
                    seg = f.read(SEG_SZ)
                    if seg != b'':
                        size += SEG_SZ
                        self.__segments.append(seg)
                    else:
                        break
                if size > MIN_CONGESTION_CONTROL_FILE_SZ:
                    self.change_state = True
        except Exception as e:
            print(e)
            return

        self.__counters = [0] * len(self.__segments)
        self.__marks = [0] * len(self.__segments)
        self.__last_send_time = [-1] * len(self.__segments)
        self.__last_rcv_ack_time = time.time()

        if self.task is None:
            self.task = Task(self.file_path)

    def speed(self):
        while not self.exit:
            time.sleep(1)
            if self.exit:
                break
            finished = 100 * self.base * SEG_SZ / self.task.file_size
            speed = self.base * SEG_SZ / (1024 * (time.time() - self.task.start_time))
            if speed < 1024:
                print('%.2f' % finished + '%, speed:', '%.2f' % speed, 'KB/s')
            else:
                print('%.2f' % finished + '%, speed:', '%.2f' % (speed / 1024), 'MB/s')

    def __run(self):
        speed = threading.Thread(target=self.speed)
        speed.start()
        blocking = self.socket.getblocking()
        self.socket.setblocking(True)
        while not self.exit:
            self.func_tabel[self.state]()
        self.socket.setblocking(blocking)
        print(self.exit_message)
        if DEBUG:
            print('all seg:', len(self.__segments))
            print('timeout count:', self.timeout_count)
            print('fast retrans count:', self.fast_retr_count)
        self.inform_eof()
        self.task.finish()
        speed.join()

    def start(self):
        self.__preprocess()
        self.__run()



