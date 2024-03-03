#!/usr/bin/python
#coding:utf-8

import socket
import threading
import select

from FDFTPsocket import Task
from FDFTPSender import Sender
from FDFTPReceiver import Receiver
from config import MSS, SERVER_PORT, SERVER_IP, START_INTERVAL, MAX_TRY_COUNTS, DEBUG
from utils import packer


class MyServer:
    def __init__(self, ip, port):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_ip = ip
        self.server_socket.bind((ip, port))
        print('server port:', self.server_socket.getsockname()[1])
        self.terminate = False
        self.client_thread_list = []
        self.in_service_ip = []
        print('The server is ready')

    def input_listening_entry(self):
        while True:
            cmd = input()
            if cmd == 'quit':
                self.terminate = True
                break

    def client_service(self, cmd, file_path, client_addr):
        new_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if cmd == 'upload':
            new_socket.bind((self.server_ip, 0))
            new_port = new_socket.getsockname()[1]
            port_pkt = packer.pack_port(new_port)
            interval = START_INTERVAL
            send_port_try_count = 0
            receiver = None
            while send_port_try_count < MAX_TRY_COUNTS:
                try:
                    new_socket.settimeout(interval)
                    self.server_socket.sendto(port_pkt, client_addr)
                    if DEBUG:
                        print('send port_pkt')
                    start_pkt, _ = new_socket.recvfrom(MSS)
                    if packer.is_sig_pkt(start_pkt):
                        start = packer.unpack_sig(start_pkt)
                        if start == 'start':
                            if DEBUG:
                                print('start receiving file:', file_path)
                            receiver = Receiver(file_path, new_socket, client_addr)
                            break
                except Exception as e:
                    if isinstance(e, socket.timeout):
                        send_port_try_count += 1
                        if send_port_try_count < MAX_TRY_COUNTS:
                            interval *= 2
                            if DEBUG:
                                print('start signal not yet received after trying', send_port_try_count, 'times')
                        else:
                            print('connection failed')
                    else:
                        pass
            if receiver is not None:
                receiver.start()
            new_socket.close()
        elif cmd == 'download':
            new_socket.bind((self.server_ip, 0))
            new_port = new_socket.getsockname()[1]
            port_pkt = packer.pack_port(new_port)
            interval = START_INTERVAL
            send_port_try_count = 0
            sender = None
            task = Task(file_path)
            while send_port_try_count < MAX_TRY_COUNTS:
                try:
                    new_socket.settimeout(interval)
                    self.server_socket.sendto(port_pkt, client_addr)
                    start_pkt, addr = new_socket.recvfrom(MSS)
                    if packer.is_sig_pkt(start_pkt):
                        start = packer.unpack_sig(start_pkt)
                        if start == 'start':
                            if DEBUG:
                                print('start sending file:', file_path)
                            sender = Sender(file_path, addr, new_socket, task)
                            break
                except Exception as e:
                    if isinstance(e, socket.timeout):
                        send_port_try_count += 1
                        if send_port_try_count < MAX_TRY_COUNTS:
                            interval *= 2
                            if DEBUG:
                                print('start signal not yet received after trying', send_port_try_count, 'times')
                        else:
                            print('connection failed')
                    else:
                        pass
            if sender is not None:
                sender.start()
            new_socket.close()

        self.in_service_ip.remove(client_addr)
        if DEBUG:
            print('client_service exit')

    def start_input_listening(self):
        input_thread = threading.Thread(target=self.input_listening_entry)
        input_thread.start()

    def run(self):
        self.start_input_listening()
        while not self.terminate:
            readable, _, _ = select.select([self.server_socket], [], [], 0.5)
            if len(readable):
                try:
                    cmd_pkt, addr = self.server_socket.recvfrom(MSS)
                except BlockingIOError:
                    pass
                else:
                    if addr in self.in_service_ip:
                        continue
                    if packer.is_cmd_pkt(cmd_pkt):
                        if DEBUG:
                            print('Received commands from', addr)
                        cmd, file_path = packer.unpack_cmd(cmd_pkt)
                        client_thread = threading.Thread(target=self.client_service, args=(cmd, file_path, addr))
                        self.client_thread_list.append(client_thread)
                        self.in_service_ip.append(addr)
                        client_thread.start()

        for ct in self.client_thread_list:
            ct.join()

        self.server_socket.close()
        print('The server is closed.')


def main():
    server = MyServer(SERVER_IP, SERVER_PORT)
    server.run()


if __name__ == "__main__":
    main()
