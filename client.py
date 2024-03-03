import re
import socket

from FDFTPsocket import Task
from FDFTPSender import Sender
from FDFTPReceiver import Receiver
from config import MSS, SERVER_PORT, SERVER_IP, START_INTERVAL, MAX_TRY_COUNTS, DEBUG
from utils import packer


guidance = '### Welcome to use FDFTP, Arthur: Monika_Pandora\n' \
           '### This ftp is currently only able to transfer files under the current directory\n' \
           '### Type \'upload file_name\' to upload the file to the server\n' \
           '### Type \'download file_name\' to download the file on the server and saved under the current directory\n' \
           '### Type #quit to normally quit the program\n' \
           '### NOTE:\n' \
           '### This is only a very simple version, only transfer function is offered\n' \
           '### File Not Found or any other error handling is not available now\n' \
           '### If something went wrong when using, the best way is to restart the program'



def get_host_using_ip(server_addr):
    so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        so.connect(('10.255.255.255', 1))
        ip = so.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        so.close()
    return ip


class MyClient:
    def __init__(self, server_address):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_socket.bind((get_host_using_ip(server_address), 0))
        if DEBUG:
            print('client bind to', self.client_socket.getsockname())
        self.server_address = server_address
        self.cmds = ['^(upload)\s+(\S+)', '^(download)\s+(\S+)']

    def do_upload(self, file_path):
        interval = START_INTERVAL
        cmd_try_count = 0
        task = Task(file_path)
        success = False
        sender = None
        # shake hands
        while cmd_try_count < MAX_TRY_COUNTS and not success:
            try:
                self.client_socket.settimeout(interval)
                cmd_pkt = packer.pack_cmd('upload', file_path)
                self.client_socket.sendto(cmd_pkt, self.server_address)
                port_pkt, addr = self.client_socket.recvfrom(MSS)
                # assert addr == self.server_address
                if packer.is_port_pkt(port_pkt):
                    success = True
                    port = packer.unpack_port(port_pkt)
                    new_addr = (self.server_address[0], port)
                    start_pkt = packer.pack_sig('start')
                    self.client_socket.sendto(start_pkt, new_addr)
                    sender = Sender(file_path, new_addr, self.client_socket, task)
            except Exception as e:
                if isinstance(e, socket.timeout):
                    cmd_try_count += 1
                    if cmd_try_count < MAX_TRY_COUNTS:
                        interval *= 2
                        if DEBUG:
                            print('try to ask for upload, count', cmd_try_count + 1)
                    else:
                        print('connection failed, just try again!')
                else:
                    print(e)
                    pass
        if sender is not None:
            sender.start()
        if DEBUG:
            print('do_upload exit')

    def do_download(self, file_path):
        interval = START_INTERVAL
        success = False
        cmd_try_count = 0
        receiver = None
        # shake hands
        while cmd_try_count < MAX_TRY_COUNTS and not success:
            try:
                self.client_socket.settimeout(interval)
                cmd_pkt = packer.pack_cmd('download', file_path)
                self.client_socket.sendto(cmd_pkt, self.server_address)
                if DEBUG:
                    print('send download command')

                port_pkt, addr = self.client_socket.recvfrom(MSS)
                # assert addr == self.server_address
                if packer.is_port_pkt(port_pkt):
                    port = packer.unpack_port(port_pkt)
                    new_addr = (self.server_address[0], port)
                    if DEBUG:
                        print('recv new port', port, 'from', addr)
                    start_pkt = packer.pack_sig('start')
                    if DEBUG:
                        print('send start signal to', new_addr)
                    self.client_socket.sendto(start_pkt, new_addr)
                    receiver = Receiver(file_path, self.client_socket, new_addr)
                    success = True
            except Exception as e:
                if isinstance(e, socket.timeout):
                    cmd_try_count += 1
                    if cmd_try_count < MAX_TRY_COUNTS:
                        interval *= 2
                        if DEBUG:
                            print('try to ask for download, count', cmd_try_count + 1)
                    else:
                        print('connection failed, just try again!')
                else:
                    pass
        if receiver is not None:
            receiver.start()
        if DEBUG:
            print('do_download exit')

    def run(self):
        print(guidance)
        while True:
            print('FDFTP> ', end='')
            cmd = input()
            if cmd == '#quit':
                break
            ma = None
            for pat in self.cmds:
                ma = re.match(pat, cmd)
                if ma is not None:
                    break
            if ma is not None:
                if ma.group(1) == 'upload':
                    self.do_upload(ma.group(2))
                elif ma.group(1) == 'download':
                    self.do_download(ma.group(2))
            else:
                print('Unknown command, see the messages above')


def main():
    server_address = (SERVER_IP, SERVER_PORT)
    client = MyClient(server_address)
    client.run()


if __name__ == "__main__":
    main()
